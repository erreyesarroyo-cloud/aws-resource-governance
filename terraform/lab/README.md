# Lab fixtures

VPC plus three `t3.micro` instances used to exercise tag governance:

| Name | Tags |
| --- | --- |
| `aws-gov-lab-compliant` | Owner, Environment, ManagedBy present |
| `aws-gov-lab-missing-managedby` | ManagedBy absent |
| `aws-gov-lab-missing-owner-env` | Owner and Environment absent |

```powershell
terraform init -backend-config=../backend.hcl
terraform apply
```

Stopped instances still bill for EBS. Destroy this stack when you no longer need the fixtures.
