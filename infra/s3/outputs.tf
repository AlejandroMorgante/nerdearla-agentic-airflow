output "bucket_name" { value = aws_s3_bucket.artifacts.id }
output "bucket_arn" { value = aws_s3_bucket.artifacts.arn }
output "requirements_key" { value = aws_s3_object.requirements.key }
output "requirements_version" { value = aws_s3_object.requirements.version_id }
output "sales_input_bucket" { value = aws_s3_bucket.sales["input"].id }
output "sales_input_arn" { value = aws_s3_bucket.sales["input"].arn }
output "sales_output_bucket" { value = aws_s3_bucket.sales["output"].id }
output "sales_output_arn" { value = aws_s3_bucket.sales["output"].arn }
