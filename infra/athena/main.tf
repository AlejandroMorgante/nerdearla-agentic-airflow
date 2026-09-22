resource "aws_athena_workgroup" "sales" {
  name          = "${var.config.project}-sales"
  force_destroy = true
  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = false
    bytes_scanned_cutoff_per_query     = 10485760
    engine_version { selected_engine_version = "Athena engine version 3" }
    result_configuration {
      output_location = "s3://${var.output_bucket}/athena-results/"
      encryption_configuration { encryption_option = "SSE_S3" }
    }
  }
}
