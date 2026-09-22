output "vpc_id" { value = aws_vpc.workshop.id }
output "private_subnet_ids" { value = aws_subnet.private[*].id }
