import logging
import os
import uuid
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

from logging_utils import log_event

logger = logging.getLogger()
logger.setLevel(logging.INFO)

REQUIRED_TAGS = ("Owner", "Environment", "ManagedBy")
FINDINGS_TABLE = os.environ.get("FINDINGS_TABLE", "")
TOPIC_ARN = os.environ.get("ALERT_TOPIC_ARN", "")
REGION = os.environ.get("AWS_REGION", "us-east-1")

ec2 = boto3.client("ec2")
sns = boto3.client("sns")
findings = boto3.resource("dynamodb").Table(FINDINGS_TABLE) if FINDINGS_TABLE else None


def get_instance_id(event):
    """Official path: detail.instance-id (EC2 Instance State-change Notification)."""
    detail = event.get("detail") or {}
    instance_id = detail.get("instance-id")
    if isinstance(instance_id, str):
        instance_id = instance_id.strip()
        if instance_id:
            return instance_id
    return None


def tags_to_dict(tag_list):
    tags = {}
    for item in tag_list or []:
        key = item.get("Key")
        if key:
            tags[key] = item.get("Value") or ""
    return tags


def get_instance_tags(instance_id):
    response = ec2.describe_instances(InstanceIds=[instance_id])
    reservations = response.get("Reservations") or []
    if not reservations:
        return None
    instances = reservations[0].get("Instances") or []
    if not instances:
        return None
    return tags_to_dict(instances[0].get("Tags"))


def evaluate_tags(tags):
    missing = [key for key in REQUIRED_TAGS if not (tags.get(key) or "").strip()]
    if missing:
        return "MANUAL_REVIEW", missing
    return "COMPLIANT", []


def placeholder_keys(tags):
    return [
        key
        for key in REQUIRED_TAGS
        if (tags.get(key) or "").strip().lower() == "missing"
    ]


def add_missing_tags(instance_id, missing_keys):
    """Add only absent keys as missing. Never overwrite an existing tag."""
    if not missing_keys:
        return
    ec2.create_tags(
        Resources=[instance_id],
        Tags=[{"Key": key, "Value": "missing"} for key in missing_keys],
    )


def persist_finding(fields):
    if findings is None:
        return None
    item = {
        "resource_id": fields.get("resource_id") or "unknown",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "finding_id": str(uuid.uuid4()),
        "resource_type": "EC2",
        "rule_id": "required-tags",
        "status": fields["status"],
        "missing_tags": fields.get("missing_tags") or [],
        "action_taken": fields.get("action") or "",
        "reason": fields.get("reason") or "",
        "correlation_id": fields.get("correlation_id") or "",
        "region": REGION,
        "instance_id": fields.get("instance_id") or "",
        "owner": fields.get("owner") or "",
        "environment": fields.get("environment") or "",
        "managed_by": fields.get("managed_by") or "",
    }
    findings.put_item(Item=item)
    return item


def needs_email(status, tags):
    if status in ("ERROR", "MANUAL_REVIEW", "AUTO_REMEDIATED", "REMEDIATION_FAILED"):
        return True
    return bool(placeholder_keys(tags or {}))


def publish_alert(item):
    if not TOPIC_ARN:
        return
    subject = f"AWS Governance Alert: {item['status']}"
    body = "\n".join(
        [
            f"status: {item['status']}",
            f"instance: {item.get('instance_id')}",
            f"missing_tags: {item.get('missing_tags')}",
            f"owner: {item.get('owner')}",
            f"environment: {item.get('environment')}",
            f"managed_by: {item.get('managed_by')}",
            f"reason: {item.get('reason')}",
            f"correlation_id: {item.get('correlation_id')}",
        ]
    )
    sns.publish(TopicArn=TOPIC_ARN, Subject=subject[:100], Message=body)


def record(fields, tags=None):
    log_event(**fields)
    try:
        item = persist_finding(fields)
    except ClientError as err:
        log_event(
            status="ERROR",
            action="put_item",
            reason=err.response.get("Error", {}).get("Code", str(err)),
            instance_id=fields.get("instance_id"),
        )
        return
    if item and needs_email(fields["status"], tags):
        try:
            publish_alert(item)
        except ClientError as err:
            log_event(
                status="ERROR",
                action="sns_publish",
                reason=err.response.get("Error", {}).get("Code", str(err)),
                instance_id=fields.get("instance_id"),
            )


def lambda_handler(event, context):
    correlation_id = event.get("id")
    instance_id = get_instance_id(event)
    state = (event.get("detail") or {}).get("state")

    if instance_id is None:
        record(
            {
                "correlation_id": correlation_id,
                "event_id": correlation_id,
                "resource_id": None,
                "resource_type": "EC2",
                "status": "ERROR",
                "action": "extract_instance_id",
                "reason": "missing_detail.instance-id",
            }
        )
        return {"status": "ERROR", "instance_id": None}

    try:
        tags = get_instance_tags(instance_id)
    except ClientError as err:
        record(
            {
                "correlation_id": correlation_id,
                "event_id": correlation_id,
                "resource_id": instance_id,
                "instance_id": instance_id,
                "resource_type": "EC2",
                "state": state,
                "status": "ERROR",
                "action": "describe_instances",
                "reason": err.response.get("Error", {}).get("Code", str(err)),
            }
        )
        return {"status": "ERROR", "instance_id": instance_id}

    if tags is None:
        record(
            {
                "correlation_id": correlation_id,
                "event_id": correlation_id,
                "resource_id": instance_id,
                "instance_id": instance_id,
                "resource_type": "EC2",
                "state": state,
                "status": "ERROR",
                "action": "describe_instances",
                "reason": "instance_not_found",
            }
        )
        return {"status": "ERROR", "instance_id": instance_id}

    status, missing_tags = evaluate_tags(tags)

    if missing_tags:
        try:
            add_missing_tags(instance_id, missing_tags)
        except ClientError as err:
            record(
                {
                    "correlation_id": correlation_id,
                    "event_id": correlation_id,
                    "resource_id": instance_id,
                    "instance_id": instance_id,
                    "resource_type": "EC2",
                    "state": state,
                    "status": "REMEDIATION_FAILED",
                    "action": "create_tags",
                    "missing_tags": missing_tags,
                    "reason": err.response.get("Error", {}).get("Code", str(err)),
                    "owner": tags.get("Owner"),
                    "environment": tags.get("Environment"),
                    "managed_by": tags.get("ManagedBy"),
                },
                tags,
            )
            return {
                "status": "REMEDIATION_FAILED",
                "instance_id": instance_id,
                "missing_tags": missing_tags,
            }
        for key in missing_tags:
            tags[key] = "missing"
        status = "AUTO_REMEDIATED"

    record(
        {
            "correlation_id": correlation_id,
            "event_id": correlation_id,
            "resource_id": instance_id,
            "instance_id": instance_id,
            "resource_type": "EC2",
            "state": state,
            "status": status,
            "action": "evaluate_tags" if status == "COMPLIANT" else "create_tags",
            "missing_tags": missing_tags or placeholder_keys(tags),
            "owner": tags.get("Owner"),
            "environment": tags.get("Environment"),
            "managed_by": tags.get("ManagedBy"),
        },
        tags,
    )
    return {
        "status": status,
        "instance_id": instance_id,
        "missing_tags": missing_tags,
    }
