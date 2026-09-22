"""SQS worker for durable lead-analysis jobs."""

import json
import logging
from fastapi import HTTPException

from app.api.deps import get_audit_repo, get_config_repo, get_followups_repo, get_leads_repo
from app.api.leads import analyze_lead_core
from app.config.settings import settings
from app.models.audit import AuditEventCreate
from app.repositories.analysis_jobs import repository as jobs

logger = logging.getLogger("leadrescue.analysis_worker")


def _mark_failed(message: dict, error_code: str) -> None:
    get_audit_repo().create(
        AuditEventCreate(
            lead_id=message["lead_id"],
            action="analysis_job_failed",
            actor=f"user:{message['actor_id']}",
            details={"job_id": message["job_id"], "error_code": error_code},
        )
    )
    jobs.set_status(message["job_id"], "FAILED", error_code)


def handler(event, _context):
    records = event.get("Records")
    if not records:
        raise RuntimeError("Worker requires an SQS event")

    for record in records:
        message = json.loads(record["body"])
        job_id = message["job_id"]
        if record.get("eventSourceARN") == settings.analysis_dlq_arn:
            _mark_failed(message, "worker_crash")
            continue
        if not jobs.claim(job_id):
            continue
        try:
            analyze_lead_core(
                message["lead_id"],
                {"sub": message["actor_id"]},
                get_leads_repo(),
                get_followups_repo(),
                get_audit_repo(),
                get_config_repo(),
                job_id,
            )
            jobs.set_status(job_id, "SUCCEEDED")
        except Exception as exc:
            if isinstance(exc, HTTPException) and exc.status_code in {400, 403, 404, 409, 422}:
                reason = "customer_opted_out" if "opted out" in str(exc.detail).lower() else "request_rejected"
                _mark_failed(message, reason)
                continue
            attempt = int(record.get("attributes", {}).get("ApproximateReceiveCount", "1"))
            if attempt >= 3:
                logger.warning("Analysis job failed after retries (%s)", type(exc).__name__)
                _mark_failed(message, "analysis_failed")
                continue
            jobs.set_status(job_id, "RETRYING", type(exc).__name__)
            raise
    return {"processed": len(records)}
