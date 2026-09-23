"""Deterministic customer-contact guardrails independent of model output."""

import re
import unicodedata
from typing import List, Tuple

# Phrases are normalized to lowercase ASCII word tokens before matching. Keep
# this list intentionally action-oriented to avoid blocking ordinary mentions
# such as "what is your opt-out policy?" unless an actual opt-out request exists.
OPT_OUT_PHRASES = (
    "unsubscribe",
    "optout",
    "opt me out",
    "opt us out",
    "please opt out",
    "i want to opt out",
    "i would like to opt out",
    "we want to opt out",
    "we would like to opt out",
    "dont want to receive emails",
    "do not want to receive emails",
    "dont want to receive messages",
    "do not want to receive messages",
    "dont want marketing emails",
    "do not want marketing emails",
    "no longer want to be contacted",
    "no longer wish to be contacted",
    "no longer contact me",
    "no longer contact us",
    "remove me",
    "remove us",
    "take me off",
    "take us off",
    "stop contacting me",
    "stop contacting us",
    "stop contacting this number",
    "stop calling me",
    "stop calling us",
    "stop calling this number",
    "stop texting me",
    "stop texting us",
    "stop messaging me",
    "stop messaging us",
    "stop emailing me",
    "stop emailing us",
    "do not contact",
    "dont contact",
    "do not call",
    "dont call",
    "do not text",
    "dont text",
    "do not message",
    "dont message",
    "do not email",
    "dont email",
    "do not send me",
    "do not send us",
    "dont send me",
    "dont send us",
    "no more emails",
    "no more texts",
    "no more messages",
    "no more calls",
    "please delete my contact",
    "delete my contact",
    "delete my data",
    "please delete my data",
    "cease contacting",
)

_NEGATED_PREFIXES = (
    "dont stop",
    "do not stop",
    "never stop",
    "dont",
    "do not",
    "never",
    "continue",
    "keep",
)


def _normalize_message(value: str) -> str:
    """Normalize Unicode punctuation/case/spacing for robust phrase matching."""
    ascii_compatible = unicodedata.normalize("NFKC", value).casefold()
    ascii_compatible = ascii_compatible.replace("’", "'").replace("‘", "'")
    ascii_compatible = re.sub(r"\bdo\s+not\b", "do not", ascii_compatible)
    ascii_compatible = re.sub(r"\bdon\s*'\s*t\b", "dont", ascii_compatible)
    ascii_compatible = re.sub(r"[^a-z0-9]+", " ", ascii_compatible)
    return " ".join(ascii_compatible.split())


def _is_negated_match(message: str, phrase: str, start: int) -> bool:
    """Avoid treating requests to continue contact as opt-outs."""
    prefix = message[:start].split()
    for negated_prefix in _NEGATED_PREFIXES:
        tokens = negated_prefix.split()
        if len(prefix) >= len(tokens) and prefix[-len(tokens):] == tokens:
            return True

    # Common natural-language negation can put "stop" after an auxiliary.
    preceding = " ".join(prefix[-8:])
    return bool(re.search(r"\b(?:do not|dont|never) want (?:you to )?$", preceding))


def check_opt_out(raw_message: str) -> Tuple[bool, str]:
    """Detect clear opt-out requests despite punctuation and Unicode variants.

    Returns the matched canonical phrase as an internal reason. This is a
    conservative phrase detector, not a multilingual or semantic classifier;
    ambiguous cases still require explicit consent policy and review.
    """
    normalized = _normalize_message(raw_message or "")
    for phrase in OPT_OUT_PHRASES:
        normalized_phrase = _normalize_message(phrase)
        match = re.search(rf"(?<![a-z0-9]){re.escape(normalized_phrase)}(?![a-z0-9])", normalized)
        if match and not _is_negated_match(normalized, normalized_phrase, match.start()):
            return True, f"Matched opt-out phrase '{phrase}'"
    return False, "No opt-out phrases detected"
