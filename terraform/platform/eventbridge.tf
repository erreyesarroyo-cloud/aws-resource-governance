resource "aws_cloudwatch_event_rule" "ec2_state_change" {
  name           = local.event_rule_name
  description    = "Invoke tag governance when an EC2 instance changes state."
  event_bus_name = "default"

  event_pattern = jsonencode({
    source      = ["aws.ec2"]
    detail-type = ["EC2 Instance State-change Notification"]
  })

  tags = local.common_tags
}

resource "aws_cloudwatch_event_target" "tag_governance" {
  rule           = aws_cloudwatch_event_rule.ec2_state_change.name
  event_bus_name = aws_cloudwatch_event_rule.ec2_state_change.event_bus_name
  arn            = aws_lambda_function.tag_governance.arn
  target_id      = "tag-governance"
}

resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.tag_governance.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.ec2_state_change.arn
}

resource "aws_scheduler_schedule" "stop_1930" {
  name                         = local.stop_schedule_name
  group_name                   = "default"
  schedule_expression          = "cron(30 19 * * ? *)"
  schedule_expression_timezone = "America/New_York"
  state                        = var.enable_stop_schedule ? "ENABLED" : "DISABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.instance_scheduler.arn
    role_arn = aws_iam_role.scheduler_stop.arn
    input    = jsonencode({ action = "stop" })
  }
}

resource "aws_lambda_permission" "allow_scheduler_stop" {
  statement_id  = "AllowSchedulerStopInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.instance_scheduler.function_name
  principal     = "scheduler.amazonaws.com"
  source_arn    = aws_scheduler_schedule.stop_1930.arn
}

resource "aws_scheduler_schedule" "orphan_daily" {
  name                         = local.orphan_schedule_name
  group_name                   = "default"
  schedule_expression          = "cron(0 8 * * ? *)"
  schedule_expression_timezone = "America/New_York"
  state                        = var.enable_orphan_schedule ? "ENABLED" : "DISABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.orphan_scanner.arn
    role_arn = aws_iam_role.scheduler_orphan.arn
    input    = jsonencode({ action = "scan" })
  }
}

resource "aws_lambda_permission" "allow_scheduler_orphan" {
  statement_id  = "AllowSchedulerOrphanInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.orphan_scanner.function_name
  principal     = "scheduler.amazonaws.com"
  source_arn    = aws_scheduler_schedule.orphan_daily.arn
}
