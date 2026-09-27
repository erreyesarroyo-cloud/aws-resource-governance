resource "aws_dynamodb_table" "findings" {
  name         = local.findings_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "resource_id"
  range_key    = "timestamp"

  attribute {
    name = "resource_id"
    type = "S"
  }

  attribute {
    name = "timestamp"
    type = "S"
  }

  tags = local.common_tags
}
