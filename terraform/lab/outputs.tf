output "instance_ids" {
  description = "Map of scenario key to instance ID. Use these in Lambda logs."
  value       = { for key, inst in aws_instance.lab : key => inst.id }
}

output "instances" {
  description = "Name, scenario, and ID for each lab VM."
  value = {
    for key, inst in aws_instance.lab : key => {
      id       = inst.id
      name     = inst.tags["Name"]
      scenario = inst.tags["Scenario"]
    }
  }
}

output "vpc_id" {
  value = aws_vpc.lab.id
}

output "instance_state" {
  value = var.lab_instance_state
}
