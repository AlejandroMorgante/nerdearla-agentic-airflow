resource "aws_s3_bucket" "artifacts" {
  bucket = "${local.project}-${local.config.account}-${local.config.region}"
  lifecycle { prevent_destroy = true }
}

resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket                  = aws_s3_bucket.artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_s3_bucket_policy" "tls" {
  bucket = aws_s3_bucket.artifacts.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Deny", Principal = "*", Action = "s3:*"
      Resource  = [aws_s3_bucket.artifacts.arn, "${aws_s3_bucket.artifacts.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
}

resource "aws_s3_object" "requirements" {
  bucket      = aws_s3_bucket.artifacts.id
  key         = "requirements/requirements.txt"
  source      = "${path.module}/../mwaa/requirements.txt"
  source_hash = filemd5("${path.module}/../mwaa/requirements.txt")
  depends_on  = [aws_s3_bucket_versioning.artifacts]
}

resource "aws_s3_object" "dag" {
  bucket      = aws_s3_bucket.artifacts.id
  key         = local.config.github_dag_path
  source      = "${path.module}/../../${local.config.github_dag_path}"
  source_hash = filemd5("${path.module}/../../${local.config.github_dag_path}")
  depends_on  = [aws_s3_bucket_versioning.artifacts]
}
