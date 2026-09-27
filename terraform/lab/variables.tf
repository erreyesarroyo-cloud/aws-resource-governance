variable "aws_region" {
  description = "Must match the platform region. EventBridge EC2 events are regional."
  type        = string
  default     = "us-east-1"
}

variable "name_prefix" {
  type    = string
  default = "aws-gov"
}

variable "instance_type" {
  description = "Cheap instance for generating EC2 state-change events."
  type        = string
  default     = "t3.micro"
}

variable "lab_instance_state" {
  description = "Applies to all three lab instances. running for events; stopped to save money."
  type        = string
  default     = "running"

  validation {
    condition     = contains(["running", "stopped"], var.lab_instance_state)
    error_message = "lab_instance_state must be running or stopped."
  }
}
