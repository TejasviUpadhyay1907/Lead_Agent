from app.agent.evaluation import score_evaluation_cases
from scripts.evaluate_lead_agent import DEFAULT_DATASET, _load_dataset, _scoring_prediction


def _case(case_id="case-1"):
    return {
        "case_id": case_id,
        "expected": {
            "intent": "purchase",
            "urgency": "high",
            "customer_stage": "new",
            "product": "CNC machines",
            "quantity": 10,
            "location": "Pune",
        },
    }


def _prediction():
    return {
        "intent": "PURCHASE",
        "urgency": "high",
        "customer_stage": "new",
        "product": " cnc machines ",
        "quantity": 10,
        "location": "Pune",
    }


def test_evaluation_reports_perfect_structured_prediction():
    result = score_evaluation_cases([_case()], {"case-1": _prediction()})

    assert result["critical_case_pass_rate"] == 1
    assert result["extraction_case_pass_rate"] == 1
    assert result["fully_correct_case_rate"] == 1
    assert result["failed_case_count"] == 0


def test_evaluation_counts_failed_live_inference_as_not_passed():
    result = score_evaluation_cases([_case()], {}, {"case-1": "RuntimeError"})

    assert result["critical_case_pass_rate"] == 0
    assert result["extraction_case_pass_rate"] == 0
    assert result["fully_correct_case_rate"] == 0
    assert result["failed_case_count"] == 1
    assert result["cases"][0]["failure_type"] == "RuntimeError"


def test_evaluation_does_not_include_message_or_generated_draft():
    case = {**_case(), "message": "synthetic source text"}
    prediction = {**_prediction(), "response_draft": "private generated response"}

    result = score_evaluation_cases([case], {"case-1": prediction})
    serialized = str(result)

    assert "synthetic source text" not in serialized
    assert "private generated response" not in serialized


def test_injection_canary_detects_exact_echo_without_reporting_the_canary():
    marker = "EVAL_SECRET_CANARY_82FA1"
    case = {**_case(), "forbidden_text_fragments": [marker]}
    prediction = {**_prediction(), "response_draft": f"I will disclose {marker} now."}

    result = score_evaluation_cases([case], {"case-1": prediction})

    assert result["injection_canary_case_count"] == 1
    assert result["injection_canary_case_pass_rate"] == 0
    assert result["cases"][0]["injection_canary_pass"] is False
    assert marker not in str(result)


def test_injection_canary_checks_summary_and_recommendation_text_too():
    marker = "EVAL_SECRET_CANARY_82FA1"
    case = {**_case(), "forbidden_text_fragments": [marker]}
    prediction = {**_prediction(), "free_text_output": f"Summary accidentally repeats {marker}."}

    result = score_evaluation_cases([case], {"case-1": prediction})

    assert result["injection_canary_case_pass_rate"] == 0
    assert result["cases"][0]["injection_canary_pass"] is False
    assert marker not in str(result)


def test_injection_canary_passes_when_generated_draft_does_not_echo_marker():
    marker = "EVAL_SECRET_CANARY_82FA1"
    case = {**_case(), "forbidden_text_fragments": [marker]}
    prediction = {**_prediction(), "response_draft": "Thanks for your inquiry. Our team can help."}

    result = score_evaluation_cases([case], {"case-1": prediction})

    assert result["injection_canary_case_pass_rate"] == 1
    assert result["fully_correct_case_rate"] == 1


def test_live_prediction_keeps_all_model_authored_text_in_memory_for_canary_checks():
    from types import SimpleNamespace

    result = _scoring_prediction(SimpleNamespace(
        intent=SimpleNamespace(value="purchase"),
        urgency=SimpleNamespace(value="low"),
        customer_stage=SimpleNamespace(value="new"),
        product="Hydraulic valves",
        quantity=2,
        location="Indore",
        key_entities=["valves"],
        summary="A synthetic summary.",
        recommended_action="Confirm the specifications.",
        response_draft="Thank you for reaching out.",
    ))

    for text in ("Hydraulic valves", "Indore", "valves", "synthetic summary", "Confirm the specifications", "Thank you"):
        assert text in result["free_text_output"]
    assert "response_draft" not in result


def test_evaluation_rejects_empty_dataset():
    try:
        score_evaluation_cases([], {})
    except ValueError as exc:
        assert "no cases" in str(exc)
    else:
        raise AssertionError("Expected an empty evaluation dataset to be rejected")


def test_checked_in_benchmark_corpus_has_unique_expected_cases_and_canaries():
    version, cases = _load_dataset(DEFAULT_DATASET)

    assert version == "2026-09-24.1"
    assert len(cases) == 20
    assert sum(bool(case.get("forbidden_text_fragments")) for case in cases) == 4
