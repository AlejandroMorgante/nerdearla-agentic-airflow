resource "aws_iam_role" "agent" {
  name = "${local.project}-agent"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "bedrock-agentcore.amazonaws.com" }
    Condition = {
      StringEquals = { "aws:SourceAccount" = local.config.account }
      ArnLike      = { "aws:SourceArn" = "arn:aws:bedrock-agentcore:${local.config.region}:${local.config.account}:runtime/${local.config.runtime_name}-*" }
    }
  }] })
}

resource "aws_iam_role_policy" "agent" {
  role = aws_iam_role.agent.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = "ecr:GetAuthorizationToken", Resource = "*" },
    { Effect = "Allow", Action = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"], Resource = var.repository_arn },
    { Effect = "Allow", Action = "secretsmanager:GetSecretValue", Resource = values(var.secret_arns) },
    { Effect = "Allow", Action = "s3:GetObject", Resource = "${var.bucket_arn}/dags/*" },
    { Effect = "Allow", Action = "airflow:GetEnvironment", Resource = var.mwaa_arn },
    { Effect = "Allow", Action = "airflow:InvokeRestApi", Resource = "arn:aws:airflow:${local.config.region}:${local.config.account}:role/${local.project}/Viewer" },
    { Effect = "Allow", Action = ["logs:DescribeLogStreams", "logs:GetLogEvents"], Resource = "${var.task_log_arn}:*" },
    { Effect = "Allow", Action = "bedrock:InvokeModel", Resource = [
      "arn:aws:bedrock:${local.config.region}:${local.config.account}:inference-profile/${var.model_id}",
      "arn:aws:bedrock:*::foundation-model/${trimprefix(var.model_id, "us.")}"
    ] },
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"], Resource = "${aws_cloudwatch_log_group.agent.arn}:*" },
    { Effect = "Allow", Action = "logs:DescribeLogGroups", Resource = "*" },
    { Effect = "Allow", Action = "cloudwatch:PutMetricData", Resource = "*", Condition = { StringEquals = { "cloudwatch:namespace" = "bedrock-agentcore" } } },
    { Effect = "Allow", Action = ["xray:PutTraceSegments", "xray:PutTelemetryRecords", "xray:GetSamplingRules", "xray:GetSamplingTargets"], Resource = "*" },
    { Effect = "Allow", Action = "bedrock-agentcore:GetWorkloadAccessToken", Resource = [
      "arn:aws:bedrock-agentcore:${local.config.region}:${local.config.account}:workload-identity-directory/default",
      "arn:aws:bedrock-agentcore:${local.config.region}:${local.config.account}:workload-identity-directory/default/workload-identity/${local.config.runtime_name}-*"
    ] }
  ] })
  lifecycle {
    precondition {
      condition     = startswith(var.model_id, "us.anthropic.")
      error_message = "Revisar IAM si se cambia la familia o geografía del modelo."
    }
  }
}

# Sin authorizer_configuration, AgentCore usa autenticación AWS IAM.

resource "aws_bedrockagentcore_agent_runtime" "agent" {
  count              = local.agent_count
  agent_runtime_name = local.config.runtime_name
  role_arn           = aws_iam_role.agent.arn
  agent_runtime_artifact {
    container_configuration {
      container_uri = "${var.repository_url}:${var.agent_image_tag}"
    }
  }
  network_configuration {
    network_mode = "VPC"
    network_mode_config {
      security_groups = [aws_security_group.agent.id]
      subnets         = var.subnet_ids
    }
  }
  protocol_configuration { server_protocol = "HTTP" }
  environment_variables = {
    MWAA_ENVIRONMENT_NAME = local.project
    AIRFLOW_DAG_ID        = local.config.dag_id
    GITHUB_REPO           = local.config.github_repo
    GITHUB_BASE_BRANCH    = local.config.github_base_branch
    GITHUB_DAG_PATH       = local.config.github_dag_path
    GITHUB_SECRET_ID      = var.secret_arns["github"]
    SLACK_SECRET_ID       = var.secret_arns["slack"]
    ENABLE_DAG_RERUN      = "false"
  }
  depends_on = [aws_iam_role_policy.agent]
}

resource "aws_bedrockagentcore_agent_runtime_endpoint" "workshop" {
  count                 = local.agent_count
  name                  = "workshop"
  agent_runtime_id      = aws_bedrockagentcore_agent_runtime.agent[0].agent_runtime_id
  agent_runtime_version = aws_bedrockagentcore_agent_runtime.agent[0].agent_runtime_version
}

resource "aws_iam_role_policy" "mwaa_invoke_agent" {
  count = local.agent_count
  role  = var.mwaa_role_id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Action = "bedrock-agentcore:InvokeAgentRuntime"
    Resource = [aws_bedrockagentcore_agent_runtime.agent[0].agent_runtime_arn,
    aws_bedrockagentcore_agent_runtime_endpoint.workshop[0].agent_runtime_endpoint_arn]
  }] })
}

resource "aws_cloudwatch_log_group" "agent" {
  name              = "/aws/bedrock-agentcore/${local.project}"
  retention_in_days = 7
  kms_key_id        = var.kms_key_arn
}

resource "aws_cloudwatch_log_delivery_source" "agent" {
  count        = local.agent_count
  name         = "${local.project}-agent"
  log_type     = "APPLICATION_LOGS"
  resource_arn = aws_bedrockagentcore_agent_runtime.agent[0].agent_runtime_arn
}

resource "aws_cloudwatch_log_delivery_destination" "agent" {
  count         = local.agent_count
  name          = "${local.project}-agent"
  output_format = "json"
  delivery_destination_configuration {
    destination_resource_arn = aws_cloudwatch_log_group.agent.arn
  }
}

resource "aws_cloudwatch_log_delivery" "agent" {
  count                    = local.agent_count
  delivery_source_name     = aws_cloudwatch_log_delivery_source.agent[0].name
  delivery_destination_arn = aws_cloudwatch_log_delivery_destination.agent[0].arn
}

resource "aws_security_group" "agent" {
  name_prefix = "${local.project}-agent-"
  description = "Salida del agente a APIs AWS, GitHub y Slack"
  vpc_id      = var.vpc_id
  egress {
    protocol    = "-1"
    from_port   = 0
    to_port     = 0
    cidr_blocks = ["0.0.0.0/0"]
  }
}
