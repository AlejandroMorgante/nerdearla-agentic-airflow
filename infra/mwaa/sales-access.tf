# Incidente: se publicó el DAG, pero no se completaron los permisos de MWAA.
# La PR del agente debe agregar sólo las acciones y recursos necesarios.
resource "aws_iam_role_policy" "sales" {
  role = aws_iam_role.mwaa.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = "s3:ListBucket", Resource = var.sales_input_arn }
  ] })
}
