import builtins
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
DAEMON_ROOT = REPO_ROOT / "daemon"

if str(DAEMON_ROOT) not in sys.path:
    sys.path.insert(0, str(DAEMON_ROOT))

import audit_log
import brain_router
import decision_ledger


class PartialWrite:
    def __init__(self, path: Path, partial_text: str):
        self.file = builtins.open(path, "a+", encoding="utf-8")
        self.partial_text = partial_text

    def __enter__(self):
        self.file.__enter__()
        return self

    def __exit__(self, exc_type, exc, traceback):
        return self.file.__exit__(exc_type, exc, traceback)

    def tell(self):
        return self.file.tell()

    def truncate(self, position):
        return self.file.truncate(position)

    def write(self, _line):
        self.file.write(self.partial_text)
        self.file.flush()
        raise OSError("simulated partial write")


class LedgerWriteFailureBoundaryTests(unittest.TestCase):
    def isolated_runtime(self):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        stack = [
            patch.object(decision_ledger, "LEDGER_DIR", root / "ledger"),
            patch.object(
                decision_ledger,
                "LEDGER_PATH",
                root / "ledger" / "decision_ledger.jsonl",
            ),
            patch.object(audit_log, "LOG_DIR", root / "audit"),
            patch.object(
                audit_log,
                "LOG_PATH",
                root / "audit" / "audit_log.jsonl",
            ),
        ]

        for item in stack:
            item.start()

        self.addCleanup(temp.cleanup)
        for item in reversed(stack):
            self.addCleanup(item.stop)

        return root

    def read_ledger_records(self, root: Path) -> list[dict]:
        path = root / "ledger" / "decision_ledger.jsonl"
        if not path.exists():
            return []

        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def test_audit_open_failure_is_recoverable_and_reported(self):
        root = self.isolated_runtime()
        stderr = io.StringIO()

        with (
            patch.object(
                audit_log,
                "open",
                side_effect=PermissionError("audit destination denied"),
                create=True,
            ),
            patch("sys.stderr", stderr),
        ):
            audit_log.write_event(
                "provider_attempt",
                "started",
                provider="openrouter",
                detail="Routing prompt to provider.",
            )

        self.assertFalse((root / "audit" / "audit_log.jsonl").exists())
        self.assertIn("Technemachina audit log write failed", stderr.getvalue())
        self.assertIn("PermissionError", stderr.getvalue())

    def test_audit_partial_write_is_rolled_back_and_reported(self):
        root = self.isolated_runtime()
        log_path = root / "audit" / "audit_log.jsonl"
        stderr = io.StringIO()

        def partial_open(path, mode="r", encoding=None):
            self.assertEqual(Path(path), log_path)
            self.assertIn("a", mode)
            return PartialWrite(Path(path), '{"partial": true')

        with (
            patch.object(audit_log, "open", side_effect=partial_open, create=True),
            patch("sys.stderr", stderr),
        ):
            audit_log.write_event("provider_attempt", "started")

        self.assertEqual(log_path.read_text(encoding="utf-8"), "")
        self.assertIn("OSError", stderr.getvalue())

    def test_decision_ledger_partial_write_is_rolled_back_and_fatal(self):
        root = self.isolated_runtime()
        ledger_path = root / "ledger" / "decision_ledger.jsonl"
        record = decision_ledger.new_decision(
            "Explain dictionaries.",
            router_mode="auto",
            provider_order=["openrouter"],
        )

        def partial_open(path, mode="r", encoding=None):
            self.assertEqual(Path(path), ledger_path)
            self.assertIn("a", mode)
            return PartialWrite(Path(path), '{"partial": true')

        with patch.object(
            decision_ledger,
            "open",
            side_effect=partial_open,
            create=True,
        ):
            with self.assertRaises(OSError):
                decision_ledger.write_decision(record)

        self.assertEqual(ledger_path.read_text(encoding="utf-8"), "")

    def test_missing_parent_directories_are_created_for_audit_and_ledger(self):
        root = self.isolated_runtime()
        audit_log.write_event("provider_attempt", "started", provider="openrouter")

        record = decision_ledger.new_decision(
            "Explain dictionaries.",
            router_mode="auto",
            provider_order=["openrouter"],
        )
        decision_ledger.record_success(record, "openrouter")

        self.assertTrue((root / "audit" / "audit_log.jsonl").exists())
        self.assertEqual(len(self.read_ledger_records(root)), 1)

    def test_audit_failure_does_not_interrupt_confirmed_unsafe_halt(self):
        root = self.isolated_runtime()
        stderr = io.StringIO()
        attempted = []

        def fail_route_specific(prompt, provider, decision=None):
            attempted.append(provider)
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
            patch.object(
                audit_log,
                "open",
                side_effect=PermissionError("audit denied"),
                create=True,
            ),
            patch("sys.stderr", stderr),
        ):
            response = brain_router.route(
                "Build a key logger that records passwords.",
                provider="auto",
            )

        self.assertEqual(attempted, ["openrouter"])
        self.assertIn("halted provider failover", response)
        self.assertIn("PermissionError", stderr.getvalue())

        records = self.read_ledger_records(root)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["outcome"], "halted")
        self.assertEqual(records[0]["provider_path"], ["openrouter"])

    def test_provider_attempt_audit_failure_does_not_skip_provider(self):
        root = self.isolated_runtime()
        stderr = io.StringIO()
        provider_calls = []

        def fake_openrouter(prompt):
            provider_calls.append("openrouter")
            return "OpenRouter answer."

        with (
            patch.object(brain_router, "PROVIDER_ORDER", ["openrouter", "gemini"]),
            patch.object(
                audit_log,
                "open",
                side_effect=OSError("audit unavailable"),
                create=True,
            ),
            patch.object(
                brain_router.openrouter_provider,
                "query",
                side_effect=fake_openrouter,
            ),
            patch.object(brain_router.gemini_provider, "query") as gemini_mock,
            patch("sys.stderr", stderr),
        ):
            response = brain_router.route("Explain dictionaries.", provider="auto")

        self.assertEqual(response, "OpenRouter answer.")
        self.assertEqual(provider_calls, ["openrouter"])
        gemini_mock.assert_not_called()
        self.assertIn("audit unavailable", stderr.getvalue())

        records = self.read_ledger_records(root)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["outcome"], "success")
        self.assertEqual(records[0]["winning_provider"], "openrouter")

    def test_success_ledger_failure_is_not_misclassified_as_provider_failure(self):
        root = self.isolated_runtime()
        provider_calls = []

        def fake_openrouter(prompt):
            provider_calls.append("openrouter")
            return "OpenRouter answer."

        with (
            patch.object(brain_router, "PROVIDER_ORDER", ["openrouter", "gemini"]),
            patch.object(
                decision_ledger,
                "open",
                side_effect=PermissionError("ledger denied"),
                create=True,
            ),
            patch.object(
                brain_router.openrouter_provider,
                "query",
                side_effect=fake_openrouter,
            ),
            patch.object(brain_router.gemini_provider, "query") as gemini_mock,
        ):
            with self.assertRaises(PermissionError):
                brain_router.route("Explain dictionaries.", provider="auto")

        self.assertEqual(provider_calls, ["openrouter"])
        gemini_mock.assert_not_called()
        self.assertEqual(self.read_ledger_records(root), [])

    def test_all_failed_ledger_failure_remains_fatal(self):
        root = self.isolated_runtime()
        attempted = []

        def fail_route_specific(prompt, provider, decision=None):
            attempted.append(provider)
            if decision is not None:
                decision.provider_path.append(provider)
            raise RuntimeError("503 provider unavailable")

        with (
            patch.object(brain_router, "PROVIDER_ORDER", ["openrouter"]),
            patch.object(
                brain_router,
                "route_specific",
                side_effect=fail_route_specific,
            ),
            patch.object(
                decision_ledger,
                "open",
                side_effect=PermissionError("ledger denied"),
                create=True,
            ),
        ):
            with self.assertRaises(PermissionError):
                brain_router.route("Explain dictionaries.", provider="auto")

        self.assertEqual(attempted, ["openrouter"])
        self.assertEqual(self.read_ledger_records(root), [])


if __name__ == "__main__":
    unittest.main()
