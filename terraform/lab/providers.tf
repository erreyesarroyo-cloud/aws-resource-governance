terraform {
  required_version = ">= 1.5.0"

  backend "s3" {
    key = "lab/terraform.tfstate"
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}
