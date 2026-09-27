data "archive_file" "tag_governance" {
  type        = "zip"
  source_dir  = "${path.module}/../../src/tag_governance"
  output_path = "${path.module}/tag_governance.zip"
  excludes    = ["__pycache__", "*.pyc"]
}

data "archive_file" "instance_scheduler" {
  type        = "zip"
  source_dir  = "${path.module}/../../src/instance_scheduler"
  output_path = "${path.module}/instance_scheduler.zip"
  excludes    = ["__pycache__", "*.pyc"]
}

data "archive_file" "orphan_scanner" {
  type        = "zip"
  source_dir  = "${path.module}/../../src/orphan_scanner"
  output_path = "${path.module}/orphan_scanner.zip"
  excludes    = ["__pycache__", "*.pyc"]
}

resource "aws_lambda_function" "tag_governance" {
  function_name    = local.tag_governance_name
  role             = aws_iam_role.tag_governance.arn
  filename         = data.archive_file.tag_governance.output_path
  source_code_hash = data.archive_file.tag_governance.output_base64sha256
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  timeout          = 30
  memory_size      = 128
  tags             = local.common_tags

  environment {
    variables = {
      FINDINGS_TABLE  = aws_dynamodb_table.findings.name
      ALERT_TOPIC_ARN = aws_sns_topic.alerts.arn
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.tag_governance,
    aws_iam_role_policy.tag_governance,
  ]
}

resource "aws_lambda_function" "instance_scheduler" {
  function_name    = local.instance_scheduler_name
  role             = aws_iam_role.instance_scheduler.arn
  filename         = data.archive_file.instance_scheduler.output_path
  source_code_hash = data.archive_file.instance_scheduler.output_base64sha256
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  timeout          = 45
  memory_size      = 128
  tags             = local.common_tags

  depends_on = [
    aws_cloudwatch_log_group.instance_scheduler,
    aws_iam_role_policy.instance_scheduler,
  ]
}

resource "aws_lambda_function" "orphan_scanner" {
  function_name    = local.orphan_scanner_name
  role             = aws_iam_role.orphan_scanner.arn
  filename         = data.archive_file.orphan_scanner.output_path
  source_code_hash = data.archive_file.orphan_scanner.output_base64sha256
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  timeout          = 120
  memory_size      = 256
  tags             = local.common_tags

  environment {
    variables = {
      FINDINGS_TABLE  = aws_dynamodb_table.findings.name
      ALERT_TOPIC_ARN = aws_sns_topic.alerts.arn
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.orphan_scanner,
    aws_iam_role_policy.orphan_scanner,
  ]
}
