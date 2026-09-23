import pytest

from app.policy.guardrails import check_opt_out


@pytest.mark.parametrize(
    "message",
    [
        "Please don't message me again.",
        "Please do not contact us.",
        "STOP—calling this number!",
        "Unsubscribe me from future emails.",
        "Remove me from your list.",
        "Take us off the mailing list.",
        "No more texts, please.",
        "Please delete my contact details.",
        "Please don’t email me.",
        "DO NOT send us any more messages.",
        "Please opt me out of promotions.",
        "I don’t want to receive emails anymore.",
        "I no longer wish to be contacted.",
    ],
)
def test_detects_common_opt_out_requests_with_punctuation_variants(message):
    detected, _reason = check_opt_out(message)
    assert detected is True


@pytest.mark.parametrize(
    "message",
    [
        "Please contact me about the order.",
        "We need to stop contacting the supplier until Monday, then resume.",
        "Do not stop contacting me; I still want the quote.",
        "Can you explain your opt-out policy?",
        "How do I opt out of marketing messages?",
        "This product is not for us.",
        "No more than 10 emails are needed for the campaign.",
        "Remove the old item from my order.",
    ],
)
def test_does_not_flag_non_opt_out_or_negated_requests(message):
    detected, _reason = check_opt_out(message)
    assert detected is False


def test_opt_out_reason_uses_canonical_matched_phrase():
    detected, reason = check_opt_out("Please DON’T text me!")

    assert detected is True
    assert "dont text" in reason
