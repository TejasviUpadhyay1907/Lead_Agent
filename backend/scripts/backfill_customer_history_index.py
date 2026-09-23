"""Backfill customer-history GSI keys before deploying indexed history reads.

Run for one isolated customer with least-privilege DynamoDB access. Defaults to
dry-run; pass --apply to re-key the history indexes and write the migration marker.
"""

import argparse
import sys
from pathlib import Path

import boto3
from boto3.dynamodb.conditions import Attr
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.repositories.customer_index import customer_index_keys, index_hmac_key_id, load_index_hmac_key
from app.repositories.customer_suppressions import history_index_marker_key


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--table", required=True, help="Leads DynamoDB table name")
    parser.add_argument("--tenant-id", required=True, help="Tenant ID for this isolated customer deployment")
    parser.add_argument("--region", help="AWS region; defaults to the boto3 region chain")
    parser.add_argument("--index-secret-arn", required=True, help="Secrets Manager ARN used by the running API and worker")
    parser.add_argument("--suppressions-table", required=True, help="CustomerSuppressionsTable used for the migration marker")
    parser.add_argument("--apply", action="store_true", help="Write keys (without this flag, only count changes)")
    args = parser.parse_args()

    index_hmac_key = load_index_hmac_key(args.index_secret_arn, args.region)
    dynamodb = boto3.resource("dynamodb", region_name=args.region)
    table = dynamodb.Table(args.table)
    suppressions = dynamodb.Table(args.suppressions_table)
    scan_args = {"ProjectionExpression": "lead_id, tenant_id, customer_email, customer_phone"}
    scan_args["FilterExpression"] = Attr("tenant_id").eq(args.tenant_id)

    if args.apply:
        # Removing the marker prevents readiness while indexes are re-keyed.
        suppressions.delete_item(
            Key={"suppression_key": history_index_marker_key(args.tenant_id)}
        )

    scanned = changed = 0
    while True:
        page = table.scan(**scan_args)
        for item in page.get("Items", []):
            scanned += 1
            updates = customer_index_keys(
                item["tenant_id"],
                item.get("customer_email"),
                item.get("customer_phone"),
                hmac_key=index_hmac_key,
            )
            if all(item.get(key) == value for key, value in updates.items()):
                continue
            changed += 1
            if args.apply:
                names, values, sets, removes = {}, {}, [], []
                for name, value in updates.items():
                    token = "#" + name
                    names[token] = name
                    if value:
                        value_token = ":" + name
                        values[value_token] = value
                        sets.append(f"{token} = {value_token}")
                    else:
                        removes.append(token)
                expression = ("SET " + ", ".join(sets) if sets else "")
                if removes:
                    expression += (" " if expression else "") + "REMOVE " + ", ".join(removes)
                update_args = {
                    "Key": {"lead_id": item["lead_id"]},
                    "UpdateExpression": expression,
                    "ExpressionAttributeNames": names,
                    "ConditionExpression": Attr("tenant_id").eq(item["tenant_id"]),
                }
                if values:
                    update_args["ExpressionAttributeValues"] = values
                table.update_item(**update_args)
        last_key = page.get("LastEvaluatedKey")
        if not last_key:
            break
        scan_args["ExclusiveStartKey"] = last_key

    mode = "updated" if args.apply else "would update"
    print(f"Scanned {scanned} leads; {mode} {changed} customer-index records.")
    if args.apply:
        suppressions.put_item(
            Item={
                "suppression_key": history_index_marker_key(args.tenant_id),
                "tenant_id": args.tenant_id,
                "record_type": "CUSTOMER_HISTORY_INDEX_COMPLETE",
                "index_key_scheme": "hmac-sha256-v1",
                "index_key_id": index_hmac_key_id(index_hmac_key),
            }
        )
        print("Customer-history index migration marked complete for this tenant and HMAC key.")


if __name__ == "__main__":
    main()
