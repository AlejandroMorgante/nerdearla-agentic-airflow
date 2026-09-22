resource "aws_vpc" "workshop" {
  cidr_block           = "10.42.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = local.project }
}

resource "aws_default_security_group" "workshop" {
  vpc_id = aws_vpc.workshop.id
}

resource "aws_subnet" "public" {
  count             = 2
  vpc_id            = aws_vpc.workshop.id
  availability_zone = local.config.availability_zones[count.index]
  cidr_block        = cidrsubnet(aws_vpc.workshop.cidr_block, 8, count.index)
  tags              = { Name = "${local.project}-public-${count.index}" }
}

resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.workshop.id
  availability_zone = local.config.availability_zones[count.index]
  cidr_block        = cidrsubnet(aws_vpc.workshop.cidr_block, 8, count.index + 2)
  tags              = { Name = "${local.project}-private-${count.index}" }
}

resource "aws_internet_gateway" "workshop" {
  vpc_id = aws_vpc.workshop.id
}

resource "aws_eip" "nat" { domain = "vpc" }

resource "aws_nat_gateway" "workshop" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id
  depends_on    = [aws_internet_gateway.workshop]
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.workshop.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.workshop.id
  }
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.workshop.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.workshop.id
  }
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "private" {
  count          = 2
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}
