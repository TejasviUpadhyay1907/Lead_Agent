import importlib.util
from pathlib import Path
import sys
import unittest

SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "validate_bedrock_profile.py"
SPEC = importlib.util.spec_from_file_location("validate_bedrock_profile", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
preflight = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = preflight
SPEC.loader.exec_module(preflight)


def profile_document():
    return {
        "inferenceProfileId": "us.amazon.nova-lite-v1:0",
        "inferenceProfileArn": (
            "arn:aws:bedrock:us-east-1:123456789012:"
            "inference-profile/us.amazon.nova-lite-v1:0"
        ),
        "status": "ACTIVE",
        "type": "SYSTEM_DEFINED",
        "models": [
            {"modelArn": "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-lite-v1:0"},
            {"modelArn": "arn:aws:bedrock:us-east-2::foundation-model/amazon.nova-lite-v1:0"},
        ],
    }


class BedrockProfilePreflightTests(unittest.TestCase):
    def validate(self, profile, approved=("us-east-1", "us-east-2")):
        return preflight.validate_profile_document(
            profile,
            profile_id="us.amazon.nova-lite-v1:0",
            foundation_model_id="amazon.nova-lite-v1:0",
            source_region="us-east-1",
            approved_destination_regions=approved,
        )

    def test_accepts_active_matching_profile_with_approved_destinations(self):
        result = self.validate(profile_document())
        self.assertEqual(result.destination_regions, ("us-east-1", "us-east-2"))
        self.assertTrue(result.profile_arn.endswith("inference-profile/us.amazon.nova-lite-v1:0"))

    def test_rejects_inactive_profile(self):
        profile = profile_document()
        profile["status"] = "INACTIVE"
        with self.assertRaisesRegex(ValueError, "not ACTIVE"):
            self.validate(profile)

    def test_rejects_model_mismatch(self):
        profile = profile_document()
        profile["models"][1]["modelArn"] = (
            "arn:aws:bedrock:us-east-2::foundation-model/amazon.nova-pro-v1:0"
        )
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.validate(profile)

    def test_rejects_unapproved_destination(self):
        with self.assertRaisesRegex(ValueError, "absent from the customer-approved"):
            self.validate(profile_document(), approved=("us-east-1",))

    def test_rejects_non_system_profile(self):
        profile = profile_document()
        profile["type"] = "APPLICATION"
        with self.assertRaisesRegex(ValueError, "Only system-defined"):
            self.validate(profile)

    def test_rejects_profile_from_different_source_region(self):
        profile = profile_document()
        profile["inferenceProfileArn"] = profile["inferenceProfileArn"].replace(
            "bedrock:us-east-1:", "bedrock:us-west-2:"
        )
        with self.assertRaisesRegex(ValueError, "source region"):
            self.validate(profile)
