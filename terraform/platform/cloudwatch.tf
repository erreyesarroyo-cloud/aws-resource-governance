resource "aws_cloudwatch_log_group" "tag_governance" {
  name              = "/aws/lambda/${local.tag_governance_name}"
  retention_in_days = var.log_retention_days
  tags              = local.common_tags
}

resource "aws_cloudwatch_log_group" "instance_scheduler" {
  name              = "/aws/lambda/${local.instance_scheduler_name}"
  retention_in_days = var.log_retention_days
  tags              = local.common_tags
}

resource "aws_cloudwatch_log_group" "orphan_scanner" {
  name              = "/aws/lambda/${local.orphan_scanner_name}"
  retention_in_days = var.log_retention_days
  tags              = local.common_tags
}
