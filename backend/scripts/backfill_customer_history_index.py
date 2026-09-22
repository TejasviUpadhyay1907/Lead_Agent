"""Backfill customer-history GSI keys before deploying indexed history reads.

Run from the deployment environment with least-privilege DynamoDB Scan and
UpdateItem access. Defaults to dry-run; pass --apply to write the keys.
"""

import argparse
import hashlib
import re

import boto3
from boto3.dynamodb.conditions import Attr


def digest_key(tenant_id: str, kind: str, value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower() if kind == "email" else re.sub(r"\D", "", value)
    if not normalized:
        return None
    return f"{tenant_id}#{hashlib.sha256(normalized.encode('utf-8')).hexdigest()}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--table", required=True, help="Leads DynamoDB table name")
    parser.add_argument("--tenant-id", help="Only backfill this tenant; defaults to every tenant")
    parser.add_argument("--region", help="AWS region; defaults to the boto3 region chain")
    parser.add_argument("--apply", action="store_true", help="Write keys (without this flag, only count changes)")
    args = parser.parse_args()

    table = boto3.resource("dynamodb", region_name=args.region).Table(args.table)
    scan_args = {"ProjectionExpression": "lead_id, tenant_id, customer_email, customer_phone"}
    if args.tenant_id:
        scan_args["FilterExpression"] = Attr("tenant_id").eq(args.tenant_id)

    scanned = changed = 0
    while True:
        page = table.scan(**scan_args)
        for item in page.get("Items", []):
            scanned += 1
            email_key = digest_key(item["tenant_id"], "email", item.get("customer_email"))
            phone_key = digest_key(item["tenant_id"], "phone", item.get("customer_phone"))
            updates = {"tenant_email_key": email_key, "tenant_phone_key": phone_key}
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


if __name__ == "__main__":
    main()
