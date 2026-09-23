"""Backfill contact suppression keys from existing opted-out leads.

Default is a read-only dry run. Deploy the suppression table first, keep lead
intake and outreach paused, review the count, then pass --apply before resuming.
"""

import argparse
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Attr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.repositories.customer_suppressions import migration_marker_key, suppression_items
from app.repositories.customer_index import index_hmac_key_id, load_index_hmac_key


def is_legacy_suppression_key(key: str, tenant_id: str) -> bool:
    """Match only the old tenant#sha256(normalized-contact) key format."""
    parts = key.split("#")
    return (
        len(parts) == 2
        and parts[0] == tenant_id
        and len(parts[1]) == 64
        and all(character in "0123456789abcdef" for character in parts[1])
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--leads-table", required=True)
    parser.add_argument("--suppressions-table", required=True)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--index-secret-arn", required=True, help="Secrets Manager ARN used by the running API and worker")
    parser.add_argument("--apply", action="store_true", help="Write suppression entries; omitted means read-only dry run")
    args = parser.parse_args()
    if not args.tenant_id.strip() or "#" in args.tenant_id or len(args.tenant_id) > 128:
        parser.error("--tenant-id must be 1–128 characters and cannot contain '#' ")

    dynamodb = boto3.resource("dynamodb", region_name=args.region)
    index_hmac_key = load_index_hmac_key(args.index_secret_arn, args.region)
    leads = dynamodb.Table(args.leads_table)
    suppressions = dynamodb.Table(args.suppressions_table)
    if args.apply:
        # Fail closed during re-keying too: a prior completion marker may
        # describe unkeyed SHA-256 values or a different HMAC key.
        suppressions.delete_item(Key={"suppression_key": migration_marker_key(args.tenant_id)})
    scan_args = {
        "FilterExpression": Attr("tenant_id").eq(args.tenant_id) & Attr("lifecycle_status").eq("opted_out"),
        "ProjectionExpression": "lead_id, tenant_id, customer_email, customer_phone",
    }
    leads_scanned = opted_out_found = entries_written = entries_existing = 0
    while True:
        page = leads.scan(**scan_args)
        leads_scanned += page.get("ScannedCount", 0)
        for item in page.get("Items", []):
            opted_out_found += 1
            for marker in suppression_items(
                args.tenant_id,
                item["lead_id"],
                item.get("customer_email"),
                item.get("customer_phone"),
                hmac_key=index_hmac_key,
            ):
                if not args.apply:
                    entries_written += 1
                    continue
                try:
                    suppressions.put_item(
                        Item=marker,
                        ConditionExpression="attribute_not_exists(suppression_key)",
                    )
                    entries_written += 1
                except ClientError as exc:
                    if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                        raise
                    entries_existing += 1
        last_key = page.get("LastEvaluatedKey")
        if not last_key:
            break
        scan_args["ExclusiveStartKey"] = last_key

    legacy_scan = {
        "FilterExpression": Attr("tenant_id").eq(args.tenant_id),
        "ProjectionExpression": "suppression_key, tenant_id",
    }
    legacy_found = legacy_removed = 0
    while True:
        page = suppressions.scan(**legacy_scan)
        for item in page.get("Items", []):
            key = item.get("suppression_key", "")
            if not is_legacy_suppression_key(key, args.tenant_id):
                continue
            legacy_found += 1
            if args.apply:
                suppressions.delete_item(
                    Key={"suppression_key": key},
                    ConditionExpression="tenant_id = :tenant",
                    ExpressionAttributeValues={":tenant": args.tenant_id},
                )
                legacy_removed += 1
        last_key = page.get("LastEvaluatedKey")
        if not last_key:
            break
        legacy_scan["ExclusiveStartKey"] = last_key

    mode = "APPLIED" if args.apply else "DRY RUN"
    result = f"created {entries_written}" if args.apply else f"would create {entries_written}"
    legacy_result = f"removed {legacy_removed}" if args.apply else f"would remove {legacy_found}"
    print(f"{mode}: scanned {leads_scanned} lead records; found {opted_out_found} opted-out leads; {result} contact suppression keys; already present {entries_existing}; {legacy_result} legacy unkeyed suppression keys.")
    if args.apply:
        suppressions.put_item(
            Item={
                "suppression_key": migration_marker_key(args.tenant_id),
                "tenant_id": args.tenant_id,
                "record_type": "MIGRATION_COMPLETE",
                "index_key_scheme": "hmac-sha256-v1",
                "index_key_id": index_hmac_key_id(index_hmac_key),
            },
        )
        print("Customer opt-out backfill marked complete for this tenant.")


if __name__ == "__main__":
    main()
