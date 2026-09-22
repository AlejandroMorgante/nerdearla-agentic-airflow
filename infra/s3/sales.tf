# Datos del proveedor y resultados separados del bucket que contiene los DAGs.
resource "aws_s3_bucket" "sales" {
  for_each      = toset(["input", "output"])
  bucket        = "${local.project}-${each.key}-${local.config.account}-${local.config.region}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "sales" {
  for_each                = aws_s3_bucket.sales
  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "sales" {
  for_each = aws_s3_bucket.sales
  bucket   = each.value.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_s3_bucket_policy" "sales_tls" {
  for_each = aws_s3_bucket.sales
  bucket   = each.value.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect    = "Deny", Principal = "*", Action = "s3:*"
    Resource  = [each.value.arn, "${each.value.arn}/*"]
    Condition = { Bool = { "aws:SecureTransport" = "false" } }
  }] })
}

resource "aws_s3_object" "sales_sample" {
  bucket       = aws_s3_bucket.sales["input"].id
  key          = "incoming/sales.csv"
  source       = "${path.module}/../../data/sales.csv"
  source_hash  = filemd5("${path.module}/../../data/sales.csv")
  content_type = "text/csv"
}
