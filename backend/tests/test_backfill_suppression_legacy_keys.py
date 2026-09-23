from scripts.backfill_customer_suppressions import is_legacy_suppression_key


def test_recognizes_only_old_tenant_scoped_sha256_key_shape():
    digest = "a" * 64
    assert is_legacy_suppression_key(f"tenant-1#{digest}", "tenant-1")


def test_does_not_match_other_tenant_or_new_hmac_key_shape():
    digest = "a" * 64
    assert not is_legacy_suppression_key(f"tenant-2#{digest}", "tenant-1")
    assert not is_legacy_suppression_key(f"tenant-1#{'b' * 16}#{digest}", "tenant-1")


def test_rejects_markers_and_malformed_or_uppercase_digests():
    assert not is_legacy_suppression_key("migration-complete#tenant-1", "tenant-1")
    assert not is_legacy_suppression_key(f"tenant-1#{'A' * 64}", "tenant-1")
    assert not is_legacy_suppression_key(f"tenant-1#{'a' * 63}", "tenant-1")
    assert not is_legacy_suppression_key(f"tenant-1#{'g' * 64}", "tenant-1")
