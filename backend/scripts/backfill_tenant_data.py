"""Backfill tenant attributes for an existing isolated DynamoDB deployment.

Run once per customer, after the tenant GSIs are ACTIVE and before routing the
production API to the new code. The default is a read-only count; pass --apply
to write. Existing records assigned to another tenant cause a hard failure.
"""

import argparse
import os

import boto3
from botocore.exceptions import ClientError


def scan_all(table):
    args = {}
    while True:
        response = table.scan(**args)
        yield from response.get("Items", [])
        key = response.get("LastEvaluatedKey")
        if not key:
            break
        args["ExclusiveStartKey"] = key


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", required=True, help="Tenant claim configured for this customer deployment")
    parser.add_argument("--region", default=os.getenv("AWS_REGION"), help="AWS region (defaults to AWS_REGION)")
    parser.add_argument("--apply", action="store_true", help="Write the migration; omitted means read-only dry run")
    args = parser.parse_args()
    if not args.tenant_id.strip() or "#" in args.tenant_id or len(args.tenant_id) > 128:
        parser.error("--tenant-id must be 1–128 characters and cannot contain '#'")
    if not args.region:
        parser.error("Set AWS_REGION or pass --region")

    dynamodb = boto3.resource("dynamodb", region_name=args.region)
    tables = {
        "leads": (os.getenv("LEADS_TABLE", "leadrescue-leads"), "lead_id"),
        "followups": (os.getenv("FOLLOWUPS_TABLE", "leadrescue-followups"), "followup_id"),
        "audit": (os.getenv("AUDIT_TABLE", "leadrescue-audit"), "audit_id"),
    }
    counts = {name: {"seen": 0, "changed": 0, "already_current": 0} for name in tables}
    pending = {name: [] for name in tables}
    conflicts = []

    # Preflight the complete migration before the first write so mixed-tenant
    # legacy tables never receive a partial tenant assignment.
    for name, (table_name, key_name) in tables.items():
        table = dynamodb.Table(table_name)
        for item in scan_all(table):
            counts[name]["seen"] += 1
            existing_tenant = item.get("tenant_id")
            if existing_tenant not in (None, args.tenant_id):
                conflicts.append(name)
                continue
            if existing_tenant == args.tenant_id and (name != "audit" or item.get("tenant_lead_id")):
                counts[name]["already_current"] += 1
                continue
            if name == "audit" and not item.get("lead_id"):
                raise RuntimeError("Audit record is missing lead_id; migration stopped")
            counts[name]["changed"] += 1
            pending[name].append({key_name: item[key_name], "lead_id": item.get("lead_id")})

    config_name = os.getenv("CONFIG_TABLE", "leadrescue-config")
    config_table = dynamodb.Table(config_name)
    config_seen = config_copied = 0
    config_pending = []
    for item in scan_all(config_table):
        config_seen += 1
        key = item.get("config_key")
        if not key or key.startswith(f"{args.tenant_id}#"):
            continue
        if item.get("tenant_id") not in (None, args.tenant_id):
            conflicts.append("config")
            continue
        target_key = f"{args.tenant_id}#{key}"
        existing = config_table.get_item(Key={"config_key": target_key}).get("Item")
        if existing and existing.get("tenant_id") not in (None, args.tenant_id):
            conflicts.append("config")
            continue
        config_copied += 1
        config_pending.append(key)

    if conflicts:
        raise RuntimeError(f"Migration preflight found records assigned to another tenant or conflicting config in: {sorted(set(conflicts))}")

    if args.apply:
        for name, (table_name, key_name) in tables.items():
            table = dynamodb.Table(table_name)
            for item_key in pending[name]:
                values = {":tenant": args.tenant_id}
                update = "SET tenant_id = :tenant"
                if name == "audit":
                    values[":tenant_lead"] = f"{args.tenant_id}#{item_key['lead_id']}"
                    update += ", tenant_lead_id = :tenant_lead"
                table.update_item(
                    Key={key_name: item_key[key_name]},
                    UpdateExpression=update,
                    ConditionExpression="attribute_not_exists(tenant_id) OR tenant_id = :tenant",
                    ExpressionAttributeValues=values,
                )

        for item in scan_all(config_table):
            key = item.get("config_key")
            if key not in config_pending:
                continue
            namespaced = dict(item)
            namespaced["config_key"] = f"{args.tenant_id}#{key}"
            namespaced["tenant_id"] = args.tenant_id
            try:
                config_table.put_item(Item=namespaced, ConditionExpression="attribute_not_exists(config_key)")
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                    raise

    mode = "APPLIED" if args.apply else "DRY RUN"
    print(f"{mode} for tenant {args.tenant_id}")
    for name, result in counts.items():
        print(f"{name}: {result}")
    print(f"config: {{'seen': {config_seen}, 'to_copy': {config_copied}}}")
    if conflicts:
        raise RuntimeError(f"Records assigned to another tenant found in: {sorted(set(conflicts))}")


if __name__ == "__main__":
    main()
