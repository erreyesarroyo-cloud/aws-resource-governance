# Remote Terraform state

This stack uses **local state on purpose**. It creates the S3 bucket and DynamoDB lock table that `lab` and `platform` use.

```powershell
cd terraform/bootstrap
terraform init
terraform apply
```

Copy `terraform/backend.hcl.example` to `terraform/backend.hcl` and set `bucket` to the `bucket` output.

Then:

```powershell
cd terraform/lab
terraform init -backend-config=../backend.hcl

cd terraform/platform
terraform init -backend-config=../backend.hcl
```

Do not destroy this folder if you still want remote state. Destroying **lab** or **platform** does not delete the bucket.

S3 and DynamoDB have `prevent_destroy = true`. To delete them, remove that lifecycle block first.

Keep `terraform/bootstrap/*.tfstate` on the machine that applied it (gitignored).
