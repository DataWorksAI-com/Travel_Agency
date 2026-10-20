"""Coverage and source-label checks; no network or inference required."""
import json
import unittest
from unittest.mock import Mock, patch

from desktop.bundled_data import destination_info, _general_guidance


class DestinationCoverageTests(unittest.TestCase):
    def test_snapshot_match_does_not_call_model(self):
        with patch("desktop.bundled_data._general_guidance") as fallback:
            result = json.loads(destination_info("  CANCUN  "))
        self.assertEqual(result["destination"]["name"], "Cancún")
        fallback.assert_not_called()

    def test_missing_place_is_labelled_unverified(self):
        with patch("desktop.bundled_data._general_guidance", return_value="Which area in Colorado?") as fallback:
            result = json.loads(destination_info("Colorado"))
        fallback.assert_called_once_with("Colorado")
        self.assertTrue(result["available"])
        self.assertFalse(result["verified"])
        self.assertEqual(result["source"], "Local Qwen model knowledge")
        self.assertIn("unverified", result["note"])
        self.assertEqual(result["general_guidance"], "Which area in Colorado?")

    def test_model_failure_does_not_fabricate_or_leak(self):
        with patch("desktop.bundled_data._general_guidance", side_effect=RuntimeError("private detail")):
            result = json.loads(destination_info("Colorado"))
        self.assertFalse(result["available"])
        self.assertNotIn("general_guidance", result)
        self.assertNotIn("private detail", json.dumps(result))

    def test_plain_local_call_and_empty_response(self):
        model = Mock()
        model.invoke.return_value.content = ""
        with patch("local_llm.local_enabled", return_value=True), patch("local_llm.local_model", return_value=model):
            with self.assertRaises(ValueError):
                _general_guidance("Colorado")
        model.invoke.assert_called_once()

    def test_empty_input_does_not_call_model(self):
        with patch("desktop.bundled_data._general_guidance") as fallback:
            self.assertFalse(json.loads(destination_info("  "))["available"])
        fallback.assert_not_called()


if __name__ == "__main__":
    unittest.main()
