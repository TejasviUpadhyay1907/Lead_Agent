"""Inventory legacy simulated-send records without modifying customer data.

This read-only report finds leads left in ``simulated_sent`` + ``contacted`` by
the old approval flow and correlates their lifecycle audit history. It emits
lead IDs and timestamps only; it never prints contact PII or writes to AWS.
Every candidate still requires human review because the old approval event did
not preserve the lifecycle value that existed before approval.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import boto3
from boto3.dynamodb.conditions import Attr, Key

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _parse_timestamp(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def classify_legacy_contact(audit_events: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Classify the available audit evidence; never claim that it proves delivery."""
    events = list(audit_events)
    approvals = [event for event in events if event.get("action") == "response_approved"]
    approvals.sort(key=lambda event: _parse_timestamp(event.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc))
    first_approval = approvals[0] if approvals else None

    contact_events = [
        event for event in events
        if event.get("action") == "lifecycle_changed"
        and (event.get("details") or {}).get("new_status") == "contacted"
    ]
    timestamps = sorted(
        event.get("timestamp") for event in contact_events if event.get("timestamp")
    )

    if first_approval is None:
        classification = "review_no_approval_audit"
        approval_at = None
    else:
        approval_at = first_approval.get("timestamp")
        approval_time = _parse_timestamp(approval_at)
        contact_times = [_parse_timestamp(event.get("timestamp")) for event in contact_events]
        contact_times = [value for value in contact_times if value is not None]
        if approval_time is None:
            classification = "review_invalid_approval_timestamp"
        elif any(value < approval_time for value in contact_times):
            classification = "explicit_contact_before_approval_review"
        elif any(value >= approval_time for value in contact_times):
            classification = "explicit_contact_after_approval_review"
        else:
            classification = "likely_legacy_approval_side_effect_review"

    return {
        "classification": classification,
        "first_approval_at": approval_at,
        "lifecycle_contact_audit_timestamps": timestamps,
        "delivery_proven": False,
    }


def _tenant_events(audit_table: Any, tenant_id: str, lead_id: str) -> List[Dict[str, Any]]:
    query = {
        "IndexName": "tenant-lead-timestamp-index",
        "KeyConditionExpression": Key("tenant_lead_id").eq(f"{tenant_id}#{lead_id}"),
        "ProjectionExpression": "#action, #details, #event_time",
        "ExpressionAttributeNames": {
            "#action": "action",
            "#details": "details",
            "#event_time": "timestamp",
        },
        "ScanIndexForward": True,
    }
    events: List[Dict[str, Any]] = []
    while True:
        page = audit_table.query(**query)
        events.extend(page.get("Items", []))
        last_key = page.get("LastEvaluatedKey")
        if not last_key:
            return events
        query["ExclusiveStartKey"] = last_key


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--leads-table", required=True)
    parser.add_argument("--audit-table", required=True)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--region", required=True)
    args = parser.parse_args()
    if not args.tenant_id.strip() or "#" in args.tenant_id or len(args.tenant_id) > 128:
        parser.error("--tenant-id must be 1–128 characters and cannot contain '#' ")

    dynamodb = boto3.resource("dynamodb", region_name=args.region)
    leads = dynamodb.Table(args.leads_table)
    audit = dynamodb.Table(args.audit_table)
    query = {
        "IndexName": "tenant-created-index",
        "KeyConditionExpression": Key("tenant_id").eq(args.tenant_id),
        "FilterExpression": (
            Attr("response_status").eq("simulated_sent")
            & Attr("lifecycle_status").eq("contacted")
        ),
        "ProjectionExpression": "lead_id, tenant_id, response_status, lifecycle_status",
        "ScanIndexForward": True,
    }

    candidates: List[Dict[str, Any]] = []
    while True:
        page = leads.query(**query)
        for lead in page.get("Items", []):
            evidence = classify_legacy_contact(_tenant_events(audit, args.tenant_id, lead["lead_id"]))
            candidates.append({
                "lead_id": lead["lead_id"],
                "response_status": lead["response_status"],
                "lifecycle_status": lead["lifecycle_status"],
                **evidence,
            })
        last_key = page.get("LastEvaluatedKey")
        if not last_key:
            break
        query["ExclusiveStartKey"] = last_key

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tenant_id": args.tenant_id,
        "candidate_count": len(candidates),
        "write_mode": False,
        "notice": "Audit evidence does not prove message delivery. Review every row; this report makes no data changes.",
        "candidates": candidates,
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
