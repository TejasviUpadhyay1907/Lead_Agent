"""
LeadRescue AI — Leads Repository
Provides persistence operations for Lead records (DynamoDB & Memory fallback).
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence
from botocore.exceptions import ClientError
from boto3.dynamodb.types import TypeSerializer
from boto3.dynamodb.conditions import Attr, Key
from app.config.settings import settings
from app.models.lead import Lead, LeadCreate, LeadUpdate
from app.models.audit import AuditEvent
from app.models.followup import FollowUp
from app.repositories.base import get_boto3_dynamodb_resource
from app.repositories.pagination import decode_cursor, encode_cursor
from app.repositories.customer_index import customer_index_keys
from app.repositories.customer_suppressions import migration_marker_key, suppression_items, suppression_keys


class ConcurrentLeadUpdateError(Exception):
    """Raised when an optimistic condition detects a newer lead version."""


class SuppressionMigrationIncompleteError(RuntimeError):
    """Raised until legacy opt-outs are loaded into the durable suppression registry."""


def _serialize_item(item: dict) -> dict:
    serializer = TypeSerializer()
    return {key: serializer.serialize(value) for key, value in item.items()}


def _next_updated_at(expected_updated_at: str) -> str:
    updated_at = datetime.now(timezone.utc)
    if updated_at.isoformat() == expected_updated_at:
        updated_at += timedelta(microseconds=1)
    return updated_at.isoformat()


def _lead_storage_item(lead: Lead, json_mode: bool = False) -> dict:
    item = lead.model_dump(mode="json") if json_mode else lead.model_dump()
    item.update(customer_index_keys(lead.tenant_id, lead.customer_email, lead.customer_phone))
    return item


class LeadsRepository:
    """Repository for Lead operations."""

    def __init__(self, use_memory: bool = False):
        self.use_memory = use_memory
        self._memory_store: Dict[str, Lead] = {}
        self._memory_suppressions: set[str] = set()
        self._table = None
        self._suppressions_table = None
        self._suppressions_ready = use_memory

        if not use_memory:
            dynamodb = get_boto3_dynamodb_resource()
            if dynamodb and settings.leads_table:
                try:
                    self._table = dynamodb.Table(settings.leads_table)
                    if settings.customer_suppressions_table:
                        self._suppressions_table = dynamodb.Table(settings.customer_suppressions_table)
                except Exception:
                    if not settings.demo_enabled:
                        raise
                    self.use_memory = True
            else:
                if not settings.demo_enabled:
                    raise RuntimeError("DynamoDB is required when DEMO_MODE is disabled")
                self.use_memory = True
        if self._suppressions_table is None and not settings.demo_enabled:
            raise RuntimeError("Customer opt-out suppression storage is required")
        if self.use_memory or self._suppressions_table is None:
            self._suppressions_ready = True
        if self._suppressions_table:
            try:
                self._suppressions_ready = bool(
                    self._suppressions_table.get_item(
                        Key={"suppression_key": migration_marker_key(settings.effective_tenant_id)},
                        ConsistentRead=True,
                    ).get("Item")
                )
            except Exception:
                if not settings.demo_enabled:
                    raise

    def customer_opted_out(self, lead: Lead) -> bool:
        """Check the durable tenant-scoped suppression registry using strongly consistent reads."""
        self._ensure_suppressions_ready()
        keys = suppression_keys(settings.effective_tenant_id, lead.customer_email, lead.customer_phone)
        if self.use_memory or not self._suppressions_table:
            if any(key in self._memory_suppressions for key in keys if key):
                return True
            target_keys = set(key for key in keys if key)
            return any(
                item.lifecycle_status.value == "opted_out"
                and target_keys.intersection(suppression_keys(item.tenant_id, item.customer_email, item.customer_phone))
                for item in self._memory_store.values()
            )
        for key in keys:
            if key and self._suppressions_table.get_item(Key={"suppression_key": key}, ConsistentRead=True).get("Item"):
                return True
        return False

    def _suppression_transaction_items(self, lead: Lead) -> list[dict]:
        """Atomically record opt-outs or reject outreach writes racing with an opt-out."""
        self._ensure_suppressions_ready()
        keys = suppression_keys(settings.effective_tenant_id, lead.customer_email, lead.customer_phone)
        if lead.lifecycle_status.value == "opted_out":
            return [
                {"Put": {"TableName": settings.customer_suppressions_table, "Item": _serialize_item(item)}}
                for item in suppression_items(settings.effective_tenant_id, lead.lead_id, lead.customer_email, lead.customer_phone)
            ]
        return [
            {
                "ConditionCheck": {
                    "TableName": settings.customer_suppressions_table,
                    "Key": _serialize_item({"suppression_key": key}),
                    "ConditionExpression": "attribute_not_exists(suppression_key)",
                }
            }
            for key in keys if key
        ]

    def _ensure_suppressions_ready(self) -> None:
        if not self._suppressions_ready:
            if self._suppressions_table:
                self._suppressions_ready = bool(
                    self._suppressions_table.get_item(
                        Key={"suppression_key": migration_marker_key(settings.effective_tenant_id)},
                        ConsistentRead=True,
                    ).get("Item")
                )
        if not self._suppressions_ready:
            raise SuppressionMigrationIncompleteError("Customer opt-out backfill must finish before lead operations resume")

    def suppression_registry_ready(self) -> bool:
        try:
            self._ensure_suppressions_ready()
            return True
        except Exception:
            return False

    def create(self, lead_create: LeadCreate) -> Lead:
        lead = Lead(**lead_create.model_dump())
        if self.use_memory or not self._table:
            self._memory_store[lead.lead_id] = lead
            return lead
        try:
            self._table.put_item(Item=_lead_storage_item(lead), ConditionExpression=Attr("lead_id").not_exists())
            return lead
        except Exception:
            if not settings.demo_enabled:
                raise
            # Fallback to memory if AWS fails
            self._memory_store[lead.lead_id] = lead
            return lead

    def create_with_audit(self, lead: Lead, audit: AuditEvent, audit_repo) -> Lead:
        """Atomically persist a new production lead and its initial audit event."""
        if self.use_memory or not self._table:
            if not audit_repo.use_memory:
                raise RuntimeError("Lead and audit records must use the same persistent storage mode")
            self._memory_store[lead.lead_id] = lead
            audit_repo.store(audit)
            if lead.lifecycle_status.value == "opted_out":
                self._memory_suppressions.update(
                    key for key in suppression_keys(lead.tenant_id, lead.customer_email, lead.customer_phone) if key
                )
            return lead
        if audit_repo.use_memory or not audit_repo._table:
            raise RuntimeError("Lead and audit records must use the same persistent storage mode")

        self._table.meta.client.transact_write_items(
            TransactItems=[
                {
                    "Put": {
                        "TableName": settings.leads_table,
                        "Item": _serialize_item(_lead_storage_item(lead, json_mode=True)),
                        "ConditionExpression": "attribute_not_exists(lead_id)",
                    }
                },
                {
                    "Put": {
                        "TableName": settings.audit_table,
                        "Item": _serialize_item(audit.model_dump(mode="json")),
                        "ConditionExpression": "attribute_not_exists(audit_id)",
                    }
                },
                *self._suppression_transaction_items(lead),
            ]
        )
        return lead

    def save_with_audits(self, lead: Lead, audits: Sequence[AuditEvent], audit_repo, expected_updated_at: str) -> Lead:
        """Atomically save a lead and its audit events, rejecting stale edits."""
        return self.save_workflow(lead, [], audits, None, audit_repo, expected_updated_at)

    def save_with_followup_and_audit(
        self, lead: Lead, followup: FollowUp, audit: AuditEvent,
        followups_repo, audit_repo, expected_updated_at: str,
    ) -> Lead:
        """Atomically commit a rescue lead update, follow-up, and audit event."""
        return self.save_workflow(lead, [followup], [audit], followups_repo, audit_repo, expected_updated_at)

    def save_workflow(
        self, lead: Lead, followups: Sequence[FollowUp], audits: Sequence[AuditEvent],
        followups_repo, audit_repo, expected_updated_at: str,
    ) -> Lead:
        """Atomically commit a lead plus related follow-up and audit records."""
        lead.updated_at = _next_updated_at(expected_updated_at)
        if self.use_memory or not self._table:
            if (followups and (not followups_repo or not followups_repo.use_memory)) or not audit_repo.use_memory:
                raise RuntimeError("Workflow records must use the same persistent storage mode")
            if lead.lifecycle_status.value != "opted_out" and self.customer_opted_out(lead):
                raise ConcurrentLeadUpdateError("Customer has opted out for this contact")
            self._memory_store[lead.lead_id] = lead
            if lead.lifecycle_status.value == "opted_out":
                self._memory_suppressions.update(
                    key for key in suppression_keys(lead.tenant_id, lead.customer_email, lead.customer_phone) if key
                )
            for followup in followups:
                followups_repo._memory_store[followup.followup_id] = followup
            for audit in audits:
                audit_repo.store(audit)
            return lead
        if (followups and (not followups_repo or followups_repo.use_memory or not followups_repo._table)) or audit_repo.use_memory or not audit_repo._table:
            raise RuntimeError("Workflow records must use the same persistent storage mode")

        transactions = [
            {
                "Put": {
                    "TableName": settings.leads_table,
                    "Item": _serialize_item(_lead_storage_item(lead, json_mode=True)),
                    "ConditionExpression": "#tenant = :tenant AND #updated = :expected",
                    "ExpressionAttributeNames": {"#tenant": "tenant_id", "#updated": "updated_at"},
                    "ExpressionAttributeValues": {
                        ":tenant": _serialize_item({"v": settings.effective_tenant_id})["v"],
                        ":expected": _serialize_item({"v": expected_updated_at})["v"],
                    },
                }
            },
        ]
        transactions.extend({
            "Put": {
                "TableName": settings.followups_table,
                "Item": _serialize_item(followup.model_dump(mode="json")),
                "ConditionExpression": "attribute_not_exists(followup_id)",
            }
        } for followup in followups)
        transactions.extend({
            "Put": {
                "TableName": settings.audit_table,
                "Item": _serialize_item(audit.model_dump(mode="json")),
                "ConditionExpression": "attribute_not_exists(audit_id)",
            }
        } for audit in audits)
        transactions.extend(self._suppression_transaction_items(lead))
        try:
            self._table.meta.client.transact_write_items(TransactItems=transactions)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "TransactionCanceledException":
                raise ConcurrentLeadUpdateError("Lead changed after it was loaded") from exc
            raise
        return lead

    def get_by_id(self, lead_id: str) -> Optional[Lead]:
        if self.use_memory or not self._table:
            return self._memory_store.get(lead_id)
        try:
            response = self._table.get_item(Key={"lead_id": lead_id})
            item = response.get("Item")
            if item and item.get("tenant_id") == settings.effective_tenant_id:
                return Lead(**item)
            return None
        except Exception:
            if not settings.demo_enabled:
                raise
            return self._memory_store.get(lead_id)

    def list_leads(
        self,
        lifecycle_status: Optional[str] = None,
        priority: Optional[str] = None,
        risk_status: Optional[str] = None,
        source: Optional[str] = None,
    ) -> List[Lead]:
        if self.use_memory or not self._table:
            leads = list(self._memory_store.values())
        else:
            try:
                leads = []
                query_args = {
                    "IndexName": "tenant-created-index",
                    "KeyConditionExpression": Key("tenant_id").eq(settings.effective_tenant_id),
                    "ScanIndexForward": False,
                }
                while True:
                    response = self._table.query(**query_args)
                    leads.extend(Lead(**item) for item in response.get("Items", []))
                    last_key = response.get("LastEvaluatedKey")
                    if not last_key:
                        break
                    query_args["ExclusiveStartKey"] = last_key
            except Exception:
                if not settings.demo_enabled:
                    raise
                leads = list(self._memory_store.values())

        # Filtering logic
        filtered = leads
        if lifecycle_status:
            filtered = [l for l in filtered if l.lifecycle_status == lifecycle_status]
        if priority:
            filtered = [l for l in filtered if l.priority == priority]
        if risk_status:
            filtered = [l for l in filtered if l.risk_status == risk_status]
        if source:
            filtered = [l for l in filtered if l.source == source]

        # Sort newest first
        filtered.sort(key=lambda x: x.created_at, reverse=True)
        return filtered

    def find_customer_history(
        self, customer_email: Optional[str] = None, customer_phone: Optional[str] = None, limit: int = 10
    ) -> List[Lead]:
        """Read bounded history using customer GSIs, never a tenant-wide lead listing."""
        keys = customer_index_keys(settings.effective_tenant_id, customer_email, customer_phone)
        if self.use_memory or not self._table:
            candidates = [
                lead for lead in self._memory_store.values()
                if (customer_email and lead.customer_email and lead.customer_email.lower() == customer_email.lower())
                or (customer_phone and lead.customer_phone and "".join(filter(str.isdigit, lead.customer_phone)) == "".join(filter(str.isdigit, customer_phone)))
            ]
            return sorted(candidates, key=lambda lead: lead.created_at, reverse=True)[:limit]

        found = {}
        for key_name, index_name in (("tenant_email_key", "tenant-email-index"), ("tenant_phone_key", "tenant-phone-index")):
            key_value = keys[key_name]
            if not key_value:
                continue
            args = {
                "IndexName": index_name,
                "KeyConditionExpression": Key(key_name).eq(key_value),
                "ScanIndexForward": False,
                "Limit": limit,
            }
            response = self._table.query(**args)
            for item in response.get("Items", []):
                if item.get("tenant_id") == settings.effective_tenant_id:
                    lead = Lead(**item)
                    found[lead.lead_id] = lead
        return sorted(found.values(), key=lambda lead: lead.created_at, reverse=True)[:limit]

    def list_leads_page(
        self,
        limit: int = 50,
        cursor: Optional[str] = None,
        lifecycle_status: Optional[str] = None,
        priority: Optional[str] = None,
        source: Optional[str] = None,
        risk_status: Optional[str] = None,
    ) -> tuple[List[Lead], Optional[str]]:
        """Read one bounded page and return an opaque continuation cursor."""
        filters = {"tenant_id": settings.effective_tenant_id, "lifecycle_status": lifecycle_status, "priority": priority, "source": source, "risk_status": risk_status}
        state = decode_cursor(cursor, filters, {"tenant_id", "created_at", "lead_id"})

        if self.use_memory or not self._table:
            leads = list(self._memory_store.values())
            if lifecycle_status:
                leads = [lead for lead in leads if lead.lifecycle_status == lifecycle_status]
            if priority:
                leads = [lead for lead in leads if lead.priority == priority]
            if source:
                leads = [lead for lead in leads if lead.source == source]
            leads.sort(key=lambda lead: lead.created_at, reverse=True)
            offset = int(state.get("offset", 0))
            page = leads[offset:offset + limit]
            next_cursor = encode_cursor({"offset": offset + len(page), "filter": filters}) if offset + len(page) < len(leads) else None
            return page, next_cursor

        conditions = []
        for name, value in (("lifecycle_status", lifecycle_status), ("priority", priority), ("source", source)):
            if value is not None:
                conditions.append(Attr(name).eq(value))
        filter_expression = None
        for condition in conditions:
            filter_expression = condition if filter_expression is None else filter_expression & condition
        query_args = {
            "IndexName": "tenant-created-index",
            "KeyConditionExpression": Key("tenant_id").eq(settings.effective_tenant_id),
            "ScanIndexForward": False,
            "Limit": limit,
        }
        if state.get("last_key"):
            query_args["ExclusiveStartKey"] = state["last_key"]
        if filter_expression is not None:
            query_args["FilterExpression"] = filter_expression
        try:
            response = self._table.query(**query_args)
        except Exception:
            if not settings.demo_enabled:
                raise
            self.use_memory = True
            return self.list_leads_page(
                limit=limit,
                lifecycle_status=lifecycle_status,
                priority=priority,
                source=source,
                risk_status=risk_status,
            )
        page = [Lead(**item) for item in response.get("Items", [])]
        page.sort(key=lambda lead: lead.created_at, reverse=True)
        last_key = response.get("LastEvaluatedKey")
        next_cursor = encode_cursor({"last_key": last_key, "filter": filters}) if last_key else None
        return page, next_cursor

    def update(self, lead_id: str, lead_update: LeadUpdate) -> Optional[Lead]:
        lead = self.get_by_id(lead_id)
        if not lead:
            return None

        update_data = lead_update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if value is not None:
                setattr(lead, key, value)

        lead.updated_at = lead.model_dump().get("updated_at", lead.created_at)

        if self.use_memory or not self._table:
            self._memory_store[lead_id] = lead
            return lead

        try:
            self._table.put_item(Item=_lead_storage_item(lead), ConditionExpression=Attr("tenant_id").eq(settings.effective_tenant_id))
            return lead
        except Exception:
            if not settings.demo_enabled:
                raise
            self._memory_store[lead_id] = lead
            return lead

    def save(self, lead: Lead) -> Lead:
        """Direct save for full lead object (used by internal services)."""
        if self.use_memory or not self._table:
            self._memory_store[lead.lead_id] = lead
            return lead
        try:
            self._table.put_item(Item=_lead_storage_item(lead), ConditionExpression=Attr("tenant_id").eq(settings.effective_tenant_id))
            return lead
        except Exception:
            if not settings.demo_enabled:
                raise
            self._memory_store[lead.lead_id] = lead
            return lead
