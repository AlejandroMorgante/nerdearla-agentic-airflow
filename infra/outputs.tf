output "bucket_name" { value = module.s3.bucket_name }
output "repository_url" { value = module.ecr.repository_url }
output "secret_arns" { value = module.secrets_manager.secret_arns }
output "mwaa_environment_name" { value = module.mwaa.environment_name }
output "mwaa_webserver_url" { value = module.mwaa.webserver_url }
output "runtime_arn" { value = module.agentcore.runtime_arn }
output "endpoint_name" { value = module.agentcore.endpoint_name }
