# Configurar Slack y GitHub

Cargar los valores directamente en AWS Secrets Manager, región `us-east-1`,
en los secretos persistentes `${project}/github` y `${project}/slack`.
Para el nombre de proyecto por defecto son `nerdearla-agentic-airflow/github` y
`nerdearla-agentic-airflow/slack`. No guardarlos en Git, `.env` ni en el chat.

Si no existen todavía, en Secrets Manager elegir **Store a new secret → Other type
of secret**, cargar el JSON correspondiente y guardar con el nombre indicado, usando
la clave de cifrado predeterminada de Secrets Manager. Crear ambos antes del primer
`terraform apply`. Si ya están cargados, no hay nada que repetir: el destroy de la POC
los conserva. Terraform sólo lee metadatos y no administra sus valores.

## Slack

1. Abrir [Slack Apps](https://api.slack.com/apps).
2. Seleccionar **Create New App → Blank app → Continue**.
3. Nombrarla `Nerdearla Airflow Agent` y elegir el workspace.
4. En **Incoming Webhooks**, activar **Activate Incoming Webhooks**.
5. Seleccionar **Add New Webhook to Workspace**, elegir el canal de la demo
   y autorizar. El workspace puede requerir aprobación de un administrador.
6. Copiar la URL generada y guardarla como valor JSON del secreto
   `nerdearla-agentic-airflow/slack`:

```json
{"webhook_url": "<URL generada por Slack>"}
```

Usamos el webhook de la app para enviar notificaciones al canal elegido.
No necesitamos un token de bot ni permisos para leer conversaciones.

[Documentación oficial](https://docs.slack.dev/messaging/sending-messages-using-incoming-webhooks/)

## GitHub

1. Abrir [New fine-grained personal access token](https://github.com/settings/personal-access-tokens/new).
2. Asignar un nombre y una expiración posterior al workshop.
3. Elegir como **Resource owner** al propietario del repo.
4. En **Repository access**, seleccionar **Only select repositories** y
   `nerdearla-agentic-airflow`.
5. En **Repository permissions**, otorgar **Contents: Read and write** y
   **Pull requests: Read and write**. Metadata queda con lectura.
6. Generar el token y guardarlo como valor JSON del secreto
   `nerdearla-agentic-airflow/github`:

```json
{"token": "<token generado por GitHub>"}
```

Estos permisos permiten leer archivos, crear una rama, escribir el fix y abrir
la draft PR. El agente no tiene una tool para mergear PRs.

[Documentación oficial](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)

## Cargar los valores y verificar

En la consola de Secrets Manager, buscar cada secreto por su nombre y guardar
su valor en formato JSON con la clave indicada. Usar los secretos existentes;
no crear otros con nombres diferentes. Para futuras rotaciones, actualizar el
valor del mismo secreto: las tools lo consultan cada vez que lo necesitan.

Antes de disparar una investigación, verificar que ambos tengan una versión
actual. Eso comprueba que se cargó un valor; la validez del token, el acceso al
repositorio y la entrega a Slack se comprueban al probar las integraciones.
