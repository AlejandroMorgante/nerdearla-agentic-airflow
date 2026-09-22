resource "aws_kms_key" "workshop" {
  description             = "Cifrado de MWAA y logs del workshop"
  enable_key_rotation     = true
  deletion_window_in_days = 30
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Principal = { AWS = "arn:aws:iam::${local.config.account}:root" }, Action = "kms:*", Resource = "*" },
      {
        Effect = "Allow", Principal = { Service = "logs.${local.config.region}.amazonaws.com" }
        Action = ["kms:Encrypt", "kms:Decrypt", "kms:ReEncrypt*", "kms:GenerateDataKey*", "kms:DescribeKey"], Resource = "*"
        Condition = { ArnLike = { "kms:EncryptionContext:aws:logs:arn" = [
          "arn:aws:logs:${local.config.region}:${local.config.account}:log-group:airflow-${local.project}-*",
          "arn:aws:logs:${local.config.region}:${local.config.account}:log-group:/aws/bedrock-agentcore/${local.project}*"
        ] } }
      }
    ]
  })
  lifecycle { prevent_destroy = true }
}
