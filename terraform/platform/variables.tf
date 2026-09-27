variable "aws_region" {
  description = "Region for platform resources. EventBridge EC2 events are regional."
  type        = string
  default     = "us-east-1"
}

variable "name_prefix" {
  description = "Prefix for resource names."
  type        = string
  default     = "aws-gov"
}

variable "log_retention_days" {
  type    = number
  default = 14
}

variable "alert_email" {
  description = "SNS email subscription. Confirm the new topic after apply."
  type        = string
}

variable "enable_stop_schedule" {
  description = "19:30 America/New_York stop. Leave false until you want it live."
  type        = bool
  default     = false
}

variable "enable_orphan_schedule" {
  description = "Daily orphan scan. Leave false until you want it live."
  type        = bool
  default     = false
}
