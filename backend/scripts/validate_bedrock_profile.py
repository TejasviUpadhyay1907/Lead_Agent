"""Pre-deployment verification for a tenant-approved Bedrock geo profile.

This checks the live Bedrock control-plane response. It does not deploy resources,
invoke a model, or change account configuration.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from typing import Any, Sequence

@dataclass(frozen=True)
class ProfileValidation:
    profile_id: str
    profile_arn: str
    foundation_model_id: str
    source_region: str
    destination_regions: tuple[str, ...]


def _parse_arn(arn: str) -> tuple[str, str, str, str, str, str]:
    parts = arn.split(":", 5)
    if len(parts) != 6 or parts[0] != "arn":
        raise ValueError("Bedrock returned a malformed ARN")
    return tuple(parts)  # type: ignore[return-value]


def validate_profile_document(
    profile: dict[str, Any],
    *,
    profile_id: str,
    foundation_model_id: str,
    source_region: str,
    approved_destination_regions: Sequence[str],
) -> ProfileValidation:
    """Validate profile identity, model pairing, and a customer-approved region allowlist."""
    if profile.get("status") != "ACTIVE":
        raise ValueError("Bedrock inference profile is not ACTIVE")
    if profile.get("type") != "SYSTEM_DEFINED":
        raise ValueError("Only system-defined geographic inference profiles are supported")
    if profile.get("inferenceProfileId") != profile_id:
        raise ValueError("Bedrock returned a different inference profile ID")

    profile_arn = profile.get("inferenceProfileArn")
    if not isinstance(profile_arn, str):
        raise ValueError("Bedrock response has no inference profile ARN")
    _, _, service, arn_region, _, resource = _parse_arn(profile_arn)
    if service != "bedrock" or arn_region != source_region:
        raise ValueError("Profile ARN does not belong to the requested Bedrock source region")
    if resource != f"inference-profile/{profile_id}":
        raise ValueError("Profile ARN does not match the requested inference profile ID")

    models = profile.get("models")
    if not isinstance(models, list) or not models:
        raise ValueError("Bedrock profile contains no destination model ARNs")

    destination_regions: set[str] = set()
    for item in models:
        model_arn = item.get("modelArn") if isinstance(item, dict) else None
        if not isinstance(model_arn, str):
            raise ValueError("Bedrock profile contains a malformed destination model entry")
        _, _, model_service, region, _, resource = _parse_arn(model_arn)
        if model_service != "bedrock" or not region:
            raise ValueError("Bedrock profile contains a non-regional destination model ARN")
        if resource != f"foundation-model/{foundation_model_id}":
            raise ValueError("Configured foundation model does not match every profile destination")
        destination_regions.add(region)

    approved = {region.strip() for region in approved_destination_regions if region.strip()}
    if not approved:
        raise ValueError("At least one customer-approved destination region is required")
    unapproved = destination_regions - approved
    if unapproved:
        raise ValueError(
            "Profile routes to regions absent from the customer-approved allowlist: "
            + ", ".join(sorted(unapproved))
        )

    return ProfileValidation(
        profile_id=profile_id,
        profile_arn=profile_arn,
        foundation_model_id=foundation_model_id,
        source_region=source_region,
        destination_regions=tuple(sorted(destination_regions)),
    )


def validate_live_profile(
    *,
    profile_id: str,
    foundation_model_id: str,
    source_region: str,
    approved_destination_regions: Sequence[str],
) -> ProfileValidation:
    """Fetch and validate one live profile using the caller's normal AWS credentials."""
    import boto3

    client = boto3.client("bedrock", region_name=source_region)
    profile = client.get_inference_profile(inferenceProfileIdentifier=profile_id)
    return validate_profile_document(
        profile,
        profile_id=profile_id,
        foundation_model_id=foundation_model_id,
        source_region=source_region,
        approved_destination_regions=approved_destination_regions,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only preflight for a Bedrock geographic inference profile. "
            "Provide the complete customer-approved destination region allowlist."
        )
    )
    parser.add_argument("--profile-id", required=True, help="SAM BedrockModelId value")
    parser.add_argument(
        "--foundation-model-id", required=True, help="SAM BedrockFoundationModelId value"
    )
    parser.add_argument("--source-region", required=True, help="SAM deployment AWS Region")
    parser.add_argument(
        "--approved-destination-region",
        action="append",
        required=True,
        help="One approved destination Region; repeat for every customer-approved Region",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = validate_live_profile(
            profile_id=args.profile_id,
            foundation_model_id=args.foundation_model_id,
            source_region=args.source_region,
            approved_destination_regions=args.approved_destination_region,
        )
    except Exception as exc:
        print(f"Bedrock profile preflight failed ({type(exc).__name__}): {exc}", file=sys.stderr)
        return 1

    print(json.dumps({"valid": True, **asdict(result)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
