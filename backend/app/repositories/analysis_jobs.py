"""Durable analysis job metadata for queue-backed Bedrock inference."""

import time
import hashlib
from datetime import datetime, timezone
from typing import Optional

from boto3.dynamodb.conditions import Attr

from app.config.settings import settings
from app.repositories.base import get_boto3_dynamodb_resource


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AnalysisJobsRepository:
    def __init__(self):
        self._memory: dict[str, dict] = {}
        resource = get_boto3_dynamodb_resource()
        self._table = resource.Table(settings.analysis_jobs_table) if resource and settings.analysis_jobs_table else None
        if self._table is None and not settings.demo_enabled:
            raise RuntimeError("Durable analysis job storage is required")

    def create(self, lead_id: str, actor_id: str, idempotency_key: str) -> tuple[dict, bool]:
        job_id = hashlib.sha256(
            f"{settings.effective_tenant_id}:{actor_id}:{idempotency_key}".encode("utf-8")
        ).hexdigest()
        job = {
            "job_id": job_id,
            "tenant_id": settings.effective_tenant_id,
            "lead_id": lead_id,
            "actor_id": actor_id,
            "status": "QUEUED",
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "expires_at": int(time.time()) + 30 * 24 * 60 * 60,
        }
        if self._table is None:
            existing = self._memory.get(job["job_id"])
            if existing:
                if existing.get("lead_id") != lead_id:
                    raise ValueError("Idempotency key was already used for another lead")
                return existing, False
            self._memory[job["job_id"]] = job
        else:
            try:
                self._table.put_item(Item=job, ConditionExpression=Attr("job_id").not_exists())
            except Exception as exc:
                if getattr(exc, "response", {}).get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                    raise
                existing = self._table.get_item(Key={"job_id": job_id}, ConsistentRead=True).get("Item")
                if not existing or existing.get("tenant_id") != settings.effective_tenant_id:
                    raise
                if existing.get("lead_id") != lead_id:
                    raise ValueError("Idempotency key was already used for another lead") from exc
                return existing, False
        return job, True

    def get(self, job_id: str) -> Optional[dict]:
        if self._table is None:
            job = self._memory.get(job_id)
        else:
            job = self._table.get_item(Key={"job_id": job_id}).get("Item")
        return job if job and job.get("tenant_id") == settings.effective_tenant_id else None

    def claim(self, job_id: str) -> bool:
        now = int(time.time())
        if self._table is None:
            job = self._memory.get(job_id)
            if not job or not (
                job.get("status") in {"QUEUED", "RETRYING"}
                or (job.get("status") == "RUNNING" and job.get("lease_until", 0) < now)
            ):
                return False
            job.update(status="RUNNING", updated_at=now_iso(), lease_until=now + 150)
            return True
        try:
            self._table.update_item(
                Key={"job_id": job_id},
                UpdateExpression="SET #status = :running, updated_at = :updated_at, lease_until = :lease_until",
                ConditionExpression=Attr("tenant_id").eq(settings.effective_tenant_id) & (
                    Attr("status").is_in(["QUEUED", "RETRYING"])
                    | (Attr("status").eq("RUNNING") & Attr("lease_until").lt(now))
                ),
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={":running": "RUNNING", ":updated_at": now_iso(), ":lease_until": now + 150},
            )
            return True
        except Exception as exc:
            if getattr(exc, "response", {}).get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                return False
            raise

    def set_status(self, job_id: str, status: str, error_code: Optional[str] = None) -> None:
        now = now_iso()
        if self._table is None:
            job = self._memory.get(job_id)
            if job:
                job.update(status=status, updated_at=now)
                job.pop("lease_until", None)
                if error_code:
                    job["error_code"] = error_code
            return
        update = "SET #status = :status, updated_at = :updated_at"
        names = {"#status": "status"}
        values = {":status": status, ":updated_at": now}
        if error_code:
            update += ", error_code = :error_code"
            values[":error_code"] = error_code
        update += " REMOVE lease_until"
        if not error_code:
            update += ", error_code"
        self._table.update_item(
            Key={"job_id": job_id},
            UpdateExpression=update,
            ConditionExpression=Attr("tenant_id").eq(settings.effective_tenant_id),
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
        )


repository = AnalysisJobsRepository()
