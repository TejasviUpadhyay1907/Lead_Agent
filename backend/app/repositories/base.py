"""
LeadRescue AI — Base Repository & Memory Repository Implementations

Provides in-memory repositories for local testing when AWS credentials/DynamoDB
are not present, while supporting boto3 DynamoDB persistence in production.
"""

from typing import Dict, List, Optional
import boto3
from botocore.exceptions import BotoCoreError, ClientError
from app.config.settings import settings


def get_boto3_dynamodb_resource():
    """Helper to get a boto3 DynamoDB resource safely."""
    try:
        if settings.aws_region:
            return boto3.resource("dynamodb", region_name=settings.aws_region)
        return boto3.resource("dynamodb")
    except Exception:
        return None
