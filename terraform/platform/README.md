# Platform stack

Lambdas (tag governance, instance scheduler, orphan scanner), findings table, SNS, EventBridge rule, and schedules.

```powershell
terraform init -backend-config=../backend.hcl
terraform apply -var="alert_email=you@example.com"
```

Confirm the SNS subscription email after apply.

Schedules default to **disabled**. Enable when you want them live:

```powershell
terraform apply -var="alert_email=you@example.com" -var="enable_stop_schedule=true" -var="enable_orphan_schedule=true"
```

Or copy `terraform.tfvars.example` to `terraform.tfvars` (gitignored).
