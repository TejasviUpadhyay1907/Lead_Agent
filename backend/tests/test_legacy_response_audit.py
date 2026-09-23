from scripts.audit_legacy_response_states import classify_legacy_contact


def test_legacy_contact_without_lifecycle_event_needs_review_as_approval_side_effect():
    result = classify_legacy_contact([
        {"action": "response_approved", "timestamp": "2026-09-20T10:00:00Z", "details": {"action": "approve"}},
    ])
    assert result["classification"] == "likely_legacy_approval_side_effect_review"
    assert result["delivery_proven"] is False


def test_explicit_contact_before_approval_is_reported_for_review():
    result = classify_legacy_contact([
        {"action": "lifecycle_changed", "timestamp": "2026-09-20T09:00:00Z", "details": {"new_status": "contacted"}},
        {"action": "response_approved", "timestamp": "2026-09-20T10:00:00Z", "details": {}},
    ])
    assert result["classification"] == "explicit_contact_before_approval_review"
    assert result["delivery_proven"] is False


def test_explicit_contact_after_approval_is_not_auto_rewritten():
    result = classify_legacy_contact([
        {"action": "response_approved", "timestamp": "2026-09-20T10:00:00Z", "details": {}},
        {"action": "lifecycle_changed", "timestamp": "2026-09-20T10:01:00Z", "details": {"new_status": "contacted"}},
    ])
    assert result["classification"] == "explicit_contact_after_approval_review"
    assert result["delivery_proven"] is False


def test_missing_approval_event_is_ambiguous():
    result = classify_legacy_contact([])
    assert result["classification"] == "review_no_approval_audit"
