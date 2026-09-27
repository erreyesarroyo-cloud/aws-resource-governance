from pathlib import Path
import importlib.util
import json
from unittest.mock import patch

import pytest
from botocore.exceptions import ClientError

SRC = Path(__file__).resolve().parents[2] / "src" / "tag_governance"
EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "ec2-state-change.json"


def _load():
    import sys

    sys.path.insert(0, str(SRC))
    spec = importlib.util.spec_from_file_location("tag_governance_handler", SRC / "handler.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


handler = _load()


def _error(code):
    return ClientError({"Error": {"Code": code, "Message": code}}, "Op")


def _describe(tags):
    return {
        "Reservations": [
            {"Instances": [{"Tags": [{"Key": k, "Value": v} for k, v in tags.items()]}]}
        ]
    }


@pytest.fixture
def state_change_event():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def test_get_instance_id_from_official_event_shape(state_change_event):
    assert handler.get_instance_id(state_change_event) == "i-1234567890abcdef0"


def test_get_instance_id_missing_detail():
    assert handler.get_instance_id({"id": "abc"}) is None


def test_evaluate_compliant():
    status, missing = handler.evaluate_tags(
        {"Owner": "lab", "Environment": "dev", "ManagedBy": "GovernancePlatform"}
    )
    assert status == "COMPLIANT"
    assert missing == []


def test_evaluate_missing_managedby():
    status, missing = handler.evaluate_tags({"Owner": "lab", "Environment": "dev"})
    assert status == "MANUAL_REVIEW"
    assert missing == ["ManagedBy"]


def test_evaluate_missing_owner_and_environment():
    status, missing = handler.evaluate_tags({"ManagedBy": "GovernancePlatform"})
    assert missing == ["Owner", "Environment"]


@patch.object(handler, "findings")
@patch.object(handler, "sns")
@patch.object(handler, "ec2")
def test_handler_compliant_no_create_tags(ec2, sns, findings, state_change_event):
    handler.FINDINGS_TABLE = "t"
    handler.TOPIC_ARN = "arn:aws:sns:us-east-1:1:t"
    findings.put_item.return_value = {}
    ec2.describe_instances.return_value = _describe(
        {"Owner": "lab", "Environment": "dev", "ManagedBy": "GovernancePlatform"}
    )
    result = handler.lambda_handler(state_change_event, None)
    assert result["status"] == "COMPLIANT"
    ec2.create_tags.assert_not_called()
    sns.publish.assert_not_called()
    findings.put_item.assert_called_once()


@patch.object(handler, "findings")
@patch.object(handler, "sns")
@patch.object(handler, "ec2")
def test_handler_missing_managedby_writes_missing(ec2, sns, findings, state_change_event):
    handler.FINDINGS_TABLE = "t"
    handler.TOPIC_ARN = "arn:aws:sns:us-east-1:1:t"
    findings.put_item.return_value = {}
    ec2.describe_instances.return_value = _describe({"Owner": "lab", "Environment": "dev"})
    result = handler.lambda_handler(state_change_event, None)
    assert result["status"] == "AUTO_REMEDIATED"
    assert result["missing_tags"] == ["ManagedBy"]
    ec2.create_tags.assert_called_once()
    tags = ec2.create_tags.call_args.kwargs["Tags"]
    assert tags == [{"Key": "ManagedBy", "Value": "missing"}]
    sns.publish.assert_called_once()


@patch.object(handler, "findings")
@patch.object(handler, "sns")
@patch.object(handler, "ec2")
def test_handler_describe_failure(ec2, sns, findings, state_change_event):
    handler.FINDINGS_TABLE = "t"
    handler.TOPIC_ARN = "arn:aws:sns:us-east-1:1:t"
    findings.put_item.return_value = {}
    ec2.describe_instances.side_effect = _error("UnauthorizedOperation")
    result = handler.lambda_handler(state_change_event, None)
    assert result["status"] == "ERROR"
    sns.publish.assert_called_once()


@patch.object(handler, "findings")
@patch.object(handler, "sns")
@patch.object(handler, "ec2")
def test_handler_create_tags_failure(ec2, sns, findings, state_change_event):
    handler.FINDINGS_TABLE = "t"
    handler.TOPIC_ARN = "arn:aws:sns:us-east-1:1:t"
    findings.put_item.return_value = {}
    ec2.describe_instances.return_value = _describe({})
    ec2.create_tags.side_effect = _error("UnauthorizedOperation")
    result = handler.lambda_handler(state_change_event, None)
    assert result["status"] == "REMEDIATION_FAILED"


def test_handler_missing_instance_id():
    result = handler.lambda_handler({"id": "evt-1", "detail": {}}, None)
    assert result["status"] == "ERROR"
    assert result["instance_id"] is None
