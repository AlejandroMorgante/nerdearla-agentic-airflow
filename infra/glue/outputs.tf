output "job_name" { value = aws_glue_job.sales.name }
output "job_arn" { value = aws_glue_job.sales.arn }
output "database_name" { value = aws_glue_catalog_database.sales.name }
