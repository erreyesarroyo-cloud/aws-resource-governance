import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def log_event(**fields):
    logger.info(json.dumps(fields, default=str))
