# Agentic Airflow — workshop

Demo de un pipeline en Amazon MWAA que, al fallar, invoca un agente en
Amazon Bedrock AgentCore para investigar, proponer una corrección y comunicarla.

## Estructura

```text
airflow-agent/
  agent.py          # Entrada HTTP de AgentCore
  config.yaml       # Modelo, instrucciones y límites
  tools.py          # Herramientas de investigación y acción
  container/
    Dockerfile
    requirements.txt
dags/
  demo_pipeline.py  # ETL con una falla intencional
infra/
  agentcore/        # Runtime, endpoint, permisos y logs
  mwaa/             # Airflow, permisos, logs y requisitos
  vpc/              # Red del workshop
  s3/               # DAGs y artefactos
  ecr/              # Imágenes del agente
  secrets-manager/  # Credenciales de integraciones
  kms/              # Cifrado
  main.tf           # Conecta los módulos por servicio
  README.md         # Guía de despliegue
README.md
```

## Estado actual

El agente valida el incidente e inicia una instancia nueva de Strands con
`get_tools()` por invocación. Usa Claude Sonnet 4.6 en Bedrock. El modelo respondió
correctamente a una prueba mínima con credenciales locales de desarrollo en `us-east-1`.
Ese profile no se copia a la imagen: AgentCore usará su propio rol IAM.
No se necesitan credenciales para importar el módulo ni ejecutar tests.

El DAG usa la interfaz de Airflow 3 y falla en `transform` porque intenta leer
`total` en registros que contienen `amount`. El resultado esperado después de
corregirlo es `{"revenue": 150}`. Todavía no invoca AgentCore.

## Construir el contenedor

Desde la raíz del repositorio, con Docker y buildx disponibles:

```bash
docker buildx build --platform linux/arm64 --load \
  -f airflow-agent/container/Dockerfile \
  -t nerdearla-airflow-agent:dev ./airflow-agent
```

Usamos el protocolo HTTP del SDK de AgentCore, con `/ping` y `/invocations`
en el puerto 8080. La imagen para AgentCore se construye para ARM64.
No se requiere `.venv` ni instalar paquetes Python en la máquina anfitriona.
El contexto de build sigue siendo `airflow-agent/`.

## Herramientas y configuración

`airflow-agent/config.yaml` contiene el modelo, la región por defecto, las
instrucciones y los límites. Se incluye en la imagen; sus cambios requieren
reconstruir y desplegar. En desarrollo se puede montar ese archivo como volumen.
`AWS_REGION` del Runtime tiene prioridad sobre la región del YAML.

Los límites iniciales son 12 turnos del modelo, 20 llamadas a tools, 4096 tokens
de salida por respuesta, 80000 tokens acumulados y 300 segundos. Strands verifica
turnos y tokens entre iteraciones: el presupuesto de tokens puede superarse por
una respuesta. El plazo de tiempo se comprueba antes de iniciar cada modelo/tool;
no interrumpe una petición ya en curso. Los clientes tienen sus propios timeouts.
Las tools se ejecutan secuencialmente y Slack se intenta una vez por invocación.

Las tools consultan el DAG, sus ejecuciones, tareas y logs en MWAA/CloudWatch;
leen código en GitHub y S3; crean una draft PR y publican un mensaje en Slack.
Se conectan a Strands con `Agent(tools=get_tools(), ...)`.

La infraestructura pasará estas variables **no secretas** al Runtime:

| Variable | Valor o propósito |
| --- | --- |
| `AWS_REGION` | Región de los recursos AWS |
| `MWAA_ENVIRONMENT_NAME` | Nombre del entorno MWAA |
| `AIRFLOW_DAG_ID` | DAG permitido; default `demo_pipeline` |
| `GITHUB_REPO` | `owner/repo` |
| `GITHUB_BASE_BRANCH` | Rama base; default `main` |
| `GITHUB_DAG_PATH` | Único archivo modificable; default `dags/demo_pipeline.py` |
| `GITHUB_SECRET_ID` | Nombre o ARN del secreto de GitHub |
| `SLACK_SECRET_ID` | Nombre o ARN del secreto de Slack |
| `ENABLE_DAG_RERUN` | Default `false`; habilitar sólo para la fase de recuperación |

Crear más adelante los secretos como JSON en Secrets Manager:

```json
{"token": "<token de GitHub>"}
```

```json
{"webhook_url": "<incoming webhook de Slack>"}
```

Los secretos se consultan al usar cada integración. El token de GitHub necesita
Contents y Pull requests con escritura sobre el repo. El webhook elige el canal.
No se usa `.env`. Los valores reales no deben entrar en Git ni en la imagen.

La PR modifica un solo archivo y verifica su SHA y sintaxis Python. No ejecuta
el código propuesto ni demuestra que el fix sea correcto. Una rama estable por
incidente permite continuar una operación parcial y reutilizar una PR existente.
Una carrera entre invocaciones puede producir un conflicto: volver a consultar
antes de reintentar. Slack no garantiza deduplicación; un timeout puede ocurrir
después de enviar el mensaje, por lo que no se reintenta automáticamente.

`rerun_dag` está deshabilitada por defecto. Una vez revisado y desplegado el fix,
se puede habilitar: conserva `conf`, exige una ejecución de origen fallida y usa
un ID estable. Un segundo intento recibe un conflicto de Airflow; consultar ese
ID con `get_dag_run`. No permite encadenar ejecuciones de recuperación. La tool
no verifica merge ni despliegue; esa coordinación queda pendiente.

Los logs usan el formato estándar `dag_id=.../run_id=.../task_id=.../` de Airflow.
Se descubren streams antes de leerlos; una plantilla de logs personalizada
requiere adaptar ese prefijo. Los logs deben estar habilitados en MWAA. Las
lecturas son limitadas y reportan truncamiento. S3 devuelve la versión actual
del archivo, no garantiza el código histórico de una ejecución.

El rol del Runtime necesitará `airflow:GetEnvironment`, `airflow:InvokeRestApi`,
`logs:DescribeLogStreams`, `logs:GetLogEvents`, `s3:GetObject` y
`secretsmanager:GetSecretValue`, limitados a los recursos del workshop. Agregar
`kms:Decrypt` si se usan claves propias. Un webserver privado requiere acceso
de red desde el Runtime; GitHub y Slack requieren salida HTTPS.
Para el modelo se necesita `bedrock:InvokeModel` tanto sobre el perfil de inferencia
`us.anthropic.claude-sonnet-4-6` como sobre los modelos de sus regiones de destino.
Que funcione con credenciales locales no confirma todavía los permisos del futuro rol.

## Probar con Docker

Después de construir `nerdearla-airflow-agent:dev`, desde la raíz del repo:

```bash
docker run --rm --network none \
  -v "$PWD/tests:/tests:ro" \
  nerdearla-airflow-agent:dev python -m unittest discover -s /tests -v
```

Los tests usan respuestas simuladas y no envían mensajes, crean PRs ni invocan AWS.
Para probar el contrato HTTP sin configurar integraciones:

```bash
docker run --rm -p 127.0.0.1:8080:8080 nerdearla-airflow-agent:dev
```

En otra terminal, consultar `http://localhost:8080/ping` o enviar el evento de
entrada con POST a `http://localhost:8080/invocations`. Sin configuración del
entorno devuelve `configuration_error`; un payload inválido devuelve `invalid_input`.
Una invocación con configuración y credenciales reales puede crear PRs y enviar
Slack. Las pruebas automatizadas usan un modelo y servicios simulados.

## Evento de entrada

Este objeto se pasa como `payload` al `BedrockInvokeAgentRuntimeOperator`.
`task_id` identifica la tarea que falló, no la tarea que invoca al agente.
La validación rechaza campos adicionales y entornos o DAGs fuera del alcance.

```json
{
  "environment_name": "workshop-mwaa",
  "dag_id": "demo_pipeline",
  "run_id": "<run_id de la ejecución fallida>",
  "task_id": "transform"
}
```

## Resultado de la investigación

El agente devuelve un objeto JSON. Ejemplo ilustrativo (no es un incidente real):

```json
{
  "status": "completed",
  "incident": {
    "environment_name": "workshop-mwaa",
    "dag_id": "demo_pipeline",
    "run_id": "manual__example",
    "task_id": "transform"
  },
  "diagnosis": "La tarea lee total, pero los registros contienen amount. PR pendiente de revisión.",
  "actions": [
    {"tool": "get_dag_run", "status": "success"},
    {"tool": "create_fix_pr", "status": "success"},
    {"tool": "send_slack_message", "status": "success"}
  ],
  "pull_request_url": "https://github.com/owner/repo/pull/123",
  "slack_status": "sent",
  "recovery_run_id": null,
  "tool_calls": 3,
  "stop_reason": "end_turn",
  "limit_reason": null,
  "usage": {"inputTokens": 2000, "outputTokens": 500, "totalTokens": 2500}
}
```

El diagnóstico es texto del modelo. `actions`, `pull_request_url`, `slack_status`
y `recovery_run_id` se derivan de las tools, no de afirmaciones del modelo.
Los errores conservan las acciones ya confirmadas. `completed` significa que
terminó la investigación, no que el pipeline se haya recuperado. Otros estados:
`needs_attention`, `limited`, `incomplete`, `error`, `invalid_input` y
`configuration_error`. `unconfirmed` en Slack requiere comprobar la entrega.

El operador devuelve este JSON dentro de la clave `response`, junto con metadatos
del Runtime. Con XCom habilitado, una tarea posterior puede leer
`ti.xcom_pull(task_ids="investigate_failure")["response"]`. Esa tarea debe revisar
`status`: una respuesta HTTP exitosa no convierte un diagnóstico incompleto en
éxito ni corrige el estado de la tarea original. Ver el
[contrato del operador](https://airflow.apache.org/docs/apache-airflow-providers-amazon/stable/operators/bedrock.html).
El cableado del DAG y el tratamiento de esos estados quedan para la siguiente etapa.

## Próximos pasos

1. Desplegar la infraestructura definida en [infra/README.md](infra/README.md) y completar los secretos.
2. Conectar el manejo de fallos del DAG al operador de AgentCore, ajustando su
   `read_timeout` por encima del presupuesto del agente y el tiempo de peticiones en curso.
3. Completar el despliegue y comprobar la recuperación después del merge.

Pendiente validar versión de MWAA y provider Amazon, IAM, conectividad y secretos.
No se ha desplegado infraestructura ni probado el flujo de punta a punta.
