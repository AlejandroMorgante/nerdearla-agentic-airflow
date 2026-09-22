output "environment_name" { value = aws_mwaa_environment.workshop.name }
output "environment_arn" { value = aws_mwaa_environment.workshop.arn }
output "webserver_url" { value = aws_mwaa_environment.workshop.webserver_url }
output "role_id" { value = aws_iam_role.mwaa.id }
output "task_log_arn" { value = aws_cloudwatch_log_group.mwaa["Task"].arn }
