resource "aws_secretsmanager_secret" "integration" {
  for_each                = toset(["github", "slack"])
  name                    = "${local.project}/${each.key}"
  recovery_window_in_days = 0
}
