output "bucket_name" { value = aws_s3_bucket.artifacts.id }
output "bucket_arn" { value = aws_s3_bucket.artifacts.arn }
output "requirements_key" { value = aws_s3_object.requirements.key }
output "requirements_version" { value = aws_s3_object.requirements.version_id }
