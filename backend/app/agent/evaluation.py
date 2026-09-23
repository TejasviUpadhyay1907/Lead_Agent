"""Scoring helpers for the synthetic lead-agent quality benchmark."""

from typing import Any, Dict, Iterable


CRITICAL_FIELDS = ("intent", "urgency", "customer_stage")
EXTRACTION_FIELDS = ("product", "quantity", "location")
EVALUATION_FIELDS = CRITICAL_FIELDS + EXTRACTION_FIELDS


def _canonical(value: Any) -> Any:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped.casefold() if stripped else None
    return value


def score_evaluation_cases(
    cases: Iterable[Dict[str, Any]],
    predictions: Dict[str, Dict[str, Any]],
    failures: Dict[str, str] | None = None,
) -> Dict[str, Any]:
    """Compare structured predictions to expected synthetic labels.

    The report intentionally contains only case IDs and the six evaluated
    structured fields; it never includes source messages or generated drafts.
    """
    failures = failures or {}
    case_rows = []
    correct_by_field = {field: 0 for field in EVALUATION_FIELDS}
    total_by_field = {field: 0 for field in EVALUATION_FIELDS}
    critical_cases_passed = extraction_cases_passed = fully_correct = 0

    for case in cases:
        case_id = case["case_id"]
        expected = case["expected"]
        actual = predictions.get(case_id) or {}
        field_results = {}
        for field in EVALUATION_FIELDS:
            matched = _canonical(actual.get(field)) == _canonical(expected.get(field))
            field_results[field] = matched
            correct_by_field[field] += int(matched)
            total_by_field[field] += 1

        critical_pass = all(field_results[field] for field in CRITICAL_FIELDS)
        extraction_pass = all(field_results[field] for field in EXTRACTION_FIELDS)
        case_pass = critical_pass and extraction_pass and case_id not in failures
        critical_cases_passed += int(critical_pass and case_id not in failures)
        extraction_cases_passed += int(extraction_pass and case_id not in failures)
        fully_correct += int(case_pass)
        case_rows.append({
            "case_id": case_id,
            "passed": case_pass,
            "field_matches": field_results,
            "expected": {key: expected.get(key) for key in EVALUATION_FIELDS},
            "actual": {key: actual.get(key) for key in EVALUATION_FIELDS},
            "failure_type": failures.get(case_id),
        })

    count = len(case_rows)
    if not count:
        raise ValueError("Evaluation dataset contains no cases")

    return {
        "case_count": count,
        "critical_case_pass_rate": critical_cases_passed / count,
        "extraction_case_pass_rate": extraction_cases_passed / count,
        "fully_correct_case_rate": fully_correct / count,
        "field_accuracy": {
            field: correct_by_field[field] / total_by_field[field]
            for field in EVALUATION_FIELDS
        },
        "failed_case_count": len(failures),
        "cases": case_rows,
    }
