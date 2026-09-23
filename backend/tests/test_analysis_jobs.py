import time

import pytest

from app.repositories.analysis_jobs import AnalysisJobsRepository


def test_idempotency_key_reuses_job_but_cannot_switch_leads():
    repo = AnalysisJobsRepository()
    first, created = repo.create("lead-a", "operator", "request-key")
    repeated, repeated_created = repo.create("lead-a", "operator", "request-key")

    assert created is True
    assert repeated_created is False
    assert repeated["job_id"] == first["job_id"]
    with pytest.raises(ValueError, match="another lead"):
        repo.create("lead-b", "operator", "request-key")


def test_claim_is_exclusive_and_retryable_jobs_can_be_reclaimed():
    repo = AnalysisJobsRepository()
    job, _created = repo.create("lead-a", "operator", "request-key")

    assert repo.claim(job["job_id"]) is True
    assert repo.claim(job["job_id"]) is False

    repo.set_status(job["job_id"], "RETRYING", "TransientFailure")
    assert repo.claim(job["job_id"]) is True
    repo.set_status(job["job_id"], "SUCCEEDED")
    assert repo.claim(job["job_id"]) is False


def test_expired_running_lease_allows_crash_recovery():
    repo = AnalysisJobsRepository()
    job, _created = repo.create("lead-a", "operator", "request-key")
    assert repo.claim(job["job_id"]) is True
    repo._memory[job["job_id"]]["lease_until"] = int(time.time()) - 1

    assert repo.claim(job["job_id"]) is True

