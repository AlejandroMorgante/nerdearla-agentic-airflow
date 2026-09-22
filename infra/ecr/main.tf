resource "aws_ecr_repository" "agent" {
  force_delete         = true
  name                 = "${local.project}/agent"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration { scan_on_push = true }
}

resource "aws_ecr_lifecycle_policy" "agent" {
  repository = aws_ecr_repository.agent.name
  policy = jsonencode({ rules = [{
    rulePriority = 1, description = "Eliminar imágenes sin tag después de 7 días"
    selection    = { tagStatus = "untagged", countType = "sinceImagePushed", countUnit = "days", countNumber = 7 }
    action       = { type = "expire" }
  }] })
}

# Sólo contenedores vacíos. Los valores se cargan fuera de Terraform y del state.
