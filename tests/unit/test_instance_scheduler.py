from pathlib import Path
import importlib.util
from unittest.mock import patch

from botocore.exceptions import ClientError

SRC = Path(__file__).resolve().parents[2] / "src" / "instance_scheduler"


def _load():
    spec = importlib.util.spec_from_file_location("instance_scheduler_handler", SRC / "handler.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


handler = _load()


def test_skips_without_stop_action():
    result = handler.lambda_handler({"action": "start"}, None)
    assert result["status"] == "SKIPPED"
    assert result["stopped"] == []


@patch.object(handler, "ec2")
def test_stops_only_lab_shutdown_running(ec2):
    ec2.describe_instances.return_value = {
        "Reservations": [
            {
                "Instances": [
                    {"InstanceId": "i-aaaa"},
                    {"InstanceId": "i-bbbb"},
                ]
            }
        ]
    }
    result = handler.lambda_handler({"action": "stop"}, None)
    assert result["status"] == "STOPPED"
    assert result["stopped"] == ["i-aaaa", "i-bbbb"]
    ec2.stop_instances.assert_called_once_with(InstanceIds=["i-aaaa", "i-bbbb"])


@patch.object(handler, "ec2")
def test_no_targets(ec2):
    ec2.describe_instances.return_value = {"Reservations": []}
    result = handler.lambda_handler({"action": "stop"}, None)
    assert result["status"] == "NO_TARGETS"
    ec2.stop_instances.assert_not_called()


@patch.object(handler, "ec2")
def test_stop_failure(ec2):
    ec2.describe_instances.return_value = {
        "Reservations": [{"Instances": [{"InstanceId": "i-aaaa"}]}]
    }
    ec2.stop_instances.side_effect = ClientError(
        {"Error": {"Code": "UnauthorizedOperation", "Message": "no"}},
        "StopInstances",
    )
    result = handler.lambda_handler({"action": "stop"}, None)
    assert result["status"] == "ERROR"
