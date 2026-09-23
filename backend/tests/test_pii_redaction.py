from app.services.pii_redaction import redact_inquiry_pii


def test_redacts_customer_name_contact_email_and_phone_without_losing_request():
    message = (
        "Hello Asha Rao, please email asha.rao@example.com or call +91 98765 43210. "
        "I need 10 CNC machines delivered to Pune."
    )

    result = redact_inquiry_pii(
        message,
        customer_name="Asha Rao",
        customer_email="asha.rao@example.com",
        customer_phone="+91-98765-43210",
    )

    assert "Asha Rao" not in result
    assert "asha.rao@example.com" not in result
    assert "98765" not in result
    assert "10 CNC machines" in result
    assert "Pune" in result
    assert "[REDACTED_NAME]" in result
    assert "[REDACTED_EMAIL]" in result
    assert "[REDACTED_PHONE]" in result


def test_redacts_unstored_email_and_formatted_phone_but_preserves_short_numbers():
    result = redact_inquiry_pii("Reply to sales@acme.com. Call +1 (415) 555-2671 about order 42.")

    assert "sales@acme.com" not in result
    assert "415" not in result
    assert "[REDACTED_PHONE]" in result
    assert "order 42" in result


def test_preserves_message_when_no_identifiers_are_detected():
    message = "Need 10 CNC machines delivered to Pune by Friday."
    assert redact_inquiry_pii(message) == message
