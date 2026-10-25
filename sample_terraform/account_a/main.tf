resource "aws_instance" "web_api" {
  ami           = "ami-0abcdef1234567890"
  instance_type = "m5.2xlarge"

  tags = {
    Name = "web-api-prod"
  }
}

resource "aws_instance" "batch_worker" {
  ami           = "ami-0abcdef1234567890"
  instance_type = "c5.4xlarge"

  tags = {
    Name = "batch-worker"
  }
}

resource "aws_instance" "dev_bastion" {
  ami           = "ami-0abcdef1234567890"
  instance_type = "t3.large"

  tags = {
    Name = "dev-bastion"
  }
}

resource "aws_instance" "legacy_etl" {
  ami           = "ami-0abcdef1234567890"
  instance_type = "r5.xlarge"

  tags = {
    Name = "legacy-etl"
  }
}

resource "aws_ebs_volume" "old_data" {
  availability_zone = "us-east-1a"
  size              = 500
  type              = "gp2"
}

resource "aws_ebs_volume" "db_data" {
  availability_zone = "us-east-1a"
  size              = 1000
  type              = "gp2"
}

resource "aws_eip" "legacy" {
  domain = "vpc"
}

resource "aws_nat_gateway" "unused_az" {
  allocation_id = aws_eip.legacy.id
  subnet_id     = "subnet-0aa11bb22cc33dd44"
}

resource "aws_ebs_snapshot" "pre_migration" {
  volume_id = aws_ebs_volume.old_data.id
}
