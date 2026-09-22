output "runtime_arn" { value = one(aws_bedrockagentcore_agent_runtime.agent[*].agent_runtime_arn) }
output "endpoint_name" { value = one(aws_bedrockagentcore_agent_runtime_endpoint.workshop[*].name) }
