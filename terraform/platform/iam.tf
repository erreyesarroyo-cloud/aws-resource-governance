data "aws_iam_policy_document" "lambda_assume" {
  statement {
    sid     = "AllowLambdaAssume"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    sid     = "AllowSchedulerAssume"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

# --- Lambda 1: tag governance ---

resource "aws_iam_role" "tag_governance" {
  name               = "${local.tag_governance_name}-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "tag_governance" {
  statement {
    sid    = "WriteOwnLogGroup"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["${aws_cloudwatch_log_group.tag_governance.arn}:*"]
  }

  statement {
    sid       = "ReadEc2Tags"
    effect    = "Allow"
    actions   = ["ec2:DescribeInstances", "ec2:DescribeTags"]
    resources = ["*"]
  }

  statement {
    sid       = "AddMissingTags"
    effect    = "Allow"
    actions   = ["ec2:CreateTags"]
    resources = ["arn:aws:ec2:${local.region}:${local.account_id}:instance/*"]
  }

  statement {
    sid       = "PutFindings"
    effect    = "Allow"
    actions   = ["dynamodb:PutItem"]
    resources = [aws_dynamodb_table.findings.arn]
  }

  statement {
    sid       = "PublishAlerts"
    effect    = "Allow"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.alerts.arn]
  }
}

resource "aws_iam_role_policy" "tag_governance" {
  name   = "tag-governance"
  role   = aws_iam_role.tag_governance.id
  policy = data.aws_iam_policy_document.tag_governance.json
}

# --- Lambda 2: instance scheduler ---

resource "aws_iam_role" "instance_scheduler" {
  name               = "${local.instance_scheduler_name}-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "instance_scheduler" {
  statement {
    sid    = "WriteOwnLogGroup"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["${aws_cloudwatch_log_group.instance_scheduler.arn}:*"]
  }

  statement {
    sid       = "FindAndStop"
    effect    = "Allow"
    actions   = ["ec2:DescribeInstances", "ec2:StopInstances"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "instance_scheduler" {
  name   = "instance-scheduler"
  role   = aws_iam_role.instance_scheduler.id
  policy = data.aws_iam_policy_document.instance_scheduler.json
}

# --- Lambda 3: orphan scanner (read-only plus write findings) ---

resource "aws_iam_role" "orphan_scanner" {
  name               = "${local.orphan_scanner_name}-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "orphan_scanner" {
  statement {
    sid    = "WriteOwnLogGroup"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["${aws_cloudwatch_log_group.orphan_scanner.arn}:*"]
  }

  statement {
    sid    = "DescribeOrphans"
    effect = "Allow"
    actions = [
      "ec2:DescribeVolumes",
      "ec2:DescribeAddresses",
      "ec2:DescribeNetworkInterfaces",
      "ec2:DescribeTags",
    ]
    resources = ["*"]
  }

  statement {
    sid       = "PutFindings"
    effect    = "Allow"
    actions   = ["dynamodb:PutItem"]
    resources = [aws_dynamodb_table.findings.arn]
  }

  statement {
    sid       = "PublishAlerts"
    effect    = "Allow"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.alerts.arn]
  }
}

resource "aws_iam_role_policy" "orphan_scanner" {
  name   = "orphan-scanner"
  role   = aws_iam_role.orphan_scanner.id
  policy = data.aws_iam_policy_document.orphan_scanner.json
}

# --- EventBridge Scheduler invoke roles ---

resource "aws_iam_role" "scheduler_stop" {
  name               = "${local.stop_schedule_name}-invoke-role"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "scheduler_stop" {
  statement {
    sid       = "InvokeStopLambda"
    effect    = "Allow"
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.instance_scheduler.arn]
  }
}

resource "aws_iam_role_policy" "scheduler_stop" {
  name   = "invoke-stop-lambda"
  role   = aws_iam_role.scheduler_stop.id
  policy = data.aws_iam_policy_document.scheduler_stop.json
}

resource "aws_iam_role" "scheduler_orphan" {
  name               = "${local.orphan_schedule_name}-invoke-role"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "scheduler_orphan" {
  statement {
    sid       = "InvokeOrphanLambda"
    effect    = "Allow"
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.orphan_scanner.arn]
  }
}

resource "aws_iam_role_policy" "scheduler_orphan" {
  name   = "invoke-orphan-lambda"
  role   = aws_iam_role.scheduler_orphan.id
  policy = data.aws_iam_policy_document.scheduler_orphan.json
}
