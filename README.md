# Agentic Airflow — POC

Un pipeline falla por permisos y un agente investiga el incidente, propone un fix
mediante una draft PR en GitHub y avisa por Slack. Airflow corre en Amazon MWAA;
el agente usa Strands y Claude Sonnet 4.6 en Amazon Bedrock AgentCore.
Consulta [AWS Knowledge MCP](https://awslabs.github.io/mcp/servers/aws-knowledge-mcp-server)
para respaldar el diagnóstico con documentación actualizada de AWS. Es un servicio
remoto: no requiere despliegue ni credenciales adicionales.

**Una POC con pocos pasos manuales:** `terraform apply` levanta el entorno y
`terraform destroy` lo elimina. Los secretos de GitHub y Slack se conservan para
reutilizarlos; la clave KMS queda programada para borrarse a los siete días.

## Arranque rápido

La idea es dedicar unos cinco minutos a los pasos de despliegue **una vez listos
los requisitos y las integraciones**. El aprovisionamiento de MWAA tarda más.

Necesitás Terraform 1.14 o superior (menor que 2.0), AWS CLI v2 autenticado con
permisos para crear la infraestructura, Docker con Buildx funcionando y acceso
al modelo Claude Sonnet 4.6 en Bedrock.

1. Cloná este repo o tu fork y revisá [infra/config.yaml](infra/config.yaml):
   región, zonas y repositorio donde el agente abrirá las PRs.
2. Creá y cargá una sola vez estos secretos en Secrets Manager, en la región
   configurada. Si ya existen, reutilizalos:

   | Nombre por defecto | Valor JSON |
   | --- | --- |
   | `nerdearla-agentic-airflow/github` | `{"token": "<token de GitHub>"}` |
   | `nerdearla-agentic-airflow/slack` | `{"webhook_url": "<webhook de Slack>"}` |

   La [guía de GitHub y Slack](infra/secrets-manager/README.md) explica cómo
   obtenerlos y cargarlos. No se usa `.env`.
3. Desde la raíz del repo:

   ```bash
   cd infra
   terraform init  # Sólo la primera vez o al cambiar módulos/providers
   terraform apply
   ```

Terraform construye y publica la imagen del agente, crea el Runtime, sube el DAG
y el CSV de ejemplo a S3 y configura las Variables de Airflow. No hace falta
publicar imágenes ni cargar Variables manualmente. Para actualizar código,
volvé a ejecutar `terraform apply`.

## Qué se levanta

| Servicio | Para qué se usa |
| --- | --- |
| **MWAA** | Ejecuta el DAG y envía el incidente al agente. |
| **AgentCore Runtime** | Aloja el agente, que usa Bedrock para razonar y sus tools para investigar y actuar. |
| **S3 y ECR** | Guardan el DAG, sus requisitos, el CSV de entrada y la imagen del agente. |
| **Secrets Manager** | Provee las credenciales de las integraciones y las Variables de Airflow. |
| **CloudWatch** | Reúne los logs de Airflow y del agente. |
| **IAM y KMS** | Controlan los permisos y el cifrado del entorno. |
| **VPC y NAT** | Dan conectividad a MWAA. AgentCore usa red `PUBLIC` con autenticación IAM. |

## Ejecutar la demo

Abrí la UI de MWAA (su dirección sale con `terraform output -raw mwaa_webserver_url`),
activá `demo_pipeline` y dispará una ejecución manual.

```text
S3KeySensor → GlueJobOperator → AthenaOperator
    │ falla por falta de s3:GetObject
    └─ BedrockInvokeAgentRuntimeOperator → AgentCore
                                             ├─ consulta Airflow, logs, S3 e IAM
                                             ├─ consulta documentación con AWS Knowledge MCP
                                             ├─ propone una draft PR en GitHub
                                             └─ notifica por Slack
```

El archivo existe, pero omitimos intencionalmente su permiso de lectura en el rol
de MWAA. El sensor falla con `403` y el operador de AgentCore envía el contexto
del incidente. El agente acepta la solicitud y continúa el triage en segundo plano;
**el DAG queda fallido**.

El resultado esperado es un diagnóstico, una draft PR con el permiso faltante y
un aviso en Slack. Una persona revisa y aplica el cambio: no hay merge ni
reejecución automática. **Glue y Athena son pasos ilustrativos:** no se crean
sus recursos ni se conceden sus permisos. Quedan bloqueados por la primera falla;
corregir S3 no convierte este ejemplo en un ETL completo.

## Limpiar

Desde `infra/`, con las mismas credenciales y conservando el state local:

```bash
terraform destroy
```

Al terminar sin errores, elimina el entorno administrado por Terraform, incluidos
MWAA, Runtime, NAT, buckets con sus objetos, imágenes y logs. **Conserva los dos
secretos de integración**, que pueden seguir generando cargos, y programa la
eliminación de la clave KMS a siete días. Las PRs y los mensajes publicados quedan
en GitHub y Slack. Podés levantar la POC nuevamente con `terraform apply`.

## Dónde mirar

- [DAG](dags/demo_pipeline.py): operadores y contexto del incidente.
- [Agente](airflow-agent/agent.py), [tools](airflow-agent/tools.py) y
  [configuración](airflow-agent/config.yaml): modelo, instrucciones y límites.
- [Infraestructura](infra/README.md): módulos por servicio y detalles operativos.

El flujo completo DAG → agente → PR → Slack todavía está pendiente de validación
end-to-end en AWS.
