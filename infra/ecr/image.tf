locals {
  agent_dir = abspath("${path.module}/../../airflow-agent")
  image_tag = sha256(join("", [for file in [
    "agent.py", "tools.py", "config.yaml", "container/Dockerfile", "container/requirements.txt"
  ] : filesha256("${local.agent_dir}/${file}")]))
}

# El Runtime depende de image_uri, que sólo queda disponible después del push.
resource "terraform_data" "image" {
  triggers_replace = [aws_ecr_repository.agent.repository_url, local.image_tag, filesha256("${path.module}/build.sh")]
  provisioner "local-exec" {
    command     = "bash build.sh"
    working_dir = path.module
    environment = {
      AGENT_REPOSITORY = aws_ecr_repository.agent.repository_url
      AGENT_TAG        = local.image_tag
      AGENT_CONTEXT    = local.agent_dir
      AGENT_REGION     = local.config.region
    }
  }
}
