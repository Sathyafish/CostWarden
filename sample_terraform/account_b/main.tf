resource "aws_instance" "orders" {
  ami           = "ami-0abcdef1234567890"
  instance_type = "m5.xlarge"

  tags = {
    Name = "orders-service"
  }
}

resource "aws_instance" "staging_app" {
  ami           = "ami-0abcdef1234567890"
  instance_type = "t3.xlarge"

  tags = {
    Name = "staging-app"
  }
}

resource "aws_db_instance" "orders" {
  identifier     = "orders-db"
  engine         = "postgres"
  instance_class = "db.r5.2xlarge"
  multi_az       = true
}

resource "aws_lb" "internal_tools" {
  name               = "internal-tools"
  load_balancer_type = "application"
  internal           = true
}

resource "aws_ebs_volume" "scratch" {
  availability_zone = "eu-west-1a"
  size              = 200
  type              = "gp3"
}
