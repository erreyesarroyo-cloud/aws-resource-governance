# AWS Resource Governance

Watches EC2 in an account, enforces a small tagging standard, stops instances that have opted in at 19:30 Eastern, and reports likely orphans. It only writes a tag or stops an instance when that action is safe and explicit. Everything else is recorded for a person to review.

It never terminates instances, never deletes volumes, never releases Elastic IPs, and never deletes ENIs.

## Design choices

Why it is built this way: [`architecture/decisions.md`](architecture/decisions.md).

- **Three Lambdas, not one.** Tag writes, the 19:30 stop, and the orphan scan have different triggers and failure modes. Splitting them keeps IAM honest: the scanner never gets `CreateTags` or `StopInstances`.
- **Write `missing`, never guess.** If `Owner`, `Environment`, or `ManagedBy` is absent, that key is set to `missing`. It does not invent `dev` or a person name, and it never overwrites a tag that already exists.
- **Report orphans, do not delete them.** An unattached ENI can still belong to Lambda, NAT, or a VPC endpoint. Unused is not the same as safe to destroy, so the scanner records `CLEANUP_CANDIDATE` or `MANUAL_REVIEW` and stops.

## What it does

| Workload | Trigger | Action |
| --- | --- | --- |
| **Tag governance** | EC2 instance state-change (EventBridge) | If `Owner`, `Environment`, or `ManagedBy` is **absent**, write that key with value `missing`. Never overwrite an existing tag. Persist a finding; email only on auto-remediation. |
| **Instance scheduler** | EventBridge Scheduler, 19:30 `America/New_York` | Stop running instances tagged `Lab=true` **and** `1930shutdown=true`. No start job. |
| **Orphan scanner** | Daily schedule | Classify unattached EBS, unused EIPs, and ambiguous ENIs. Read-only. One summary email per scan. |

## Architecture

```text
                         AWS account
  ┌─────────────────────────────────────────────────────────────┐
  │                                                             │
  │   EC2 instance state change                                 │
  │              │                                              │
  │              ▼                                              │
  │        EventBridge  ──────► Tag Governance Lambda           │
  │                                  │                          │
  │                     DynamoDB findings + SNS (if remediated) │
  │                                                             │
  │   EventBridge Scheduler (19:30 America/New_York)            │
  │              │                                              │
  │              ▼                                              │
  │        Instance Scheduler Lambda  →  Stop if opted in       │
  │                                                             │
  │   EventBridge schedule (daily)                              │
  │              │                                              │
  │              ▼                                              │
  │        Orphan Scanner Lambda                                │
  │              │                                              │
  │        EBS / EIP / ENI → findings + one summary email       │
  │                                                             │
  └─────────────────────────────────────────────────────────────┘
```

Full map: [`architecture/architecture.md`](architecture/architecture.md). Design choices: [`architecture/decisions.md`](architecture/decisions.md).

## Repository layout

```text
src/tag_governance/           Tag governance Lambda
src/instance_scheduler/       Instance scheduler Lambda
src/orphan_scanner/           Orphan scanner Lambda
examples/                     Sample EventBridge and Scheduler events
terraform/bootstrap/          S3 + DynamoDB for remote Terraform state
terraform/lab/                Optional VPC + three tagged EC2 fixtures
terraform/platform/           Lambdas, IAM, EventBridge, DynamoDB, SNS
tests/unit/
```

## Prerequisites

- AWS account and credentials with rights to create the stacks
- Terraform >= 1.5
- Python 3.12 (for unit tests)
- Region: `us-east-1` (default; EventBridge EC2 events are regional)

## Deploy

Three **separate** Terraform states. Destroying lab or platform does not delete the state bucket.

**1. Remote state (once)**

```powershell
cd terraform/bootstrap
terraform init
terraform apply
```

Copy [`terraform/backend.hcl.example`](terraform/backend.hcl.example) to `terraform/backend.hcl` and set `bucket` to the bootstrap output (`aws-gov-tfstate-<account-id>`).

**2. Optional fixtures** (three instances so you can watch tags get fixed)

```powershell
cd terraform/lab
terraform init -backend-config=../backend.hcl
terraform apply
```

One instance is fully tagged. Two are missing required tags on purpose.

**3. Platform**

```powershell
cd terraform/platform
terraform init -backend-config=../backend.hcl
terraform apply -var="alert_email=you@example.com"
```

Confirm the SNS subscription email. Schedules default to **disabled**. Enable when you want them live:

```powershell
terraform apply -var="alert_email=you@example.com" -var="enable_stop_schedule=true" -var="enable_orphan_schedule=true"
```

## Tests

```powershell
pip install -r requirements-dev.txt
pytest
```

AWS APIs are mocked. Coverage includes missing vs present tags, scheduler stop filter, unattached EBS, unused EIP, and ambiguous ENI → `MANUAL_REVIEW`.

The same command runs in GitHub Actions on every push and pull request (`.github/workflows/test.yml`).

## Teardown

```powershell
cd terraform/lab; terraform destroy
cd terraform/platform; terraform destroy
```

Leave `terraform/bootstrap` applied if you still want remote state. S3 and the lock table have `prevent_destroy`. Remove that lifecycle block only if you intend to delete them.

## License and disclaimer

MIT License. Copyright (c) 2026 Edward Reyes Arroyo. See [`LICENSE`](LICENSE).

The code is provided **as is**, with no warranty. You can run these defaults as written. If you apply this in your own account, you are responsible for AWS charges, for what gets tagged or stopped, and for tearing it down.

The required tags and the 19:30 Eastern stop are this stack’s protocol, not a universal standard. Match them to yours before you enable schedules or aim this at real workloads:

| Default | Where to change it |
| --- | --- |
| Required tags `Owner`, `Environment`, `ManagedBy` | `src/tag_governance/handler.py` (`REQUIRED_TAGS`) |
| Stop opt-in tag `1930shutdown=true` plus `Lab=true` | `src/instance_scheduler/handler.py` |
| Stop at 19:30 `America/New_York` | `terraform/platform/eventbridge.tf` (`cron(30 19 * * ? *)` and timezone) |
| Daily orphan scan at 08:00 Eastern | same file (`orphan_daily`) |

Read the Terraform and IAM before you apply. Schedules start disabled. Stopped instances still bill for EBS — destroy `terraform/lab` when you no longer need the fixtures. Lambda, EventBridge, DynamoDB on-demand, and SNS stay cheap at this scale; the VMs do not.
