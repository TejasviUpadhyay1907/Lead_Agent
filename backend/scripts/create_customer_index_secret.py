"""Create a per-deployment HMAC key without printing or writing its value locally."""

import argparse
import json


def create_customer_index_secret(secrets_client, name: str, kms_key_id: str | None = None) -> str:
    """Generate a high-entropy key in Secrets Manager and return only its ARN."""
    generated = secrets_client.get_random_password(
        PasswordLength=64,
        ExcludePunctuation=True,
    )
    hmac_key = generated.get("RandomPassword")
    if not isinstance(hmac_key, str) or len(hmac_key.encode("utf-8")) < 32:
        raise RuntimeError("Secrets Manager did not return a valid customer index key")

    request = {
        "Name": name,
        "Description": "LeadRescue customer contact-index HMAC key. Do not rotate without both data backfills.",
        "SecretString": json.dumps(
            {
                "purpose": "LeadRescue customer index HMAC key",
                "hmac_key": hmac_key,
            }
        ),
    }
    if kms_key_id:
        request["KmsKeyId"] = kms_key_id
    response = secrets_client.create_secret(**request)
    arn = response.get("ARN")
    if not isinstance(arn, str) or not arn:
        raise RuntimeError("Secrets Manager created no ARN for the customer index key")
    return arn


def main() -> int:
    import boto3
    from botocore.config import Config

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True, help="New secret name, unique within the AWS account/Region")
    parser.add_argument("--region", required=True, help="Same AWS Region as the LeadRescue stack")
    parser.add_argument("--kms-key-id", help="Optional customer-managed KMS key ID or ARN")
    args = parser.parse_args()

    client = boto3.client(
        "secretsmanager",
        region_name=args.region,
        config=Config(connect_timeout=3, read_timeout=5, retries={"total_max_attempts": 2}),
    )
    create_customer_index_secret(client, args.name, args.kms_key_id)
    print("Customer index secret created successfully in Secrets Manager.")
    print("Retrieve its ARN from Secrets Manager when configuring the deployment.")
    print("Secret value was not printed or written to a local file.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
