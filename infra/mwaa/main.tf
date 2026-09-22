resource "aws_cloudwatch_log_group" "mwaa" {
  for_each          = toset(["DAGProcessing", "Scheduler", "Task", "WebServer", "Worker"])
  name              = "airflow-${local.project}-${each.key}"
  retention_in_days = 7
  kms_key_id        = var.kms_key_arn
}

resource "aws_iam_role" "mwaa" {
  name = "${local.project}-mwaa"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect    = "Allow", Action = "sts:AssumeRole"
    Principal = { Service = ["airflow.amazonaws.com", "airflow-env.amazonaws.com"] }
  }] })
}

resource "aws_iam_role_policy" "mwaa" {
  role = aws_iam_role.mwaa.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["s3:ListBucket", "s3:GetBucketLocation", "s3:GetBucketPublicAccessBlock", "s3:GetObject*"], Resource = [var.bucket_arn, "${var.bucket_arn}/*"] },
    { Effect = "Allow", Action = ["kms:Encrypt", "kms:Decrypt", "kms:ReEncrypt*", "kms:GenerateDataKey*", "kms:DescribeKey"], Resource = var.kms_key_arn },
    { Effect = "Allow", Action = "airflow:PublishMetrics", Resource = "arn:aws:airflow:${local.config.region}:${local.config.account}:environment/${local.project}" },
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:CreateLogGroup", "logs:PutLogEvents", "logs:GetLogEvents", "logs:GetLogRecord", "logs:GetLogGroupFields", "logs:GetQueryResults", "logs:DescribeLogStreams"], Resource = "arn:aws:logs:${local.config.region}:${local.config.account}:log-group:airflow-${local.project}-*" },
    { Effect = "Allow", Action = ["logs:DescribeLogGroups", "s3:GetAccountPublicAccessBlock", "cloudwatch:PutMetricData"], Resource = "*" },
    { Effect = "Allow", Action = ["sqs:ChangeMessageVisibility", "sqs:DeleteMessage", "sqs:GetQueueAttributes", "sqs:GetQueueUrl", "sqs:ReceiveMessage", "sqs:SendMessage"], Resource = "arn:aws:sqs:${local.config.region}:*:airflow-celery-*" }
  ] })
}

resource "aws_mwaa_environment" "workshop" {
  name                           = local.project
  airflow_version                = local.config.airflow_version
  environment_class              = local.config.mwaa_class
  execution_role_arn             = aws_iam_role.mwaa.arn
  kms_key                        = var.kms_key_arn
  source_bucket_arn              = var.bucket_arn
  dag_s3_path                    = "dags"
  requirements_s3_path           = var.requirements_key
  requirements_s3_object_version = var.requirements_version
  min_workers                    = 1
  max_workers                    = 2
  schedulers                     = 2
  webserver_access_mode          = "PUBLIC_ONLY"
  airflow_configuration_options  = { "core.load_examples" = "False" }
  network_configuration {
    security_group_ids = [aws_security_group.mwaa.id]
    subnet_ids         = var.subnet_ids
  }
  logging_configuration {
    dag_processing_logs {
      enabled   = true
      log_level = "INFO"
    }
    scheduler_logs {
      enabled   = true
      log_level = "INFO"
    }
    task_logs {
      enabled   = true
      log_level = "INFO"
    }
    webserver_logs {
      enabled   = true
      log_level = "INFO"
    }
    worker_logs {
      enabled   = true
      log_level = "INFO"
    }
  }
  depends_on = [
    aws_iam_role_policy.mwaa, aws_cloudwatch_log_group.mwaa,
  ]
}

resource "aws_security_group" "mwaa" {
  name_prefix = "${local.project}-mwaa-"
  description = "Comunicacion interna de MWAA"
  vpc_id      = var.vpc_id
  ingress {
    protocol  = "-1"
    from_port = 0
    to_port   = 0
    self      = true
  }
  egress {
    protocol    = "-1"
    from_port   = 0
    to_port     = 0
    cidr_blocks = ["0.0.0.0/0"]
  }
}
