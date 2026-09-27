from pathlib import Path
import importlib.util
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

SRC = Path(__file__).resolve().parents[2] / "src" / "orphan_scanner"
NOW = datetime(2026, 9, 26, tzinfo=timezone.utc)


def _load():
    spec = importlib.util.spec_from_file_location("orphan_scanner_handler", SRC / "handler.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


handler = _load()


def test_ebs_age_observe():
    status, days = handler.classify_ebs_age(NOW - timedelta(days=2), now=NOW)
    assert status == "OBSERVE"
    assert days == 2


def test_ebs_age_manual_review():
    status, days = handler.classify_ebs_age(NOW - timedelta(days=10), now=NOW)
    assert status == "MANUAL_REVIEW"
    assert days == 10


def test_ebs_age_cleanup():
    status, days = handler.classify_ebs_age(NOW - timedelta(days=40), now=NOW)
    assert status == "CLEANUP_CANDIDATE"


def test_eni_lambda_is_aws_owned():
    assert handler.eni_is_aws_owned(
        {"Description": "AWS Lambda VPC ENI-abc", "Status": "available"}
    )


def test_eni_unclear_owner_not_aws():
    assert not handler.eni_is_aws_owned(
        {"Description": "lab leftover", "Status": "available", "RequesterManaged": False}
    )


@patch.object(handler, "sns")
@patch.object(handler, "findings")
@patch.object(handler, "ec2")
def test_scan_unattached_ebs_and_skip_associated_eip(ec2, findings, sns):
    handler.FINDINGS_TABLE = "t"
    handler.TOPIC_ARN = "arn:aws:sns:us-east-1:1:t"
    findings.put_item.return_value = {}

    ebs_page = {
        "Volumes": [
            {
                "VolumeId": "vol-1",
                "Size": 8,
                "VolumeType": "gp3",
                "AvailabilityZone": "us-east-1a",
                "CreateTime": NOW - timedelta(days=40),
            }
        ]
    }
    eni_page = {
        "NetworkInterfaces": [
            {
                "NetworkInterfaceId": "eni-lambda",
                "Description": "AWS Lambda VPC ENI",
                "Status": "available",
            },
            {
                "NetworkInterfaceId": "eni-mystery",
                "Description": "old lab nic",
                "Status": "available",
                "RequesterManaged": False,
            },
            {
                "NetworkInterfaceId": "eni-attached",
                "Status": "in-use",
                "Attachment": {"InstanceId": "i-1"},
            },
        ]
    }

    def paginate_for(name):
        mock = MagicMock()
        if name == "describe_volumes":
            mock.paginate.return_value = [ebs_page]
        else:
            mock.paginate.return_value = [eni_page]
        return mock

    ec2.get_paginator.side_effect = paginate_for
    ec2.describe_addresses.return_value = {
        "Addresses": [
            {"AllocationId": "eipalloc-used", "AssociationId": "eipassoc-1", "PublicIp": "1.1.1.1"},
            {"AllocationId": "eipalloc-free", "PublicIp": "2.2.2.2"},
        ]
    }

    result = handler.lambda_handler({}, None)
    assert result["status"] == "SCAN_COMPLETE"
    assert result["counts"]["EBS"] == 1
    assert result["counts"]["EIP"] == 1
    assert result["counts"]["ENI"] == 1
    sns.publish.assert_called_once()
    assert "orphan scan summary" in sns.publish.call_args.kwargs["Subject"]
