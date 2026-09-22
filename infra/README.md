# Infraestructura del workshop

Terraform organizado en módulos por servicio. Requiere Terraform 1.14 o superior
(menor que 2.0) y credenciales del AWS CLI.
`main.tf` conecta los módulos en un único despliegue y state; `config.yaml`
contiene los parámetros de la demo. La cuenta se obtiene automáticamente de
las credenciales del AWS CLI; no se guarda ningún perfil ni ID de cuenta en el repo.

```text
infra/
  agentcore/        # Runtime, endpoint, IAM y logs del agente
  mwaa/             # Airflow, IAM, logs y requirements.txt
  vpc/              # Red, subnets y NAT
  s3/               # Bucket, DAG y requisitos versionados
  ecr/              # Repositorio de imágenes
  secrets-manager/  # Secretos vacíos de GitHub y Slack
  kms/              # Clave de cifrado compartida
  main.tf           # Provider y conexión entre módulos
  outputs.tf
  config.yaml
  tests/
  README.md
```

Cada módulo contiene `main.tf`, `variables.tf` y `outputs.tf`. Se ejecuta
Terraform desde `infra/`, no dentro de cada servicio.
Los roles IAM y los logs pertenecen al módulo del servicio que los usa.
Docker se usa para construir la imagen del agente; Terraform se ejecuta directamente.

MWAA y AgentCore usan subnets privadas con salida por NAT. La UI de MWAA es
pública con autenticación AWS; AgentCore requiere IAM. El agente tiene acceso
Viewer a Airflow y la reejecución está deshabilitada. Los logs están cifrados con
KMS y se conservan siete días. Un solo NAT simplifica la demo, sin alta disponibilidad.

Verificar las zonas soportadas por AgentCore en la cuenta donde se desplegará;
los nombres de Availability Zones pueden corresponder a IDs diferentes entre cuentas.
El plan y el apply operan sobre la cuenta del perfil seleccionado en el AWS CLI.

## Módulos y despliegues independientes

Esta configuración usa módulos hijos bajo una raíz y comparte un único state.
Un `apply` normal revisa el conjunto y aplica únicamente los cambios necesarios;
no recrea todos los servicios en cada ejecución.

Es posible seleccionar un módulo desde la raíz con `plan -target=module.ecr`.
Terraform incluye también las dependencias necesarias, pero puede omitir otros
cambios y consumidores. HashiCorp reserva `-target` para situaciones excepcionales;
no es el flujo habitual del workshop. Después de usarlo, revisar un plan completo.

Para aplicar servicios de forma independiente de manera habitual, se necesitan
configuraciones raíz y states separados, con un contrato para compartir outputs
(por ejemplo, un backend remoto o consultas a recursos existentes). Las carpetas
actuales organizan código; no son stacks autónomos ni deben aplicarse por separado.
Ver [módulos](https://developer.hashicorp.com/terraform/language/modules) y
[resource targeting](https://developer.hashicorp.com/terraform/tutorials/state/resource-targeting).

## Empezar

Con el AWS CLI autenticado, desde la raíz del repo:

```bash
cd infra
terraform init
terraform plan
```

`init` se ejecuta la primera vez o cuando cambian los módulos o providers.
Los comandos restantes de esta guía se ejecutan dentro de `infra/`.
Si usás un perfil distinto de `default`, seleccionarlo previamente en la terminal:
`export AWS_PROFILE="mi-perfil-local"`.

Para validar y ejecutar las pruebas:

```bash
terraform fmt -check -recursive
terraform validate
terraform test
```

`init` descarga el provider y genera `.terraform/`. El archivo
`.terraform.lock.hcl` fija su versión y checksums y se guarda en Git.
`validate` y los tests con provider simulado se ejecutan sin red ni credenciales.

Terraform usa la cadena habitual de credenciales de AWS, incluido `AWS_PROFILE`
o el perfil `default`. El state queda en `infra/terraform.tfstate`, ignorado por Git: conservarlo
para actualizar o eliminar los recursos. Para este workshop se usa state local;
si varias personas despliegan, configurar antes un backend remoto con locking.
Los valores de GitHub y Slack nunca se cargan mediante Terraform ni entran al state.

## Desplegar

Todavía no se desplegó infraestructura. Los `apply` crean recursos facturables,
incluyendo MWAA y NAT mientras estén activos.

1. Tener el AWS CLI autenticado y revisar los parámetros de `infra/config.yaml`:
región, zonas y `github_repo` (este repositorio por defecto). El repo de GitHub debe contener el DAG en `main`.
No hace falta crear configuración local adicional. Si usás un perfil distinto de
`default`, seleccionarlo con `AWS_PROFILE` en la terminal.

2. Crear la infraestructura inicial. Sin `agent_image_tag`, se crean ECR, MWAA y
sus dependencias; el Runtime queda pendiente hasta publicar la imagen:

```bash
terraform plan -out=workshop.tfplan
terraform apply workshop.tfplan
```

Terraform sube el DAG y los requisitos a S3 y pasa el VersionId a MWAA.
Un cambio local en esos archivos se publica con el próximo `apply`.

3. Construir y publicar la imagen ARM64. Usar un tag nuevo en cada actualización
y la misma región que en `config.yaml` (el ejemplo usa `us-east-1`):

```bash
AGENT_REPOSITORY="$(terraform output -raw repository_url)"
AGENT_TAG=v1
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin "${AGENT_REPOSITORY%%/*}"
docker buildx build --platform linux/arm64 --provenance=false --push \
  -f ../airflow-agent/container/Dockerfile \
  -t "$AGENT_REPOSITORY:$AGENT_TAG" ../airflow-agent
```

4. Copiar `infra/terraform.tfvars.example` a `infra/terraform.tfvars` y dejar
`agent_image_tag = "v1"` (o el tag publicado). Mantener ese archivo para los
siguientes planes: quitar el tag vuelve a deshabilitar el Runtime y propone
eliminarlo. El archivo contiene configuración, nunca tokens.

```bash
cp terraform.tfvars.example terraform.tfvars
terraform plan -out=workshop.tfplan
terraform apply workshop.tfplan
terraform output
```

5. Seguir el [paso a paso de Slack y GitHub](integrations.md) y cargar los valores
de los secretos desde la consola de Secrets Manager:

| Secreto | Contenido JSON |
| --- | --- |
| `nerdearla-agentic-airflow/github` | `{"token": "..."}` |
| `nerdearla-agentic-airflow/slack` | `{"webhook_url": "..."}` |

El token de GitHub necesita Contents y Pull requests con escritura en este repo.
El Runtime puede crearse con secretos vacíos; esas tools funcionarán después de
completarlos. Para Slack se usa un Incoming Webhook.

El output `runtime_arn` y el endpoint `workshop` se usarán al conectar el
`BedrockInvokeAgentRuntimeOperator`, con
`invoke_agent_runtime_kwargs={"qualifier": "workshop"}`.
El DAG todavía no tiene cableado el manejo de fallos.

Antes de la demo, comprobar MWAA `AVAILABLE`, Runtime y endpoint `READY`, la
instalación de los requisitos y una investigación completa. La validación local
y el plan no comprueban permisos efectivos, conectividad ni que la imagen arranque.

## Limpieza

Esta infraestructura es descartable. Desde `infra/`, con el mismo perfil y state:

```bash
terraform destroy
```

El comando solicita confirmación y elimina los recursos administrados por este
state: MWAA, AgentCore, red (incluyendo NAT y EIP), roles, logs, bucket y repositorio.
S3 usa `force_destroy` para borrar objetos y versiones; ECR usa `force_delete` para
borrar las imágenes. Los secretos se eliminan sin período de recuperación.
La clave KMS queda pendiente de eliminación durante siete días, el mínimo de AWS;
no desaparece inmediatamente. El borrado de los servicios puede ser asíncrono.

Conservar el state y revisar que `destroy` termine sin errores. Si los recursos ya
existían antes de incorporar estos flags, ejecutar primero `terraform apply` para
registrarlos en el state. No se ha probado todavía un ciclo real de apply/destroy.
No borra el repositorio GitHub, las PRs, mensajes o webhooks de Slack ni los tokens
emitidos en GitHub. Tampoco administra recursos creados fuera de este state,
como roles vinculados a servicios que AWS pueda crear automáticamente.

## Referencias

- [Provider AWS: AgentCore Runtime](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/bedrockagentcore_agent_runtime)
- [Provider AWS: entrega de logs](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudwatch_log_delivery_source)
- [Versiones de MWAA](https://docs.aws.amazon.com/mwaa/latest/userguide/airflow-versions.html)
- [Constraints de Airflow 3.3.1](https://raw.githubusercontent.com/apache/airflow/constraints-3.3.1/constraints-3.12.txt)

- [Eliminación de claves KMS](https://docs.aws.amazon.com/kms/latest/developerguide/deleting-keys.html)
