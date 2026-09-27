import json
import logging
import os
import uuid
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

FINDINGS_TABLE = os.environ.get("FINDINGS_TABLE", "")
TOPIC_ARN = os.environ.get("ALERT_TOPIC_ARN", "")
REGION = os.environ.get("AWS_REGION", "us-east-1")

ec2 = boto3.client("ec2")
sns = boto3.client("sns")
findings = boto3.resource("dynamodb").Table(FINDINGS_TABLE) if FINDINGS_TABLE else None

AWS_ENI_MARKERS = (
    "AWS Lambda",
    "ELB ",
    "Amazon EKS",
    "RDSNetworkInterface",
    "VPC Endpoint",
    "Interface for NAT Gateway",
    "DMSNetworkInterface",
)

AWS_ENI_TYPES = {
    "lambda",
    "nat_gateway",
    "efa",
    "trunk",
    "network_load_balancer",
    "gateway_load_balancer",
    "vpc_endpoint",
}


def log_event(**fields):
    logger.info(json.dumps(fields, default=str))


def classify_ebs_age(create_time, now=None):
    now = now or datetime.now(timezone.utc)
    if create_time.tzinfo is None:
        create_time = create_time.replace(tzinfo=timezone.utc)
    age_days = (now - create_time).days
    if age_days < 7:
        return "OBSERVE", age_days
    if age_days <= 30:
        return "MANUAL_REVIEW", age_days
    return "CLEANUP_CANDIDATE", age_days


def eni_is_aws_owned(eni):
    if eni.get("RequesterManaged"):
        return True
    interface_type = (eni.get("InterfaceType") or "").lower()
    if interface_type in AWS_ENI_TYPES:
        return True
    description = eni.get("Description") or ""
    return any(marker in description for marker in AWS_ENI_MARKERS)


def persist_finding(item):
    if findings is None:
        return
    findings.put_item(Item=item)


def finding_base(resource_id, resource_type, status, **extra):
    item = {
        "resource_id": resource_id,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "finding_id": str(uuid.uuid4()),
        "resource_type": resource_type,
        "rule_id": "orphan-scan",
        "status": status,
        "region": REGION,
        "action_taken": "scan",
        "reason": extra.pop("reason", ""),
    }
    item.update(extra)
    return item


def scan_ebs():
    found = []
    paginator = ec2.get_paginator("describe_volumes")
    for page in paginator.paginate(Filters=[{"Name": "status", "Values": ["available"]}]):
        for volume in page.get("Volumes") or []:
            status, age_days = classify_ebs_age(volume["CreateTime"])
            item = finding_base(
                volume["VolumeId"],
                "EBS",
                status,
                size_gb=volume.get("Size"),
                volume_type=volume.get("VolumeType"),
                availability_zone=volume.get("AvailabilityZone"),
                age_days=age_days,
                reason="unattached_volume",
            )
            persist_finding(item)
            found.append(item)
    return found


def scan_eips():
    found = []
    response = ec2.describe_addresses()
    for address in response.get("Addresses") or []:
        if address.get("AssociationId"):
            continue
        allocation_id = address.get("AllocationId") or address.get("PublicIp")
        item = finding_base(
            allocation_id,
            "EIP",
            "MANUAL_REVIEW",
            public_ip=address.get("PublicIp"),
            association_id=address.get("AssociationId") or "",
            network_interface_id=address.get("NetworkInterfaceId") or "",
            reason="unassociated_eip",
        )
        persist_finding(item)
        found.append(item)
    return found


def scan_enis():
    found = []
    paginator = ec2.get_paginator("describe_network_interfaces")
    for page in paginator.paginate():
        for eni in page.get("NetworkInterfaces") or []:
            if eni.get("Attachment"):
                continue
            if eni_is_aws_owned(eni):
                continue
            if (eni.get("Status") or "") != "available":
                continue
            item = finding_base(
                eni["NetworkInterfaceId"],
                "ENI",
                "MANUAL_REVIEW",
                description=eni.get("Description") or "",
                interface_type=eni.get("InterfaceType") or "",
                reason="available_eni_owner_unclear",
            )
            persist_finding(item)
            found.append(item)
    return found


def publish_summary(counts, errors):
    if not TOPIC_ARN:
        return
    lines = [
        "Orphan scanner summary",
        f"EBS: {counts.get('EBS', 0)}",
        f"EIP: {counts.get('EIP', 0)}",
        f"ENI: {counts.get('ENI', 0)}",
    ]
    if errors:
        lines.append("errors: " + "; ".join(errors))
    sns.publish(
        TopicArn=TOPIC_ARN,
        Subject="AWS Governance: orphan scan summary",
        Message="\n".join(lines),
    )


def lambda_handler(event, context):
    errors = []
    results = {"EBS": [], "EIP": [], "ENI": []}

    try:
        results["EBS"] = scan_ebs()
    except ClientError as err:
        errors.append("ebs:" + err.response.get("Error", {}).get("Code", str(err)))

    try:
        results["EIP"] = scan_eips()
    except ClientError as err:
        errors.append("eip:" + err.response.get("Error", {}).get("Code", str(err)))

    try:
        results["ENI"] = scan_enis()
    except ClientError as err:
        errors.append("eni:" + err.response.get("Error", {}).get("Code", str(err)))

    counts = {key: len(value) for key, value in results.items()}
    log_event(status="SCAN_COMPLETE", counts=counts, errors=errors)
    try:
        publish_summary(counts, errors)
    except ClientError as err:
        log_event(
            status="ERROR",
            action="sns_publish",
            reason=err.response.get("Error", {}).get("Code", str(err)),
        )

    return {
        "status": "ERROR" if errors else "SCAN_COMPLETE",
        "counts": counts,
        "errors": errors,
    }
