import json
import logging

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ec2 = boto3.client("ec2")

LAB_TAG = {"Name": "tag:Lab", "Values": ["true"]}
SHUTDOWN_TAG = {"Name": "tag:1930shutdown", "Values": ["true"]}
RUNNING = {"Name": "instance-state-name", "Values": ["running"]}


def log_event(**fields):
    logger.info(json.dumps(fields, default=str))


def find_stop_targets():
    response = ec2.describe_instances(Filters=[LAB_TAG, SHUTDOWN_TAG, RUNNING])
    instance_ids = []
    for reservation in response.get("Reservations") or []:
        for instance in reservation.get("Instances") or []:
            instance_ids.append(instance["InstanceId"])
    return instance_ids


def lambda_handler(event, context):
    action = (event or {}).get("action")
    if action != "stop":
        log_event(
            status="SKIPPED",
            action=action,
            reason="scheduler_only_stops",
        )
        return {"status": "SKIPPED", "action": action, "stopped": []}

    try:
        instance_ids = find_stop_targets()
    except ClientError as err:
        log_event(
            status="ERROR",
            action="describe_instances",
            reason=err.response.get("Error", {}).get("Code", str(err)),
        )
        return {"status": "ERROR", "stopped": []}

    if not instance_ids:
        log_event(
            status="NO_TARGETS",
            action="stop",
            reason="no_running_lab_instances_with_1930shutdown_true",
        )
        return {"status": "NO_TARGETS", "stopped": []}

    try:
        ec2.stop_instances(InstanceIds=instance_ids)
    except ClientError as err:
        log_event(
            status="ERROR",
            action="stop_instances",
            instance_ids=instance_ids,
            reason=err.response.get("Error", {}).get("Code", str(err)),
        )
        return {"status": "ERROR", "stopped": []}

    log_event(status="STOPPED", action="stop", instance_ids=instance_ids)
    return {"status": "STOPPED", "stopped": instance_ids}
