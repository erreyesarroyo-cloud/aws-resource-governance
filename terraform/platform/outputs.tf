output "tag_governance_function_name" {
  value = aws_lambda_function.tag_governance.function_name
}

output "instance_scheduler_function_name" {
  value = aws_lambda_function.instance_scheduler.function_name
}

output "orphan_scanner_function_name" {
  value = aws_lambda_function.orphan_scanner.function_name
}

output "eventbridge_rule_name" {
  value = aws_cloudwatch_event_rule.ec2_state_change.name
}

output "stop_schedule_name" {
  value = aws_scheduler_schedule.stop_1930.name
}

output "orphan_schedule_name" {
  value = aws_scheduler_schedule.orphan_daily.name
}

output "findings_table_name" {
  value = aws_dynamodb_table.findings.name
}

output "alerts_topic_arn" {
  value = aws_sns_topic.alerts.arn
}

output "alert_email" {
  value     = var.alert_email
  sensitive = true
}
