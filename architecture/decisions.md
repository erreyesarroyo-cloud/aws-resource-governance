# Architecture decisions

## Why Lambda?

The work is short, event-driven, and idle most of the day. Lambda scales to zero, fits EventBridge as a target, and matches how AWS governance automation is usually built. It is a poor fit if a scan cannot finish before the timeout (orphan inventory across many accounts). Then Step Functions or a container job is the next step.

## Why EventBridge?

EC2 already emits state-change events onto the default bus. A rule is the least moving parts between “instance launched” and “run this function.” Polling `DescribeInstances` on a schedule would miss nothing important for tags, but it would be slower, costlier, and worse as an event-driven pattern.

## Why not CloudTrail for the tag path?

Native `EC2 Instance State-change Notification` events include `detail.instance-id`, need no trail, and fire on launch. CloudTrail `RunInstances` / `CreateTags` are the right source for “who tagged what,” but they add a trail, a nested JSON path, and payload-size holes. Revisit CloudTrail when tag-change attribution matters.

## Why three Lambda functions?

Tag governance is real-time and writes tags. The scheduler stops opted-in instances at wall-clock time. The orphan scanner is scheduled and must stay read-only. Splitting them keeps IAM honest: the scanner never gets `CreateTags` or `StopInstances`; tag governance never gets `StopInstances`.

## Why a separate instance-schedule Lambda?

Start/stop at wall-clock time cannot hang off EC2 state-change events. Those fire when the instance already moved, not at 19:30. A timezone-aware EventBridge Scheduler (`America/New_York`) plus an opt-in tag is deterministic and low risk.

## Why no automatic deletion?

Unused does not mean safe to destroy. AWS-managed ENIs, volumes you meant to keep, and Elastic IPs on a maintenance window all look “orphaned.” The scanner records `CLEANUP_CANDIDATE` and stops.

## Why Terraform in three stacks?

Bootstrap cannot store its own state in the bucket it is creating. Lab fixtures and the platform have different lifetimes: you destroy VMs to stop EBS charges and leave the Lambdas, or the reverse. Separate state files make that safe. Remote state (S3 + DynamoDB lock) is so a later apply does not depend on a laptop `.tfstate`.

## Where this stops scaling

- One Lambda scanning hundreds of accounts will time out.
- Multi-region needs stacked rules or an organization-wide aggregator.
- Complex approvals belong in Step Functions or a ticketing workflow.
- Fleet-wide config history is what AWS Config and Security Hub are for.

Those are different problems. This stack is one account, one region, and no automatic delete.
