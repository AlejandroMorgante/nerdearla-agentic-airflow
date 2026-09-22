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
  s3/               # Artefactos, bucket de entrada y CSV de ejemplo
  ecr/              # Repositorio de imágenes
  secrets-manager/  # Referencias a credenciales persistentes y Variables de Airflow
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
Terraform se ejecuta directamente e invoca Docker para construir la imagen del agente.

Sólo MWAA usa la VPC del workshop: dos subnets privadas, dos públicas y un NAT.
AgentCore usa red `PUBLIC` administrada por AWS, sin subnets ni security group
propios. Las invocaciones siguen requiriendo IAM; `PUBLIC` es el modo de red,
no acceso anónimo. El agente llama a las APIs de MWAA, CloudWatch, S3 y Secrets
Manager, y tiene salida HTTPS para GitHub y Slack.

La UI de MWAA es pública con autenticación AWS. El agente tiene acceso Viewer
a Airflow y la reejecución está deshabilitada. Los logs de MWAA y AgentCore están
cifrados con KMS y se conservan siete días. El resultado del triage asíncrono
queda en `/aws/bedrock-agentcore/runtimes/<runtime-id>-workshop`; este grupo
también lo administra Terraform. Un NAT simplifica la POC, sin alta
disponibilidad. El plan y el apply usan la cuenta del perfil activo del AWS CLI.

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
para actualizar o eliminar los recursos. Sus backups históricos locales se conservan
en `.state-backups/`. Los planes guardados son temporales y no se necesitan
para ejecutar `terraform apply`. Para este workshop se usa state local;
si varias personas despliegan, configurar antes un backend remoto con locking.
Los valores de GitHub y Slack nunca se cargan mediante Terraform ni entran al state.

## Desplegar

Requisitos locales: Terraform, AWS CLI v2 autenticado y Docker con Buildx funcionando.
Si usás un perfil distinto de `default`, seleccionarlo con `AWS_PROFILE` en la
terminal. El provider y el build de Docker usan esas mismas credenciales.

Una sola vez, crear y cargar los secretos `${project}/github` y `${project}/slack`
en Secrets Manager, en la región de `config.yaml`. Seguir la [guía de integraciones](secrets-manager/README.md).
Son persistentes: Terraform sólo consulta sus ARNs, nunca lee sus valores ni los
borra. Si todavía no existen, el plan informa que faltan.

Revisar `config.yaml`, especialmente región, zonas y repositorio de GitHub.
Desde `infra/`, después de `terraform init` en un checkout nuevo:

```bash
terraform apply
```

El despliegue crea ECR, construye y publica la imagen ARM64 y crea AgentCore después
del push. El tag se calcula a partir del código, configuración, Dockerfile y
requirements del agente. No hay que editar tags, crear tfvars ni hacer dos applies.
Un cambio en esos archivos reconstruye la imagen; un cambio sólo en el DAG no.
El build corre localmente mediante `ecr/build.sh`, invocado por Terraform.
Si el push ya terminó en un intento anterior, el script reutiliza ese tag inmutable.

Terraform crea los buckets de artefactos y entrada, carga el CSV, el DAG y los
requisitos de Airflow. Glue y Athena sólo aparecen como operadores en el DAG;
no se crean jobs, catálogos, workgroups ni buckets de resultados.
Un cambio del DAG actualiza el mismo objeto en S3 y MWAA lo sincroniza.

Las Variables `mwaa_environment_name`, `agentcore_runtime_arn` y
`sales_input_bucket` se crean automáticamente
en Secrets Manager bajo `${project}/airflow/variables/`. Airflow las consulta a través
del backend configurado; no hay que cargarlas en la UI y no aparecen en su listado.
Estas referencias de infraestructura sí entran al state y se eliminan con el entorno.

Al finalizar, comprobar MWAA `AVAILABLE`, Runtime y endpoint `READY`, y ejecutar
manualmente el DAG para probar el incidente. El procesamiento se bloquea por los
permisos omitidos intencionalmente; un apply exitoso no equivale a una prueba end-to-end.
El operador invoca el endpoint `workshop` y el agente continúa el triage en segundo plano.

[Backend Secrets Manager para MWAA](https://docs.aws.amazon.com/mwaa/latest/userguide/connections-secrets-manager.html)

## Incidente de permisos

El sensor consulta `incoming/sales.csv`, cargado por Terraform. El rol MWAA
sólo puede listar el bucket de entrada: falta `s3:GetObject` para ese objeto y
faltan los permisos Glue para el job. La primera tarea falla por acceso y bloquea
el procesamiento. No ejecutar manualmente la tarea Glue saltándose dependencias.

La PR del agente puede modificar `mwaa/sales-access.tf`. Ese módulo recibe
`sales_input_arn` para proponer un permiso sobre el objeto concreto.
El agente puede leer las políticas inline y simular acciones del rol de MWAA;
no puede modificar IAM ni desplegar. Su acceso de lectura al archivo permite
comprobar existencia, pero no implica que MWAA tenga ese mismo acceso.

Glue y Athena conservan nombres de ejemplo en el DAG. No se crean sus recursos
ni se conceden sus permisos. Si se llega a esos pasos, pueden fallar por acceso
o por recursos inexistentes. La rama del agente está conectada a la falla inicial
del sensor; corregirla no significa que el pipeline completo vaya a funcionar.

## Limpieza

Esta infraestructura es descartable. Desde `infra/`, con el mismo perfil y state:

```bash
terraform destroy
```

El comando solicita confirmación y elimina los recursos administrados por este
state: MWAA, AgentCore, red (incluyendo NAT y EIP), roles, logs, bucket y repositorio.
S3 usa `force_destroy` para borrar objetos y versiones; ECR usa `force_delete` para
borrar las imágenes. Las Variables de Airflow se eliminan sin período de recuperación;
los secretos de GitHub y Slack quedan intactos y se reutilizan en el siguiente apply.
La clave KMS queda pendiente de eliminación durante siete días, el mínimo de AWS;
no desaparece inmediatamente. El borrado de los servicios puede ser asíncrono.

Conservar el state y revisar que `destroy` termine sin errores. Si los recursos ya
existían antes de incorporar estos flags, ejecutar primero `terraform apply` para
registrarlos en el state. El despliegue anterior se eliminó por completo, conservando
los secretos y el período de eliminación de KMS. AgentCore usa ahora modo PUBLIC.
No borra el repositorio GitHub, las PRs, mensajes o webhooks de Slack ni los tokens
emitidos en GitHub. Tampoco administra recursos creados fuera de este state,
como roles vinculados a servicios que AWS pueda crear automáticamente.

Para instalaciones anteriores, el bloque `removed` de `secrets-manager/main.tf`
retira del state los dos secretos de integración sin eliminarlos. Aplicar esa migración
antes de destruir y revisar el plan: debe indicar que dejan de administrarse, nunca
que se destruyen. Las instalaciones nuevas sólo consultan los secretos existentes.

Para volver a desplegar, con las credenciales vigentes y Docker funcionando, alcanza con
`terraform apply`: reconstruye/publica la imagen y reutiliza los secretos conservados.

## Referencias

- [Provider AWS: AgentCore Runtime](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/bedrockagentcore_agent_runtime)
- [Provider AWS: entrega de logs](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudwatch_log_delivery_source)
- [Versiones de MWAA](https://docs.aws.amazon.com/mwaa/latest/userguide/airflow-versions.html)
- [Constraints de Airflow 3.3.1](https://raw.githubusercontent.com/apache/airflow/constraints-3.3.1/constraints-3.12.txt)

- [Eliminación de claves KMS](https://docs.aws.amazon.com/kms/latest/developerguide/deleting-keys.html)
