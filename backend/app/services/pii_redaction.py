"""Conservative redaction for personal identifiers before third-party inference."""

import re
from typing import Optional


_EMAIL = re.compile(r"\b[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE_CANDIDATE = re.compile(r"(?<!\w)\+?\d(?:[\d\s()./-]*\d)?(?!\w)")


def _redact_customer_name(text: str, name: Optional[str]) -> str:
    if not name or len(name.strip()) < 2:
        return text
    parts = [re.escape(part) for part in name.split() if part]
    if not parts:
        return text
    pattern = re.compile(r"(?<!\w)" + r"\s+".join(parts) + r"(?!\w)", re.IGNORECASE)
    return pattern.sub("[REDACTED_NAME]", text)


def redact_inquiry_pii(
    message: str,
    customer_name: Optional[str] = None,
    customer_email: Optional[str] = None,
    customer_phone: Optional[str] = None,
) -> str:
    """Mask common personal identifiers while preserving the stored source message.

    Email addresses and name/email/phone values already stored on the lead are
    removed before the inquiry is sent to a model. Phone-like sequences are
    masked when they contain at least ten digits, use a country prefix, or use
    formatting separators and contain at least seven digits. This intentionally
    favors privacy; formatted long numeric identifiers may also be masked.
    """
    redacted = _redact_customer_name(message, customer_name)
    if customer_email:
        redacted = re.sub(re.escape(customer_email), "[REDACTED_EMAIL]", redacted, flags=re.IGNORECASE)
    redacted = _EMAIL.sub("[REDACTED_EMAIL]", redacted)

    stored_phone_digits = re.sub(r"\D", "", customer_phone or "")

    def replace_phone(match: re.Match[str]) -> str:
        candidate = match.group(0)
        digits = re.sub(r"\D", "", candidate)
        has_prefix = candidate.lstrip().startswith("+")
        has_separators = bool(re.search(r"[\s()./-]", candidate))
        if digits == stored_phone_digits and len(digits) >= 7:
            return "[REDACTED_PHONE]"
        if 7 <= len(digits) <= 15 and (len(digits) >= 10 or has_prefix or has_separators):
            return "[REDACTED_PHONE]"
        return candidate

    return _PHONE_CANDIDATE.sub(replace_phone, redacted)
