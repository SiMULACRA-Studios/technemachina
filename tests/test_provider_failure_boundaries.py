import json
import inspect
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[1]
DAEMON_ROOT = REPO_ROOT / "daemon"

if str(DAEMON_ROOT) not in sys.path:
    sys.path.insert(0, str(DAEMON_ROOT))

import ai
import app
import audit_log
import brain_router
import decision_ledger
import memory
from providers import gemini_provider


class FailingGeminiModels:
    def __init__(self):
        self.attempts = []

    def generate_content(self, *, model, contents):
        self.attempts.append(model)
        raise RuntimeError(f"503 unavailable from {model}")


class FailingGeminiClient:
    def __init__(self, models):
        self.models = models


class ProviderFailureBoundaryTests(unittest.TestCase):
    def isolated_runtime(self):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        stack = [
            patch.object(decision_ledger, "LEDGER_DIR", root),
            patch.object(decision_ledger, "LEDGER_PATH", root / "decision_ledger.jsonl"),
            patch.object(audit_log, "LOG_DIR", root),
            patch.object(audit_log, "LOG_PATH", root / "audit_log.jsonl"),
        ]

        for item in stack:
            item.start()

        self.addCleanup(temp.cleanup)
        for item in reversed(stack):
            self.addCleanup(item.stop)

        return root

    def read_ledger_records(self, root: Path) -> list[dict]:
        path = root / "decision_ledger.jsonl"
        if not path.exists():
            return []

        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def test_gemini_exhaustion_raises_after_all_models_fail(self):
        models = FailingGeminiModels()

        with patch.object(
            gemini_provider,
            "get_client",
            return_value=FailingGeminiClient(models),
        ):
            with self.assertRaises(RuntimeError) as context:
                gemini_provider.query("Explain a provider outage.")

        self.assertIn("All Gemini models failed", str(context.exception))
        self.assertEqual(
            models.attempts,
            [
                "gemini-2.5-flash",
                "gemini-2.5-flash-lite",
            ],
        )

    def test_all_provider_failure_records_truthful_ledger_and_raises(self):
        root = self.isolated_runtime()

        def fail_route_specific(prompt, provider, decision=None):
            if decision is not None:
                decision.provider_path.append(provider)
            raise RuntimeError("503 provider unavailable")

        with (
            patch.object(brain_router, "PROVIDER_ORDER", ["openrouter", "gemini"]),
            patch.object(
                brain_router,
                "route_specific",
                side_effect=fail_route_specific,
            ),
        ):
            with self.assertRaises(RuntimeError) as context:
                brain_router.route("Explain a total provider outage.", provider="auto")

        self.assertIn("All configured providers failed", str(context.exception))

        records = self.read_ledger_records(root)
        self.assertEqual(len(records), 1)

        record = records[0]
        self.assertEqual(record["outcome"], "all_failed")
        self.assertIsNone(record["winning_provider"])
        self.assertEqual(record["router_mode"], "auto")
        self.assertEqual(record["provider_order"], ["openrouter", "gemini"])
        self.assertEqual(record["provider_path"], ["openrouter", "gemini"])
        self.assertEqual(
            [failure["provider"] for failure in record["provider_failures"]],
            ["openrouter", "gemini"],
        )

    def test_failover_success_records_winning_provider(self):
        root = self.isolated_runtime()
        attempts = []

        def fake_route_specific(prompt, provider, decision=None):
            attempts.append(provider)
            if decision is not None:
                decision.provider_path.append(provider)

            if provider == "openrouter":
                raise RuntimeError("503 upstream unavailable")

            return "Gemini recovered answer."

        with (
            patch.object(brain_router, "PROVIDER_ORDER", ["openrouter", "gemini"]),
            patch.object(brain_router, "route_specific", side_effect=fake_route_specific),
        ):
            response = brain_router.route("Explain a recoverable outage.", provider="auto")

        self.assertEqual(response, "Gemini recovered answer.")
        self.assertEqual(attempts, ["openrouter", "gemini"])

        records = self.read_ledger_records(root)
        self.assertEqual(len(records), 1)

        record = records[0]
        self.assertEqual(record["outcome"], "success")
        self.assertEqual(record["winning_provider"], "gemini")
        self.assertEqual(record["provider_path"], ["openrouter", "gemini"])
        self.assertEqual(
            [failure["provider"] for failure in record["provider_failures"]],
            ["openrouter"],
        )

    def test_total_provider_failure_does_not_save_assistant_memory(self):
        root = self.isolated_runtime()
        db_path = root / "database.db"

        with patch.object(memory, "DB_PATH", db_path):
            memory.init_db()

            with patch.object(
                ai,
                "route",
                side_effect=RuntimeError("All configured providers failed."),
            ):
                with self.assertRaises(RuntimeError):
                    ai.query_model("Remember this failed prompt.", "auto")

            with sqlite3.connect(db_path) as conn:
                rows = conn.execute(
                    "SELECT role, content FROM history ORDER BY id"
                ).fetchall()

        self.assertEqual(rows, [("user", "Remember this failed prompt.")])
        assistant_rows = [
            row
            for row in rows
            if row[0] == "assistant"
        ]
        self.assertEqual(assistant_rows, [])

    def test_explain_and_debug_return_5xx_when_provider_routing_raises(self):
        self.assertTrue(inspect.iscoroutinefunction(app.handle_explain))
        self.assertTrue(inspect.iscoroutinefunction(app.handle_debug))
        self.assertNotIn(Exception, app.app.exception_handlers)

        client = TestClient(
            app.app,
            base_url="http://localhost",
            raise_server_exceptions=False,
        )
        route_failure = RuntimeError("All configured providers failed.")
        route_mock = Mock(side_effect=route_failure)

        with (
            patch.object(app.ai, "save_message"),
            patch.object(app.ai, "route", route_mock),
        ):
            explain = client.post(
                "/explain",
                json={"code": "print('hello')", "model": "auto"},
            )
            debug = client.post(
                "/debug",
                json={"code": "print('hello')", "model": "auto"},
            )

        self.assertEqual(route_mock.call_count, 2)
        self.assertGreaterEqual(explain.status_code, 500)
        self.assertGreaterEqual(debug.status_code, 500)


if __name__ == "__main__":
    unittest.main()
