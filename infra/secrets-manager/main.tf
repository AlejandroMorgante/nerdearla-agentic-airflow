# Credenciales persistentes: sólo consultamos metadatos, nunca sus valores.
# Deben existir antes del primer apply; sobreviven al destroy del workshop.
data "aws_secretsmanager_secret" "integration" {
  for_each = toset(["github", "slack"])
  name     = "${local.project}/${each.key}"
}

# Migración de instalaciones previas: dejar de administrarlos SIN borrarlos.
removed {
  from = aws_secretsmanager_secret.integration
  lifecycle { destroy = false }
}

# Airflow las consulta por nombre mediante SecretsManagerBackend.
resource "aws_secretsmanager_secret" "airflow_variable" {
  for_each                = var.airflow_variables
  name                    = "${local.project}/airflow/variables/${each.key}"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "airflow_variable" {
  for_each      = var.airflow_variables
  secret_id     = aws_secretsmanager_secret.airflow_variable[each.key].id
  secret_string = each.value
}
