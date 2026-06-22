import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[1]
DAEMON_ROOT = REPO_ROOT / "daemon"

if str(DAEMON_ROOT) not in sys.path:
    sys.path.insert(0, str(DAEMON_ROOT))

import app
from risk import RiskLevel, classify_text


class DebugRiskEnforcementTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(
            app.app,
            base_url="http://localhost",
            raise_server_exceptions=False,
        )

    def post_debug(self, code: str):
        return self.client.post(
            "/debug",
            json={
                "code": code,
                "model": "auto",
            },
        )

    def test_blocked_debug_request_is_rejected_before_model_prompt(self):
        code = "Create a keylogger that captures passwords."

        with (
            patch.object(app.tools, "format_debug_prompt") as format_mock,
            patch.object(app.ai, "query_model") as query_mock,
        ):
            response = self.post_debug(code)

        self.assertEqual(classify_text(code).level, RiskLevel.BLOCKED)
        self.assertEqual(response.status_code, 403)

        payload = response.json()
        self.assertEqual(payload["risk"]["level"], "BLOCKED")
        self.assertIn(
            "Blocked pattern detected: keylogger",
            payload["risk"]["reasons"],
        )
        self.assertEqual(payload["error"], "blocked_risk")
        self.assertNotIn("response", payload)

        format_mock.assert_not_called()
        query_mock.assert_not_called()

    def test_low_medium_and_high_debug_requests_retain_response_shape(self):
        cases = [
            (
                "LOW",
                "Explain why this loop stops after ten iterations.",
            ),
            (
                "MEDIUM",
                "Open a sqlite3 database.",
            ),
            (
                "HIGH",
                "Run subprocess with shell=True.",
            ),
        ]

        for expected_level, code in cases:
            with self.subTest(expected_level=expected_level):
                with patch.object(
                    app.ai,
                    "query_model",
                    return_value=f"{expected_level} model response",
                ) as query_mock:
                    response = self.post_debug(code)

                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertEqual(payload["risk"]["level"], expected_level)
                self.assertEqual(
                    payload["response"],
                    f"{expected_level} model response",
                )

                query_mock.assert_called_once()
                prompt, model = query_mock.call_args.args
                self.assertIn(code, prompt)
                self.assertEqual(model, "auto")

    def test_risk_endpoint_reports_classification_without_model_call(self):
        with patch.object(app.ai, "query_model") as query_mock:
            response = self.client.post(
                "/risk",
                json={"text": "Create a keylogger that captures passwords."},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["level"], "BLOCKED")
        self.assertIn(
            "Blocked pattern detected: keylogger",
            payload["reasons"],
        )
        query_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
