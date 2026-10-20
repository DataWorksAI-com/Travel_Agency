"""Local-only routing guardrails; no live cloud calls."""

import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_llm import local_settings, local_model


class LocalRoutingTests(unittest.TestCase):
    def test_rejects_remote_or_credentialed_endpoint(self):
        for address in ["https://api.openai.com/v1", "http://localhost.example.org/v1", "http://name:password@localhost:1234/v1", "file:///v1", "http://localhost:1234/v1?proxy=remote", "http://localhost:1234/other"]:
            with self.subTest(address=address), patch.dict(os.environ, {"TRAVEL_LOCAL_BASE_URL": address}):
                with self.assertRaises(ValueError):
                    local_settings()

    def test_explicit_local_client_ignores_cloud_endpoint_and_key(self):
        with patch.dict(os.environ, {"TRAVEL_LOCAL_BASE_URL": "http://127.0.0.1:1234/v1", "TRAVEL_LOCAL_MODEL": "test-model", "OPENAI_API_KEY": "unused-cloud-fixture", "OPENAI_API_BASE": "https://example.org/v1", "OPENAI_BASE_URL": "https://example.org/v1"}):
            model = local_model()
            self.assertEqual(model.openai_api_base, "http://127.0.0.1:1234/v1")
            self.assertEqual(model.model_name, "test-model")
            self.assertEqual(model.openai_api_key.get_secret_value(), "local-no-cloud-key")
            self.assertEqual(model.max_retries, 0)


if __name__ == "__main__":
    unittest.main()
