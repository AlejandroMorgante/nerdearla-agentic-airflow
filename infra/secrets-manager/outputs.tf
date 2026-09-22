output "secret_arns" { value = { for name, secret in data.aws_secretsmanager_secret.integration : name => secret.arn } }
