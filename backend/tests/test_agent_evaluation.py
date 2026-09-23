from app.agent.evaluation import score_evaluation_cases


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


def test_evaluation_rejects_empty_dataset():
    try:
        score_evaluation_cases([], {})
    except ValueError as exc:
        assert "no cases" in str(exc)
    else:
        raise AssertionError("Expected an empty evaluation dataset to be rejected")
