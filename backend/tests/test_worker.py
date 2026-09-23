import json

import pytest
from fastapi import HTTPException

from app.config.settings import settings
from app import worker


def _record(attempt=1, event_source_arn="arn:aws:sqs:region:account:analysis"):
    return {
        "body": json.dumps({"job_id": "job-1", "lead_id": "lead-1", "actor_id": "operator-1"}),
        "attributes": {"ApproximateReceiveCount": str(attempt)},
        "eventSourceARN": event_source_arn,
    }


def _patch_dependencies(monkeypatch, *, claim_result=True, audit_events=None, status_updates=None):
    audit_events = audit_events if audit_events is not None else []
    status_updates = status_updates if status_updates is not None else []
    monkeypatch.setattr(worker.jobs, "claim", lambda _job_id: claim_result)
    monkeypatch.setattr(
        worker.jobs,
        "set_status",
        lambda job_id, status_value, error_code=None: status_updates.append(
            (job_id, status_value, error_code)
        ),
    )
    monkeypatch.setattr(worker, "get_leads_repo", lambda: object())
    monkeypatch.setattr(worker, "get_followups_repo", lambda: object())
    monkeypatch.setattr(worker, "get_config_repo", lambda: object())
    monkeypatch.setattr(
        worker,
        "get_audit_repo",
        lambda: type("Audit", (), {"create": lambda _self, event: audit_events.append(event)})(),
    )
    return audit_events, status_updates


def test_worker_success_marks_job_succeeded(monkeypatch):
    _events, status_updates = _patch_dependencies(monkeypatch)
    analyzed = []
    monkeypatch.setattr(worker, "analyze_lead_core", lambda *args: analyzed.append(args))

    result = worker.handler({"Records": [_record()]}, None)

    assert result == {"processed": 1}
    assert len(analyzed) == 1
    assert status_updates == [("job-1", "SUCCEEDED", None)]


def test_worker_skips_duplicate_delivery_when_job_is_already_claimed(monkeypatch):
    _events, status_updates = _patch_dependencies(monkeypatch, claim_result=False)
    monkeypatch.setattr(
        worker,
        "analyze_lead_core",
        lambda *_args: pytest.fail("A delivery that cannot claim the job must not run inference"),
    )

    assert worker.handler({"Records": [_record()]}, None) == {"processed": 1}
    assert status_updates == []


def test_retryable_worker_failure_releases_lease_and_retries_message(monkeypatch):
    _events, status_updates = _patch_dependencies(monkeypatch)
    monkeypatch.setattr(worker, "analyze_lead_core", lambda *_args: (_ for _ in ()).throw(RuntimeError("transient")))

    with pytest.raises(RuntimeError, match="transient"):
        worker.handler({"Records": [_record(attempt=1)]}, None)

    assert status_updates == [("job-1", "RETRYING", "RuntimeError")]


def test_third_worker_failure_is_recorded_as_terminal(monkeypatch):
    events, status_updates = _patch_dependencies(monkeypatch)
    monkeypatch.setattr(worker, "analyze_lead_core", lambda *_args: (_ for _ in ()).throw(RuntimeError("transient")))

    assert worker.handler({"Records": [_record(attempt=3)]}, None) == {"processed": 1}
    assert len(events) == 1
    assert events[0].action == "analysis_job_failed"
    assert status_updates == [("job-1", "FAILED", "analysis_failed")]


def test_opt_out_conflict_is_terminal_and_not_retried(monkeypatch):
    events, status_updates = _patch_dependencies(monkeypatch)
    monkeypatch.setattr(
        worker,
        "analyze_lead_core",
        lambda *_args: (_ for _ in ()).throw(HTTPException(status_code=409, detail="Customer has opted out for this contact")),
    )

    assert worker.handler({"Records": [_record(attempt=1)]}, None) == {"processed": 1}
    assert len(events) == 1
    assert events[0].details["error_code"] == "customer_opted_out"
    assert status_updates == [("job-1", "FAILED", "customer_opted_out")]


def test_dead_letter_delivery_is_audited_as_worker_crash(monkeypatch):
    events, status_updates = _patch_dependencies(monkeypatch, claim_result=False)
    dlq_arn = "arn:aws:sqs:region:account:analysis-dlq"
    monkeypatch.setattr(settings, "analysis_dlq_arn", dlq_arn)
    monkeypatch.setattr(
        worker,
        "analyze_lead_core",
        lambda *_args: pytest.fail("DLQ messages must not rerun analysis"),
    )

    assert worker.handler({"Records": [_record(event_source_arn=dlq_arn)]}, None) == {"processed": 1}
    assert len(events) == 1
    assert events[0].details["error_code"] == "worker_crash"
    assert status_updates == [("job-1", "FAILED", "worker_crash")]
