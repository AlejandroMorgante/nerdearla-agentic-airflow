resource "aws_iam_role_policy" "sales" {
  role = aws_iam_role.mwaa.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = "s3:ListBucket", Resource = var.sales_input_arn },
    { Effect = "Allow", Action = "s3:GetObject", Resource = "${var.sales_input_arn}/incoming/sales.csv" }
  ] })
}
