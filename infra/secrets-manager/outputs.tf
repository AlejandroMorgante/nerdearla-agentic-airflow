output "secret_arns" { value = { for name, secret in aws_secretsmanager_secret.integration : name => secret.arn } }
