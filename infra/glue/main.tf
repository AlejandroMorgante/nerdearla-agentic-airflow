resource "aws_s3_object" "script" {
  bucket      = var.artifacts_bucket
  key         = "glue/sales.py"
  source      = "${path.module}/sales.py"
  source_hash = filemd5("${path.module}/sales.py")
}

resource "aws_iam_role" "glue" {
  name = "${var.config.project}-glue"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "glue.amazonaws.com" }
  }] })
}

resource "aws_cloudwatch_log_group" "glue" {
  for_each          = toset(["error", "output"])
  name              = "/${var.config.project}/glue/${each.key}"
  retention_in_days = 7
}

resource "aws_iam_role_policy" "glue" {
  role = aws_iam_role.glue.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["s3:ListBucket", "s3:GetBucketLocation"], Resource = [
      "arn:aws:s3:::${var.input_bucket}", "arn:aws:s3:::${var.output_bucket}", "arn:aws:s3:::${var.artifacts_bucket}"
    ] },
    { Effect = "Allow", Action = "s3:GetObject", Resource = [
      "arn:aws:s3:::${var.input_bucket}/incoming/sales.csv", "arn:aws:s3:::${var.artifacts_bucket}/${aws_s3_object.script.key}"
    ] },
    { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:AbortMultipartUpload"],
    Resource = "arn:aws:s3:::${var.output_bucket}/sales/*" },
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"],
    Resource = [for group in aws_cloudwatch_log_group.glue : "${group.arn}:*"] }
  ] })
}

resource "aws_glue_job" "sales" {
  name              = "${var.config.project}-sales"
  role_arn          = aws_iam_role.glue.arn
  glue_version      = "5.0"
  worker_type       = "G.1X"
  number_of_workers = 2
  timeout           = 10
  max_retries       = 0
  execution_property { max_concurrent_runs = 1 }
  command {
    name            = "glueetl"
    python_version  = "3"
    script_location = "s3://${var.artifacts_bucket}/${aws_s3_object.script.key}"
  }
  default_arguments = {
    "--INPUT_URI"              = "s3://${var.input_bucket}/incoming/sales.csv"
    "--OUTPUT_URI"             = "s3://${var.output_bucket}/sales/"
    "--job-language"           = "python"
    "--job-bookmark-option"    = "job-bookmark-disable"
    "--custom-logGroup-prefix" = "/${var.config.project}/glue"
  }
  depends_on = [aws_iam_role_policy.glue]
}
