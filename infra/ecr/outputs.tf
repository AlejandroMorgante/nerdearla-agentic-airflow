output "repository_url" { value = aws_ecr_repository.agent.repository_url }
output "repository_arn" { value = aws_ecr_repository.agent.arn }
output "image_uri" {
  value      = "${aws_ecr_repository.agent.repository_url}:${local.image_tag}"
  depends_on = [terraform_data.image]
}
