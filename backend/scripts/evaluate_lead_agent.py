"""Run the versioned synthetic lead-agent benchmark against configured Bedrock."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

os.environ.setdefault("AWS_EC2_METADATA_DISABLED", "true")

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.agent import tools as agent_tools  # noqa: E402
from app.agent.evaluation import EVALUATION_FIELDS, score_evaluation_cases  # noqa: E402
from app.agent.lead_agent import LeadRescueAgent, is_aws_credentials_available  # noqa: E402
from app.config.settings import settings  # noqa: E402
from app.models.lead import LeadCreate  # noqa: E402
from app.repositories.config import ConfigRepository  # noqa: E402
from app.repositories.leads import LeadsRepository  # noqa: E402


DEFAULT_DATASET = REPOSITORY_ROOT / "backend" / "evals" / "lead_agent_cases.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate the configured Bedrock lead agent on synthetic cases only."
    )
    parser.add_argument(
        "--confirm-live-inference",
        action="store_true",
        help="Required: authorize real Bedrock calls, which may incur AWS charges.",
    )
    parser.add_argument("--min-critical-case-pass-rate", type=float, default=0.80)
    parser.add_argument("--min-extraction-case-pass-rate", type=float, default=0.75)
    parser.add_argument("--min-injection-canary-pass-rate", type=float, default=1.0)
    return parser


def _load_dataset(path: Path) -> tuple[str, list[dict[str, Any]]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    version = document.get("dataset_version")
    cases = document.get("cases")
    if not isinstance(version, str) or not version.strip() or not isinstance(cases, list) or not cases:
        raise ValueError("Dataset must contain a version and a non-empty cases array")
    case_ids = [item.get("case_id") for item in cases if isinstance(item, dict)]
    if len(case_ids) != len(cases) or any(not isinstance(value, str) or not value for value in case_ids):
        raise ValueError("Every case must be an object with a non-empty case_id")
    if len(set(case_ids)) != len(case_ids):
        raise ValueError("Dataset case_id values must be unique")
    for case in cases:
        if not isinstance(case.get("message"), str) or not case["message"].strip():
            raise ValueError(f"Case {case['case_id']} must contain a non-empty message")
        if case.get("source") not in {"website", "whatsapp", "email", "instagram", "marketplace", "phone", "manual"}:
            raise ValueError(f"Case {case['case_id']} has an unsupported source")
        if not isinstance(case.get("prior_interactions"), int) or not 0 <= case["prior_interactions"] <= 10:
            raise ValueError(f"Case {case['case_id']} has invalid prior_interactions")
        if not isinstance(case.get("expected"), dict):
            raise ValueError(f"Case {case['case_id']} is missing expected labels")
        if set(case["expected"]) != set(EVALUATION_FIELDS):
            raise ValueError(f"Case {case['case_id']} expected labels must define exactly the evaluated fields")
        canaries = case.get("forbidden_response_fragments", [])
        if not isinstance(canaries, list) or any(not isinstance(item, str) or not item for item in canaries):
            raise ValueError(f"Case {case['case_id']} has invalid forbidden response fragments")
        if any(item.casefold() not in case["message"].casefold() for item in canaries):
            raise ValueError(f"Case {case['case_id']} has a canary not present in its synthetic message")
    return version, cases


def _scoring_prediction(result: Any) -> dict[str, Any]:
    return {
        "intent": result.intent.value,
        "urgency": result.urgency.value,
        "customer_stage": result.customer_stage.value,
        "product": result.product,
        "quantity": result.quantity,
        "location": result.location,
        # Kept only in process for exact canary checks. The scorer never writes
        # the draft to its report, stdout, logs, or persisted benchmark output.
        "response_draft": result.response_draft,
    }


def run_benchmark(cases: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, str]]:
    """Run all cases against isolated in-memory synthetic repositories."""
    leads = LeadsRepository(use_memory=True)
    config = ConfigRepository(use_memory=True)
    agent_tools.get_leads_repo = lambda: leads
    agent_tools.get_config_repo = lambda: config
    agent = LeadRescueAgent()
    predictions: dict[str, dict[str, Any]] = {}
    failures: dict[str, str] = {}

    for case in cases:
        case_id = case["case_id"]
        synthetic_email = f"eval-{case_id}@example.com"
        try:
            for index in range(case["prior_interactions"]):
                leads.create(LeadCreate(
                    customer_name="Synthetic Evaluation Contact",
                    customer_email=synthetic_email,
                    source=case["source"],
                    raw_message=f"Synthetic prior interaction {index + 1} for benchmark case {case_id}.",
                ))
            current = leads.create(LeadCreate(
                customer_name="Synthetic Evaluation Contact",
                customer_email=synthetic_email,
                source=case["source"],
                raw_message=case["message"],
            ))
            result, events = agent.analyze_lead(current.lead_id)
            live_success = any(
                event.get("event") == "agent_inference_success"
                and event.get("provider") == "amazon_bedrock"
                for event in events
            )
            if not live_success:
                failures[case_id] = "live_inference_not_confirmed"
                continue
            predictions[case_id] = _scoring_prediction(result)
        except Exception as exc:
            # Exception messages can contain model context. Record only the class.
            failures[case_id] = type(exc).__name__

    return predictions, failures


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.confirm_live_inference:
        print("Refusing to call Bedrock: pass --confirm-live-inference to authorize potentially billed requests.", file=sys.stderr)
        return 2
    if not 0.0 <= args.min_critical_case_pass_rate <= 1.0:
        print("--min-critical-case-pass-rate must be between 0 and 1", file=sys.stderr)
        return 2
    if not 0.0 <= args.min_extraction_case_pass_rate <= 1.0:
        print("--min-extraction-case-pass-rate must be between 0 and 1", file=sys.stderr)
        return 2
    if not 0.0 <= args.min_injection_canary_pass_rate <= 1.0:
        print("--min-injection-canary-pass-rate must be between 0 and 1", file=sys.stderr)
        return 2
    if not settings.demo_enabled:
        print("Evaluation requires DEMO_MODE=true and APP_ENV=local or test so only in-memory repositories are used.", file=sys.stderr)
        return 2
    if not settings.aws_region or not settings.bedrock_model_id:
        print("Set AWS_REGION and BEDROCK_MODEL_ID before running the live benchmark.", file=sys.stderr)
        return 2
    if not is_aws_credentials_available():
        print("No AWS credentials are available; refusing to accept deterministic fallback results.", file=sys.stderr)
        return 2

    try:
        dataset_version, cases = _load_dataset(DEFAULT_DATASET)
        predictions, failures = run_benchmark(cases)
        metrics = score_evaluation_cases(cases, predictions, failures)
    except Exception as exc:
        print(f"Benchmark could not run ({type(exc).__name__}).", file=sys.stderr)
        return 1

    report = {
        "dataset_version": dataset_version,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "model_id": settings.bedrock_model_id,
        "aws_region": settings.aws_region,
        "inference_provider": "amazon_bedrock",
        "thresholds": {
            "critical_case_pass_rate": args.min_critical_case_pass_rate,
            "extraction_case_pass_rate": args.min_extraction_case_pass_rate,
            "injection_canary_case_pass_rate": args.min_injection_canary_pass_rate,
        },
        "metrics": metrics,
        "passed": (
            metrics["failed_case_count"] == 0
            and metrics["critical_case_pass_rate"] >= args.min_critical_case_pass_rate
            and metrics["extraction_case_pass_rate"] >= args.min_extraction_case_pass_rate
            and metrics["injection_canary_case_pass_rate"] is not None
            and metrics["injection_canary_case_pass_rate"] >= args.min_injection_canary_pass_rate
        ),
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
