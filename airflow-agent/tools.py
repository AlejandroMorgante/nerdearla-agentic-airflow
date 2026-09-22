"""Tools de Strands para el workshop. Credenciales en Secrets Manager."""

import ast
import base64
import hashlib
import json
import os
import re
from functools import lru_cache
from urllib.parse import quote, urlparse

import boto3
import requests
from botocore.config import Config
from strands import tool

MAX_FILE_BYTES = 100_000


def _setting(name: str, default: str = "") -> str:
    value = os.environ.get(name, default).strip()
    if not value:
        raise ValueError(f"Falta configurar {name} en el Runtime.")
    return value


@lru_cache
def _client(service: str):
    return boto3.client(
        service,
        region_name=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION"),
        config=Config(connect_timeout=5, read_timeout=30,
                      retries={"mode": "standard", "total_max_attempts": 3}),
    )


def _secret(setting: str, field: str) -> str:
    # Sin cache: los cambios de credenciales se leen en la siguiente operación.
    response = _client("secretsmanager").get_secret_value(SecretId=_setting(setting))
    try:
        value = json.loads(response["SecretString"])[field]
        if not isinstance(value, str) or not value.strip():
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        raise ValueError(f"El secreto de {setting} debe contener el campo {field}.") from None
    return value


def _environment() -> dict:
    return _client("mwaa").get_environment(Name=_setting("MWAA_ENVIRONMENT_NAME"))["Environment"]


def _dag_path(dag_id: str) -> str:
    if dag_id != _setting("AIRFLOW_DAG_ID", "demo_pipeline"):
        raise ValueError("El DAG no está habilitado para este workshop.")
    return f"/dags/{quote(dag_id, safe='')}"


def _run_path(dag_id: str, run_id: str) -> str:
    return f"{_dag_path(dag_id)}/dagRuns/{quote(run_id, safe='')}"


def _airflow(path: str, method: str = "GET", **kwargs) -> dict:
    response = _client("mwaa").invoke_rest_api(
        Name=_setting("MWAA_ENVIRONMENT_NAME"), Path=path, Method=method, **kwargs
    )
    if not 200 <= response["RestApiStatusCode"] < 300:
        raise RuntimeError(f"Airflow respondió HTTP {response['RestApiStatusCode']}.")
    return response["RestApiResponse"]


def _bounded(value: int, maximum: int) -> int:
    if not 1 <= value <= maximum:
        raise ValueError(f"El límite debe estar entre 1 y {maximum}.")
    return value


@tool
def get_dag_details(dag_id: str) -> dict:
    """Consulta la definición del DAG, sus tareas y dependencias."""
    path = _dag_path(dag_id)
    return {"dag": _airflow(f"{path}/details"), "tasks": _airflow(f"{path}/tasks")}


@tool
def list_dag_runs(dag_id: str, limit: int = 10, offset: int = 0) -> dict:
    """Lista ejecuciones recientes. Aumentar offset para consultar otra página."""
    if offset < 0:
        raise ValueError("offset debe ser mayor o igual a cero.")
    return _airflow(f"{_dag_path(dag_id)}/dagRuns", QueryParameters={
        "limit": _bounded(limit, 100), "offset": offset, "order_by": "-start_date",
    })


@tool
def get_dag_run(dag_id: str, run_id: str) -> dict:
    """Consulta el estado y la configuración de una ejecución concreta."""
    return _airflow(_run_path(dag_id, run_id))


@tool
def list_task_instances(dag_id: str, run_id: str, offset: int = 0) -> dict:
    """Lista tareas, estados e intentos de una ejecución, en páginas de 100."""
    if offset < 0:
        raise ValueError("offset debe ser mayor o igual a cero.")
    return _airflow(f"{_run_path(dag_id, run_id)}/taskInstances",
                    QueryParameters={"limit": 100, "offset": offset})


def _log_location(dag_id: str, run_id: str, task_id: str) -> tuple[str, str]:
    _dag_path(dag_id)
    if any(not value or "/" in value for value in (run_id, task_id)):
        raise ValueError("run_id y task_id deben ser identificadores sin '/'.")
    logging = _environment().get("LoggingConfiguration", {}).get("TaskLogs", {})
    if not logging.get("Enabled"):
        raise ValueError("Los logs de tareas no están habilitados en MWAA.")
    group = logging["CloudWatchLogGroupArn"].split(":log-group:", 1)[1].removesuffix(":*")
    return group, f"dag_id={dag_id}/run_id={run_id}/task_id={task_id}/"


@tool
def list_task_log_streams(dag_id: str, run_id: str, task_id: str) -> dict:
    """Descubre los streams de la tarea, incluyendo intentos y tareas mapeadas."""
    group, prefix = _log_location(dag_id, run_id, task_id)
    pages = _client("logs").get_paginator("describe_log_streams").paginate(
        logGroupName=group, logStreamNamePrefix=prefix,
        PaginationConfig={"MaxItems": 100},
    ).build_full_result()
    return {"streams": [s["logStreamName"] for s in pages.get("logStreams", [])],
            "truncated": bool(pages.get("NextToken"))}


@tool
def read_task_logs(dag_id: str, run_id: str, task_id: str, stream: str,
                   limit: int = 100, next_token: str = "") -> dict:
    """Lee el final del log. Usar previous_token como next_token para retroceder."""
    group, prefix = _log_location(dag_id, run_id, task_id)
    if not stream.startswith(prefix):
        raise ValueError("El stream no corresponde a la tarea indicada.")
    params = {"logGroupName": group, "logStreamName": stream,
              "limit": _bounded(limit, 200), "startFromHead": False}
    if next_token:
        params["nextToken"] = next_token
    response = _client("logs").get_log_events(**params)
    events = response["events"]
    return {"events": [{"timestamp": e["timestamp"], "message": e["message"][:4000]}
                       for e in events],
            "messages_truncated": any(len(e["message"]) > 4000 for e in events),
            "previous_token": response["nextBackwardToken"],
            "at_start": next_token == response["nextBackwardToken"]}


@tool
def inspect_mwaa_permissions() -> dict:
    """Lee las políticas inline del rol de MWAA y simula acceso al archivo de entrada.

    La simulación IAM es evidencia parcial: no reproduce todas las políticas
    de recursos, SCPs ni condiciones de una llamada real. No modifica permisos.
    """
    role_arn = _environment()["ExecutionRoleArn"]
    role_name = role_arn.rsplit("/", 1)[1]
    iam = _client("iam")
    role = iam.get_role(RoleName=role_name)["Role"]
    names = iam.get_paginator("list_role_policies").paginate(RoleName=role_name)
    policies = [iam.get_role_policy(RoleName=role_name, PolicyName=name)["PolicyDocument"]
                for page in names for name in page["PolicyNames"]]
    attached = [policy for page in iam.get_paginator("list_attached_role_policies").paginate(
        RoleName=role_name) for policy in page["AttachedPolicies"]]
    checks = iam.simulate_principal_policy(
        PolicySourceArn=role_arn, ActionNames=["s3:GetObject"],
        ResourceArns=[f"arn:aws:s3:::{_setting('SALES_INPUT_BUCKET')}/{_setting('SALES_INPUT_KEY')}"],
    )["EvaluationResults"]
    return {"role_arn": role_arn, "inline_policies": policies, "attached_policies": attached,
            "permissions_boundary": role.get("PermissionsBoundary"), "simulation": checks,
            "note": "Simulación parcial; contrastar con los logs. Las managed policies se listan sin su contenido."}


@tool
def inspect_sales_file() -> dict:
    """Consulta metadatos del archivo de entrada usando el rol del agente, no el de MWAA."""
    bucket, key = _setting("SALES_INPUT_BUCKET"), _setting("SALES_INPUT_KEY")
    response = _client("s3").head_object(Bucket=bucket, Key=key)
    return {"bucket": bucket, "key": key, "size": response["ContentLength"],
            "etag": response.get("ETag"), "checked_as": "agent_runtime_role"}


def _relative_path(path: str) -> str:
    if not path or any(p in ("", ".", "..") for p in path.split("/")) or "\\" in path:
        raise ValueError("Se requiere un path relativo sin segmentos vacíos, '.' o '..'.")
    return path


@tool
def read_deployed_dag(relative_path: str = "demo_pipeline.py") -> dict:
    """Lee el código actual en S3, relativo a la carpeta de DAGs de MWAA.

    Es la versión actual del objeto, no necesariamente la usada por una ejecución pasada.
    """
    relative_path = _relative_path(relative_path)
    environment = _environment()
    bucket = environment["SourceBucketArn"].split(":::", 1)[1]
    key = f"{environment['DagS3Path'].rstrip('/')}/{relative_path}"
    response = _client("s3").get_object(Bucket=bucket, Key=key)
    with response["Body"] as body:
        content = body.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise ValueError("El archivo supera el tamaño máximo de 100 KB.")
    return {"key": key, "version_id": response.get("VersionId"),
            "content": content.decode("utf-8")}


def _github(method: str, path: str, *, allow_missing: bool = False, **kwargs):
    repo = _setting("GITHUB_REPO")
    if len(repo.split("/")) != 2 or any(not p for p in repo.split("/")):
        raise ValueError("GITHUB_REPO debe tener el formato owner/repo.")
    url = f"https://api.github.com/repos/{quote(repo, safe='/')}{path}"
    try:
        response = requests.request(method, url, headers={
            "Authorization": f"Bearer {_secret('GITHUB_SECRET_ID', 'token')}",
            "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
        }, timeout=(5, 30), allow_redirects=False, **kwargs)
    except requests.RequestException:
        raise RuntimeError("GitHub no confirmó la operación; verificar antes de reintentar.") from None
    if response.status_code == 404 and allow_missing:
        return None
    if not 200 <= response.status_code < 300:
        raise RuntimeError(f"GitHub respondió HTTP {response.status_code}.")
    return response.json()


def _repo_file(path: str, ref: str) -> dict:
    result = _github("GET", f"/contents/{quote(_relative_path(path), safe='/')}",
                     params={"ref": ref})
    if not isinstance(result, dict) or result.get("type") != "file":
        raise ValueError("El path debe identificar un archivo regular.")
    if result.get("size", MAX_FILE_BYTES + 1) > MAX_FILE_BYTES or result.get("encoding") != "base64":
        raise ValueError("Se requiere un archivo de texto de hasta 100 KB.")
    return {"path": path, "ref": ref, "sha": result["sha"],
            "content": base64.b64decode(result["content"]).decode("utf-8")}


@tool
def read_repository_file(path: str, ref: str = "") -> dict:
    """Lee un archivo de GitHub y su SHA. Usar ese SHA al proponer la corrección."""
    return _repo_file(path, ref or _setting("GITHUB_BASE_BRANCH", "main"))


@tool
def create_fix_pr(incident_id: str, original_sha: str, content: str,
                  title: str, description: str, path: str = "") -> dict:
    """Propone el contenido del DAG o archivo IAM permitido en una draft PR.

    incident_id debe ser estable (dag_id/run_id/task_id). Reutiliza su rama y PR.
    Comprueba sintaxis Python. Terraform requiere revisión y terraform validate/plan externos.
    NO ejecuta código, valida permisos efectivos ni despliega.
    """
    dag_path = _setting("GITHUB_DAG_PATH", "dags/demo_pipeline.py")
    path = _relative_path(path or dag_path)
    allowed = {dag_path, os.environ.get("GITHUB_IAM_PATH", "")}
    if path not in allowed:
        raise ValueError("El archivo no está habilitado para correcciones.")
    if not incident_id.strip() or not title.strip() or not description.strip():
        raise ValueError("Se requieren incidente, título y descripción.")
    if not path.endswith((".py", ".tf")) or not content.strip() or len(content.encode()) > MAX_FILE_BYTES:
        raise ValueError("La corrección debe ser un archivo Python o Terraform de hasta 100 KB.")
    # El repo de la demo es público: usar referencias Terraform, no IDs de cuenta.
    if re.search(r"(?<!\d)\d{12}(?!\d)", "\n".join((content, title, description))):
        raise ValueError("La PR pública no puede incluir IDs de cuenta AWS. Usar referencias o placeholders.")
    if path.endswith(".py"):
        ast.parse(content)
    base = _setting("GITHUB_BASE_BRANCH", "main")
    branch = "agent-fix/" + hashlib.sha256(f"{incident_id}:{path}".encode()).hexdigest()[:20]
    owner = _setting("GITHUB_REPO").split("/", 1)[0]
    existing = _github("GET", "/pulls", params={"head": f"{owner}:{branch}",
                                               "base": base, "state": "all"})
    if existing:
        return {"url": existing[0]["html_url"], "state": existing[0]["state"], "reused": True}
    reference = _github("GET", f"/git/ref/heads/{quote(branch, safe='/')}", allow_missing=True)
    if reference is None:
        base_ref = _github("GET", f"/git/ref/heads/{quote(base, safe='/')}")
        current = _repo_file(path, base_ref["object"]["sha"])
        if current["sha"] != original_sha:
            raise ValueError("El archivo cambió en GitHub. Volver a leerlo antes de proponer el fix.")
        if current["content"] == content:
            raise ValueError("La propuesta no contiene cambios.")
        _github("POST", "/git/refs", json={"ref": f"refs/heads/{branch}",
                                          "sha": base_ref["object"]["sha"]})
    current = _repo_file(path, branch)
    if current["content"] != content:
        if current["sha"] != original_sha:
            raise ValueError("La rama del incidente ya contiene una corrección diferente.")
        _github("PUT", f"/contents/{quote(path, safe='/')}", json={
            "message": title, "content": base64.b64encode(content.encode()).decode(),
            "sha": current["sha"], "branch": branch,
        })
    result = _github("POST", "/pulls", json={"title": title, "body": description,
                                            "head": branch, "base": base, "draft": True})
    return {"url": result["html_url"], "state": result["state"], "reused": False}


@tool
def send_slack_message(text: str) -> dict:
    """Publica en el canal del webhook. No lee conversaciones ni devuelve un hilo."""
    if not text.strip() or len(text) > 4000:
        raise ValueError("El mensaje debe tener entre 1 y 4000 caracteres.")
    webhook = _secret("SLACK_SECRET_ID", "webhook_url")
    url = urlparse(webhook)
    if url.scheme != "https" or url.netloc != "hooks.slack.com" or not url.path.startswith("/services/"):
        raise ValueError("El secreto no contiene un webhook válido de Slack.")
    try:
        response = requests.post(webhook, json={"text": text, "unfurl_links": False},
                                 timeout=(5, 15), allow_redirects=False)
    except requests.RequestException:
        # Requests incluye la URL en sus errores: nunca devolverla al modelo/logs.
        raise RuntimeError("Slack no confirmó la entrega; verificar el canal antes de reintentar.") from None
    if response.status_code != 200 or response.text.strip() != "ok":
        raise RuntimeError(f"Slack no confirmó la entrega (HTTP {response.status_code}).")
    return {"sent": True}


@tool
def rerun_dag(dag_id: str, source_run_id: str) -> dict:
    """Crea una ejecución después de revisar y desplegar el fix.

    Requiere ENABLE_DAG_RERUN=true. No comprueba el despliegue.
    Usa un ID estable por incidente y rechaza recuperaciones de recuperaciones.
    """
    if os.environ.get("ENABLE_DAG_RERUN", "false").lower() != "true":
        raise ValueError("La reejecución está deshabilitada en el Runtime.")
    path = _run_path(dag_id, source_run_id)
    if source_run_id.startswith("agent_recovery__"):
        raise ValueError("No se permite encadenar ejecuciones de recuperación.")
    source = _airflow(path)
    if source["state"] != "failed":
        raise ValueError("La ejecución de origen debe haber terminado en failed.")
    recovery_id = "agent_recovery__" + hashlib.sha256(source_run_id.encode()).hexdigest()[:20]
    # Airflow rechaza un segundo POST con el mismo dag_run_id: no duplica ejecuciones.
    return _airflow(f"{_dag_path(dag_id)}/dagRuns", method="POST", Body={
        "dag_run_id": recovery_id, "logical_date": None, "conf": source.get("conf") or {},
    })


TOOLS = [get_dag_details, list_dag_runs, get_dag_run, list_task_instances,
         list_task_log_streams, read_task_logs, read_deployed_dag,
         read_repository_file, create_fix_pr, send_slack_message,
         inspect_mwaa_permissions, inspect_sales_file]


def get_tools() -> list:
    """Devuelve las tools para conectar con Agent(tools=get_tools())."""
    return TOOLS + ([rerun_dag] if os.environ.get("ENABLE_DAG_RERUN", "false").lower() == "true" else [])
