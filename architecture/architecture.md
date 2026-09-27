# Architecture

Event-driven AWS governance: tag enforcement on EC2 state change, an opt-in 19:30 stop, and a read-only orphan scan. Remediate only when the action is known and low risk. Record everything else for a human.

Never delete volumes, release Elastic IPs, delete ENIs, or terminate instances.

---

## 1. Overview

Three independent Lambda workloads share a findings table and an alert topic. They stay separate because they have different triggers, IAM needs, and failure modes.

```text
                         AWS account
  ┌─────────────────────────────────────────────────────────────┐
  │                                                             │
  │   EC2 instance state change                                 │
  │              │                                              │
  │              ▼                                              │
  │        EventBridge  ──────► Tag Governance Lambda           │
  │                                  │                          │
  │                     CloudWatch Logs                         │
  │                     DynamoDB findings                       │
  │                     SNS (AUTO_REMEDIATED only)              │
  │                                                             │
  │   EventBridge Scheduler (19:30 America/New_York)            │
  │              │                                              │
  │              ▼                                              │
  │        Instance Scheduler Lambda                            │
  │              │                                              │
  │        Stop only if Lab=true and 1930shutdown=true          │
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

### Tag rules

Required keys: `Owner`, `Environment`, `ManagedBy`.

If a required tag is **absent**, write that key with value `missing`. Do not guess `dev` or a person name. Do not overwrite a tag that already exists.

### Instance schedule tags

Times are **America/New_York**. Tag value must be `true` (case-sensitive). **Stop only** — never start, never terminate.

| Tags | At 19:30 |
| --- | --- |
| `Lab=true` and `1930shutdown=true` | Stop if running |
| either tag absent | ignore |

No 06:00 start job. IAM: `DescribeInstances` + `StopInstances` only (no `StartInstances`, no `CreateTags`).

---

## 2. Tag governance workflow

```text
EC2 Resource Change
        │
        ▼
   EventBridge
        │
        ▼
Tag Governance Lambda
        │
 Retrieve tags
        │
 Evaluate Owner / Environment / ManagedBy
        │
  COMPLIANT | AUTO_REMEDIATE | MANUAL_REVIEW
        │
 Safe tag write: absent keys get value missing
        │
 DynamoDB + SNS (remediation only) + metrics
```

EventBridge is **at-least-once**. The same event `id` can be delivered more than once. A launch also produces **two different events**: `pending` then `running`. Findings are keyed so retries do not spam email.

---

## 3. Orphan scanner workflow

```text
EventBridge schedule (every 24h)
        │
        ▼
Orphan Scanner Lambda
        │
 Discover unattached EBS, unused EIPs, ambiguous ENIs
        │
 Classify: OBSERVE / MANUAL_REVIEW / CLEANUP_CANDIDATE
        │
 DynamoDB findings + one summary SNS email
```

The scanner is read-only. It never deletes. An ENI in `available` is not proof it is safe to remove (AWS-managed interfaces, Lambda, NAT, VPC endpoints).

---

## 4. EC2 event source

Native EC2 service event, not CloudTrail.

| Field | Value |
| --- | --- |
| Event bus | default |
| `source` | `aws.ec2` |
| `detail-type` | `EC2 Instance State-change Notification` |
| CloudTrail required? | **No** |
| Instance ID path | `detail.instance-id` |

EC2 publishes this event when an instance enters `pending`, `running`, `stopping`, `stopped`, `shutting-down`, or `terminated`. See [State change events for Amazon EC2 instances](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/monitoring-instance-state-changes.html).

CloudTrail `RunInstances` / `CreateTags` would be the right source for “who tagged what.” That needs a trail, a nested JSON path, and can omit `responseElements` when the payload is too large. Launch already produces native state-change events, which is enough to evaluate tags.

### EventBridge filter

```json
{
  "source": ["aws.ec2"],
  "detail-type": ["EC2 Instance State-change Notification"]
}
```

No instance-id or state filter, so launch, stop, and terminate all invoke the function.

### Example event

```json
{
  "id": "7bf73129-1428-4cd3-a780-95db273d1602",
  "detail-type": "EC2 Instance State-change Notification",
  "source": "aws.ec2",
  "account": "123456789012",
  "time": "2021-11-11T21:29:54Z",
  "region": "us-east-1",
  "resources": [
    "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0"
  ],
  "detail": {
    "instance-id": "i-1234567890abcdef0",
    "state": "pending"
  }
}
```

---

## 5. Lambda responsibilities

### Tag governance

| Function | |
| --- | --- |
| Receive EventBridge event | yes |
| Extract `detail.instance-id` | yes |
| Structured CloudWatch log | yes |
| Describe instance tags | yes |
| Evaluate Owner / Environment / ManagedBy | yes |
| Write absent tags as `missing` | yes |
| DynamoDB findings + SNS on AUTO_REMEDIATED | yes |

Handler coordinates. `get_instance_id()` owns event parsing. Logging is separate from storage and notification.

### Instance scheduler

Reads `action` from the Scheduler payload. If `action != stop`, skip. Otherwise describe instances with the opt-in filters and call `StopInstances`.

### Orphan scanner

Describe EBS / EIP / ENI, classify, write findings, send one summary. No mutate APIs.

---

## 6. IAM

Least privilege per function. No `ec2:*`, no `Action = "*"`.

**Tag governance execution role**

- `logs:CreateLogStream`, `logs:PutLogEvents` on its log group
- `ec2:DescribeInstances`, `ec2:DescribeTags`
- `ec2:CreateTags` on instances in this account/region
- `dynamodb:PutItem` on the findings table
- `sns:Publish` on the alert topic

**Instance scheduler execution role**

- Own log group
- `ec2:DescribeInstances`
- `ec2:StopInstances`

**Orphan scanner execution role**

- Own log group
- Describe volumes, addresses, network interfaces
- `dynamodb:PutItem`, `sns:Publish`

**EventBridge → Lambda:** resource-based `lambda:InvokeFunction` from the rule ARN (`aws_lambda_permission`).

---

## 7. Terraform stacks and remote state

Three **separate** states. Destroying one never deletes the others.

| Folder | What it owns | State lives |
| --- | --- | --- |
| `terraform/bootstrap` | S3 bucket `aws-gov-tfstate-<account-id>` + DynamoDB lock table | Local (gitignored). First apply cannot use S3 yet. |
| `terraform/lab` | Lab VPC + three EC2 fixtures | S3 key `lab/terraform.tfstate` |
| `terraform/platform` | Lambdas, findings table, SNS, schedules | S3 key `platform/terraform.tfstate` |

Lab and platform do **not** take a Terraform variable for the bucket. They use an S3 **backend**.

1. Shared settings are in `terraform/backend.hcl` (copy from `backend.hcl.example`).
2. Each stack names its object in `providers.tf`:

```hcl
backend "s3" {
  key = "platform/terraform.tfstate"   # lab uses lab/terraform.tfstate
}
```

3. Init after clone:

```powershell
cd terraform/platform
terraform init -backend-config=../backend.hcl
```

S3 and the lock table have `prevent_destroy = true`. Only a bootstrap destroy (after removing that lifecycle) can delete the bucket.

```text
terraform/
├── backend.hcl.example  # copy to backend.hcl; set bucket
├── bootstrap/           # creates the bucket; local state
├── lab/
└── platform/
```

---

## 8. Console locations

Same region as Terraform (default `us-east-1`).

| What | Console path |
| --- | --- |
| Tag governance | Lambda → `aws-gov-tag-governance` |
| Scheduler | Lambda → `aws-gov-instance-scheduler` |
| Orphan scanner | Lambda → `aws-gov-orphan-scanner` |
| Logs | CloudWatch → `/aws/lambda/aws-gov-tag-governance` |
| EventBridge rule | EventBridge → Rules → `aws-gov-ec2-state-change` |
| Stop schedule | EventBridge → Schedules → `aws-gov-stop-1930` |
| Findings | DynamoDB → `aws-gov-findings` |
| Alerts | SNS → `aws-gov-alerts` |
| Lab instances | EC2 → `aws-gov-lab-compliant`, `aws-gov-lab-missing-managedby`, `aws-gov-lab-missing-owner-env` |

---

## Component notes

### EventBridge

Rules match events on a bus and invoke targets. Here: EC2 state changes → tag Lambda; Scheduler cron → stop Lambda; daily schedule → scanner. Failures: pattern mismatch (no invoke), missing `lambda:InvokeFunction` (`FailedInvocations`), Lambda errors (retries). Troubleshoot rule metrics, then Lambda logs.

### Lambda

Short, event-driven work. Failures: timeout, unhandled exception, IAM `AccessDenied`. Troubleshoot CloudWatch logs and the function Monitor tab.

### IAM

The execution role is what Lambda uses at runtime. EventBridge invokes via the function resource policy. Compare AccessDenied action/resource to the role policy.

### CloudWatch Logs

Lambda writes to `/aws/lambda/<name>`. Confirm region, then newest stream timestamp vs the EC2 state-change time.
