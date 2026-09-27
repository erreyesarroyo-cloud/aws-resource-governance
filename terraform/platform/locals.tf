data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  tag_governance_name     = "${var.name_prefix}-tag-governance"
  instance_scheduler_name = "${var.name_prefix}-instance-scheduler"
  orphan_scanner_name     = "${var.name_prefix}-orphan-scanner"
  event_rule_name         = "${var.name_prefix}-ec2-state-change"
  stop_schedule_name      = "${var.name_prefix}-stop-1930"
  orphan_schedule_name    = "${var.name_prefix}-orphan-daily"
  findings_table_name     = "${var.name_prefix}-findings"
  alerts_topic_name       = "${var.name_prefix}-alerts"
  account_id              = data.aws_caller_identity.current.account_id
  region                  = data.aws_region.current.name

  common_tags = {
    Project   = "aws-resource-governance"
    Component = "platform"
    ManagedBy = "Terraform"
  }
}
