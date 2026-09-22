# Datos del proveedor separados del bucket que contiene los DAGs.
resource "aws_s3_bucket" "sales_input" {
  bucket        = "${local.project}-input-${local.config.account}-${local.config.region}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "sales" {
  bucket                  = aws_s3_bucket.sales_input.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "sales" {
  bucket = aws_s3_bucket.sales_input.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_s3_bucket_policy" "sales_tls" {
  bucket = aws_s3_bucket.sales_input.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect    = "Deny", Principal = "*", Action = "s3:*"
    Resource  = [aws_s3_bucket.sales_input.arn, "${aws_s3_bucket.sales_input.arn}/*"]
    Condition = { Bool = { "aws:SecureTransport" = "false" } }
  }] })
}

resource "aws_s3_object" "sales_sample" {
  bucket       = aws_s3_bucket.sales_input.id
  key          = "incoming/sales.csv"
  source       = "${path.module}/../../data/sales.csv"
  source_hash  = filemd5("${path.module}/../../data/sales.csv")
  content_type = "text/csv"
}
