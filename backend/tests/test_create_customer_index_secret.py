import json
import unittest

from scripts.create_customer_index_secret import create_customer_index_secret


class FakeSecretsManager:
    def __init__(self, password="a" * 64):
        self.password = password
        self.create_request = None

    def get_random_password(self, **kwargs):
        self.random_request = kwargs
        return {"RandomPassword": self.password}

    def create_secret(self, **kwargs):
        self.create_request = kwargs
        return {"ARN": "arn:aws:secretsmanager:ap-south-1:123456789012:secret:index-key-abcd"}


class CustomerIndexSecretTests(unittest.TestCase):
    def test_generates_secret_in_service_and_returns_only_arn(self):
        client = FakeSecretsManager()

        arn = create_customer_index_secret(client, "leadrescue/customer-index")

        self.assertEqual(arn, "arn:aws:secretsmanager:ap-south-1:123456789012:secret:index-key-abcd")
        self.assertEqual(client.random_request, {"PasswordLength": 64, "ExcludePunctuation": True})
        stored = json.loads(client.create_request["SecretString"])
        self.assertEqual(stored["hmac_key"], client.password)
        self.assertNotIn("KmsKeyId", client.create_request)

    def test_uses_optional_customer_managed_kms_key(self):
        client = FakeSecretsManager()

        create_customer_index_secret(client, "leadrescue/customer-index", "alias/customer-secrets")

        self.assertEqual(client.create_request["KmsKeyId"], "alias/customer-secrets")

    def test_rejects_short_generated_secret(self):
        client = FakeSecretsManager(password="short")

        with self.assertRaisesRegex(RuntimeError, "valid customer index key"):
            create_customer_index_secret(client, "leadrescue/customer-index")
