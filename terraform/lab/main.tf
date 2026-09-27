data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  filter {
    name   = "state"
    values = ["available"]
  }
}

locals {
  common_tags = {
    Project = "aws-resource-governance"
    Lab     = "true"
  }

  # Three fixtures for tag governance and the 19:30 stop filter.
  #   compliant          → 1930shutdown=true
  #   missing_managedby  → 1930shutdown=true
  #   missing_owner_env  → no schedule tag (scheduler must ignore)
  lab_instances = {
    compliant = {
      name = "${var.name_prefix}-lab-compliant"
      extra_tags = {
        Owner          = "lab"
        Environment    = "dev"
        ManagedBy      = "GovernancePlatform"
        "1930shutdown" = "true"
        Scenario       = "compliant"
        Purpose        = "LAB RESOURCE"
      }
    }
    missing_managedby = {
      name = "${var.name_prefix}-lab-missing-managedby"
      extra_tags = {
        Owner          = "lab"
        Environment    = "dev"
        "1930shutdown" = "true"
        Scenario       = "missing-managedby"
        Purpose        = "INTENTIONALLY NONCOMPLIANT LAB RESOURCES"
      }
    }
    missing_owner_env = {
      name = "${var.name_prefix}-lab-missing-owner-env"
      extra_tags = {
        Scenario = "missing-owner-env"
        Purpose  = "INTENTIONALLY NONCOMPLIANT LAB RESOURCES"
      }
    }
  }
}

resource "aws_vpc" "lab" {
  cidr_block           = "10.42.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(local.common_tags, {
    Name    = "${var.name_prefix}-lab-vpc"
    Purpose = "LAB RESOURCE"
  })
}

resource "aws_subnet" "lab" {
  vpc_id                  = aws_vpc.lab.id
  cidr_block              = "10.42.1.0/24"
  availability_zone       = data.aws_availability_zones.available.names[0]
  map_public_ip_on_launch = false

  tags = merge(local.common_tags, {
    Name    = "${var.name_prefix}-lab-subnet"
    Purpose = "LAB RESOURCE"
  })
}

resource "aws_security_group" "lab" {
  name        = "${var.name_prefix}-lab-sg"
  description = "Lab instances: no inbound. State-change events do not need SSH."
  vpc_id      = aws_vpc.lab.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name    = "${var.name_prefix}-lab-sg"
    Purpose = "LAB RESOURCE"
  })
}

resource "aws_instance" "lab" {
  for_each = local.lab_instances

  ami                         = data.aws_ami.al2023.id
  instance_type               = var.instance_type
  subnet_id                   = aws_subnet.lab.id
  vpc_security_group_ids      = [aws_security_group.lab.id]
  associate_public_ip_address = false

  root_block_device {
    # AL2023 AMI root snapshot is now 30 GB; 8 GB fails InvalidBlockDeviceMapping.
    volume_size = 30
    volume_type = "gp3"
    encrypted   = true
  }

  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }

  tags = merge(local.common_tags, each.value.extra_tags, {
    Name = each.value.name
  })

  lifecycle {
    ignore_changes = [ami]
  }
}

resource "aws_ec2_instance_state" "lab" {
  for_each    = aws_instance.lab
  instance_id = each.value.id
  state       = var.lab_instance_state
}
