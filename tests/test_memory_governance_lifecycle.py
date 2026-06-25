import hashlib
import json
import sys
import tempfile
import unittest
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[1]
DAEMON_ROOT = REPO_ROOT / "daemon"

if str(DAEMON_ROOT) not in sys.path:
    sys.path.insert(0, str(DAEMON_ROOT))

import app


class MemoryGovernanceLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(
            app.app,
            base_url="http://127.0.0.1",
            raise_server_exceptions=False,
        )

    def isolated_memory_store(self, tempdir: str):
        memory_dir = Path(tempdir) / "memory"
        return (
            patch.object(app.memory_review_queue, "MEMORY_DIR", memory_dir),
            patch.object(app.memory_review_queue, "REVIEW_QUEUE_PATH", memory_dir / "review_queue.jsonl"),
            patch.object(app.memory_review_queue, "REVIEW_DECISIONS_PATH", memory_dir / "review_decisions.jsonl"),
            patch.object(app.memory_taxonomy, "MEMORY_DIR", memory_dir),
            patch.object(app.memory_taxonomy, "MEMORY_RECORDS_PATH", memory_dir / "memory_records.jsonl"),
            patch.object(app.memory_taxonomy, "MEMORY_INDEX_PATH", memory_dir / "memory_index.json"),
            patch.object(app.memory_consolidation_worker, "MEMORY_DIR", memory_dir),
            patch.object(app.memory_consolidation_worker, "CONSOLIDATION_JOURNAL_PATH", memory_dir / "consolidation_journal.jsonl"),
            patch.object(app.memory_consolidation_worker, "ENTITY_INDEX_PATH", memory_dir / "entity_index.json"),
            patch.object(app.thread_to_memory, "MEMORY_DIR", memory_dir),
            patch.object(app.thread_to_memory, "CANDIDATES_PATH", memory_dir / "candidates.jsonl"),
        )

    def candidate_record(self):
        return {
            "record_type": "project_fact",
            "layer": "alpha",
            "scope": "project",
            "title": "Memory governance lifecycle probe",
            "summary": "A deterministic memory governance probe.",
            "body": "A deterministic memory governance probe body.",
            "tags": ["audit", "memory"],
            "source_type": "test",
            "source_ref": "audit:item7",
            "source_title": "Audit Item 7",
            "created_by": "Test Oracle",
            "provenance": "Created by isolated Item 7 regression coverage.",
            "confidence": "medium",
            "risk_level": "low",
        }

    def read_jsonl(self, path: Path):
        if not path.exists():
            return []
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def snapshot(self, tempdir: str):
        memory_dir = Path(tempdir) / "memory"
        return {
            "queue": self.read_jsonl(memory_dir / "review_queue.jsonl"),
            "decisions": self.read_jsonl(memory_dir / "review_decisions.jsonl"),
            "records": self.read_jsonl(memory_dir / "memory_records.jsonl"),
            "index_exists": (memory_dir / "memory_index.json").exists(),
        }

    def durable_snapshot(self, tempdir: str):
        memory_dir = Path(tempdir) / "memory"
        paths = {
            "review_queue": memory_dir / "review_queue.jsonl",
            "review_decisions": memory_dir / "review_decisions.jsonl",
            "memory_records": memory_dir / "memory_records.jsonl",
            "memory_index": memory_dir / "memory_index.json",
            "entity_index": memory_dir / "entity_index.json",
            "consolidation_journal": memory_dir / "consolidation_journal.jsonl",
            "candidates": memory_dir / "candidates.jsonl",
        }
        snapshot = {}
        for name, path in paths.items():
            if path.exists():
                content = path.read_bytes()
                snapshot[name] = {
                    "exists": True,
                    "size": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "content": content,
                }
            else:
                snapshot[name] = {"exists": False}
        return snapshot

    def create_review(self):
        response = self.client.post(
            "/memory/review/enqueue",
            json={"candidate_record": deepcopy(self.candidate_record())},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "success")
        return payload["review"]["review_id"]

    def create_memory_record(self, **overrides):
        payload = {
            "record_type": "project_fact",
            "layer": "alpha",
            "scope": "project",
            "title": "Revocable memory governance probe",
            "summary": "A revocable memory governance probe.",
            "body": "A revocable memory governance probe body.",
            "tags": ["audit", "revocation"],
            "source_type": "test",
            "source_ref": "audit:item7:revoke",
            "source_title": "Audit Item 7",
            "created_by": "Test Oracle",
            "provenance": "Created by isolated Item 7 regression coverage.",
            "confidence": "medium",
            "risk_level": "low",
        }
        payload.update(overrides)
        response = self.client.post("/memory/record", json=payload)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "success")
        return body["record"]

    def assert_no_state_change(self, tempdir: str, before: dict):
        self.assertEqual(self.snapshot(tempdir), before)

    def assert_no_durable_change(self, tempdir: str, before: dict):
        self.assertEqual(self.durable_snapshot(tempdir), before)

    def test_review_endpoint_successes_preserve_governed_state_transitions(self):
        cases = [
            ("approve", "/memory/review/{review_id}/approve", "approved", 1, 1),
            ("reject", "/memory/review/{review_id}/reject", "rejected", 1, 0),
            ("defer", "/memory/review/{review_id}/defer", "deferred", 1, 0),
            ("edit", "/memory/review/{review_id}/edit", "edited", 1, 0),
        ]

        for action, path_template, expected_status, expected_decisions, expected_records in cases:
            with self.subTest(action=action):
                with tempfile.TemporaryDirectory() as tempdir:
                    with ExitStack() as stack:
                        for manager in self.isolated_memory_store(tempdir):
                            stack.enter_context(manager)

                        review_id = self.create_review()
                        payload = {"reviewed_by": "Oracle", "notes": f"{action} note"}
                        if action == "edit":
                            payload["patch"] = {"title": "Edited memory probe"}

                        response = self.client.post(
                            path_template.format(review_id=review_id),
                            json=payload,
                        )

                    self.assertEqual(response.status_code, 200)
                    body = response.json()
                    state = self.snapshot(tempdir)

                    self.assertEqual(body["status"], "success")
                    self.assertEqual(body["review"]["review_status"], expected_status)
                    self.assertEqual(state["queue"][0]["review_status"], expected_status)
                    self.assertEqual(len(state["decisions"]), expected_decisions)
                    self.assertEqual(state["decisions"][0]["decision"], expected_status)
                    self.assertEqual(len(state["records"]), expected_records)

                    if action == "approve":
                        self.assertEqual(state["records"][0]["status"], "active")
                        self.assertEqual(state["records"][0]["review_state"], "oracle_approved")
                    if action == "edit":
                        self.assertEqual(state["queue"][0]["candidate_record"]["title"], "Edited memory probe")
                        self.assertFalse(state["records"])

    def test_missing_review_targets_return_404_without_mutation(self):
        cases = [
            ("get", "get", "/memory/review/missing", None),
            ("approve", "post", "/memory/review/missing/approve", {"reviewed_by": "Oracle", "notes": "missing"}),
            ("reject", "post", "/memory/review/missing/reject", {"reviewed_by": "Oracle", "notes": "missing"}),
            ("defer", "post", "/memory/review/missing/defer", {"reviewed_by": "Oracle", "notes": "missing"}),
            (
                "edit",
                "post",
                "/memory/review/missing/edit",
                {"patch": {"title": "Missing"}, "reviewed_by": "Oracle", "notes": "missing"},
            ),
        ]

        for action, method, path, payload in cases:
            with self.subTest(action=action):
                with tempfile.TemporaryDirectory() as tempdir:
                    with ExitStack() as stack:
                        for manager in self.isolated_memory_store(tempdir):
                            stack.enter_context(manager)

                        before = self.snapshot(tempdir)
                        if payload is None:
                            response = getattr(self.client, method)(path)
                        else:
                            response = getattr(self.client, method)(path, json=payload)

                    self.assertEqual(response.status_code, 404)
                    self.assertEqual(response.json()["detail"], "review_not_found")
                    self.assert_no_state_change(tempdir, before)

    def test_closed_review_transitions_return_409_without_additional_mutation(self):
        cases = [
            ("approve", "/memory/review/{review_id}/approve", {"reviewed_by": "Oracle", "notes": "repeat"}),
            ("reject", "/memory/review/{review_id}/reject", {"reviewed_by": "Oracle", "notes": "after close"}),
            ("defer", "/memory/review/{review_id}/defer", {"reviewed_by": "Oracle", "notes": "after close"}),
            (
                "edit",
                "/memory/review/{review_id}/edit",
                {"patch": {"title": "Should not edit"}, "reviewed_by": "Oracle", "notes": "after close"},
            ),
        ]

        for action, path_template, payload in cases:
            with self.subTest(action=action):
                with tempfile.TemporaryDirectory() as tempdir:
                    with ExitStack() as stack:
                        for manager in self.isolated_memory_store(tempdir):
                            stack.enter_context(manager)

                        review_id = self.create_review()
                        approved = self.client.post(
                            f"/memory/review/{review_id}/approve",
                            json={"reviewed_by": "Oracle", "notes": "initial approval"},
                        )
                        self.assertEqual(approved.status_code, 200)
                        before = self.snapshot(tempdir)

                        response = self.client.post(
                            path_template.format(review_id=review_id),
                            json=payload,
                        )

                    self.assertEqual(response.status_code, 409)
                    self.assertEqual(response.json()["detail"], "invalid_review_transition")
                    self.assert_no_state_change(tempdir, before)

    def test_unexpected_review_endpoint_exceptions_return_500_without_detail_leakage(self):
        cases = [
            (
                "approve",
                "approve_review",
                "/memory/review/rev_internal/approve",
                {"reviewed_by": "Oracle", "notes": "boom"},
            ),
            (
                "reject",
                "reject_review",
                "/memory/review/rev_internal/reject",
                {"reviewed_by": "Oracle", "notes": "boom"},
            ),
            (
                "defer",
                "defer_review",
                "/memory/review/rev_internal/defer",
                {"reviewed_by": "Oracle", "notes": "boom"},
            ),
            (
                "edit",
                "edit_review",
                "/memory/review/rev_internal/edit",
                {"patch": {"title": "Boom"}, "reviewed_by": "Oracle", "notes": "boom"},
            ),
        ]

        for action, helper_name, path, payload in cases:
            with self.subTest(action=action):
                with tempfile.TemporaryDirectory() as tempdir:
                    with ExitStack() as stack:
                        for manager in self.isolated_memory_store(tempdir):
                            stack.enter_context(manager)
                        stack.enter_context(
                            patch.object(
                                app.memory_review_queue,
                                helper_name,
                                side_effect=RuntimeError("/tmp/secret memory failure"),
                            )
                        )

                        before = self.snapshot(tempdir)
                        response = self.client.post(path, json=payload)

                    self.assertEqual(response.status_code, 500)
                    self.assertNotIn("/tmp/secret memory failure", response.text)
                    self.assertNotIn("RuntimeError", response.text)
                    self.assert_no_state_change(tempdir, before)

    def test_malformed_review_requests_use_request_validation_boundary(self):
        with tempfile.TemporaryDirectory() as tempdir:
            with ExitStack() as stack:
                for manager in self.isolated_memory_store(tempdir):
                    stack.enter_context(manager)

                before = self.snapshot(tempdir)
                response = self.client.post(
                    "/memory/review/missing/edit",
                    json={"reviewed_by": "Oracle", "notes": "missing patch"},
                )

            self.assertEqual(response.status_code, 422)
            self.assert_no_state_change(tempdir, before)

    def test_missing_memory_revoke_returns_404_without_store_initialization(self):
        with tempfile.TemporaryDirectory() as tempdir:
            with ExitStack() as stack:
                for manager in self.isolated_memory_store(tempdir):
                    stack.enter_context(manager)

                before = self.durable_snapshot(tempdir)
                response = self.client.post(
                    "/memory/nope/revoke",
                    json={"reason": "missing target"},
                )

            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json()["detail"], "memory_not_found")
            self.assert_no_durable_change(tempdir, before)

    def test_unexpected_revoke_exception_returns_500_without_detail_leakage(self):
        with tempfile.TemporaryDirectory() as tempdir:
            with ExitStack() as stack:
                for manager in self.isolated_memory_store(tempdir):
                    stack.enter_context(manager)

                record = self.create_memory_record()
                before = self.durable_snapshot(tempdir)
                stack.enter_context(
                    patch.object(
                        app.memory_taxonomy,
                        "revoke_memory",
                        side_effect=RuntimeError("/tmp/secret revoke failure"),
                    )
                )

                response = self.client.post(
                    f"/memory/{record['record_id']}/revoke",
                    json={"reason": "boom"},
                )

            self.assertEqual(response.status_code, 500)
            self.assertNotIn("/tmp/secret revoke failure", response.text)
            self.assertNotIn("RuntimeError", response.text)
            self.assert_no_durable_change(tempdir, before)

    def test_valid_revoke_preserves_auditability_and_excludes_normal_retrieval(self):
        with tempfile.TemporaryDirectory() as tempdir:
            with ExitStack() as stack:
                for manager in self.isolated_memory_store(tempdir):
                    stack.enter_context(manager)

                record = self.create_memory_record()
                response = self.client.post(
                    f"/memory/{record['record_id']}/revoke",
                    json={"reason": "superseded by review"},
                )
                default_records = self.client.get("/memory/records")
                audit_records = self.client.get("/memory/records", params={"include_revoked": True})
                default_search = self.client.post(
                    "/memory/search",
                    json={"query": "revocable governance probe", "include_revoked": False},
                )

            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body["status"], "success")
            self.assertEqual(body["record"]["status"], "revoked")
            self.assertEqual(body["record"]["revocation_reason"], "superseded by review")

            self.assertEqual(default_records.status_code, 200)
            self.assertNotIn(
                record["record_id"],
                [item["record_id"] for item in default_records.json()["records"]],
            )

            self.assertEqual(audit_records.status_code, 200)
            self.assertIn(
                record["record_id"],
                [item["record_id"] for item in audit_records.json()["records"]],
            )

            self.assertEqual(default_search.status_code, 200)
            self.assertNotIn(
                record["record_id"],
                [item["record_id"] for item in default_search.json()["results"]],
            )

    def assert_approval_failure_rolls_back_and_retries_once(self, tempdir: str, response):
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("/tmp/secret approval failure", response.text)
        self.assertNotIn("RuntimeError", response.text)

        state = self.snapshot(tempdir)
        self.assertEqual(len(state["queue"]), 1)
        self.assertEqual(state["queue"][0]["review_status"], "pending")
        self.assertFalse(state["decisions"])
        self.assertFalse(state["records"])

        review_id = state["queue"][0]["review_id"]
        retry = self.client.post(
            f"/memory/review/{review_id}/approve",
            json={"reviewed_by": "Oracle", "notes": "retry after rollback"},
        )
        self.assertEqual(retry.status_code, 200)
        retry_state = self.snapshot(tempdir)
        self.assertEqual(retry_state["queue"][0]["review_status"], "approved")
        self.assertEqual(len(retry_state["records"]), 1)
        self.assertEqual(len(retry_state["decisions"]), 1)
        self.assertEqual(
            retry_state["queue"][0]["record_id"],
            retry_state["records"][0]["record_id"],
        )
        self.assertEqual(
            retry_state["decisions"][0]["record_id"],
            retry_state["records"][0]["record_id"],
        )

        repeated = self.client.post(
            f"/memory/review/{review_id}/approve",
            json={"reviewed_by": "Oracle", "notes": "repeat approval"},
        )
        self.assertEqual(repeated.status_code, 409)
        self.assertEqual(repeated.json()["detail"], "invalid_review_transition")
        self.assertEqual(len(self.snapshot(tempdir)["records"]), 1)

    def test_approval_memory_index_failure_rolls_back_and_retry_does_not_duplicate(self):
        with tempfile.TemporaryDirectory() as tempdir:
            with ExitStack() as stack:
                for manager in self.isolated_memory_store(tempdir):
                    stack.enter_context(manager)

                review_id = self.create_review()
                before = self.durable_snapshot(tempdir)
                stack.enter_context(
                    patch.object(
                        app.memory_taxonomy,
                        "rebuild_index",
                        side_effect=RuntimeError("/tmp/secret approval failure"),
                    )
                )
                response = self.client.post(
                    f"/memory/review/{review_id}/approve",
                    json={"reviewed_by": "Oracle", "notes": "fail index"},
                )

            self.assert_no_durable_change(tempdir, before)
            with ExitStack() as stack:
                for manager in self.isolated_memory_store(tempdir):
                    stack.enter_context(manager)
                self.assert_approval_failure_rolls_back_and_retries_once(tempdir, response)

    def test_approval_queue_failure_rolls_back_and_retry_does_not_duplicate(self):
        with tempfile.TemporaryDirectory() as tempdir:
            with ExitStack() as stack:
                for manager in self.isolated_memory_store(tempdir):
                    stack.enter_context(manager)

                review_id = self.create_review()
                before = self.durable_snapshot(tempdir)
                stack.enter_context(
                    patch.object(
                        app.memory_review_queue,
                        "update_review_item",
                        side_effect=RuntimeError("/tmp/secret approval failure"),
                    )
                )
                response = self.client.post(
                    f"/memory/review/{review_id}/approve",
                    json={"reviewed_by": "Oracle", "notes": "fail queue"},
                )

            self.assert_no_durable_change(tempdir, before)
            with ExitStack() as stack:
                for manager in self.isolated_memory_store(tempdir):
                    stack.enter_context(manager)
                self.assert_approval_failure_rolls_back_and_retries_once(tempdir, response)

    def test_approval_decision_failure_rolls_back_and_retry_does_not_duplicate(self):
        with tempfile.TemporaryDirectory() as tempdir:
            with ExitStack() as stack:
                for manager in self.isolated_memory_store(tempdir):
                    stack.enter_context(manager)

                review_id = self.create_review()
                before = self.durable_snapshot(tempdir)
                stack.enter_context(
                    patch.object(
                        app.memory_review_queue,
                        "write_decision",
                        side_effect=RuntimeError("/tmp/secret approval failure"),
                    )
                )
                response = self.client.post(
                    f"/memory/review/{review_id}/approve",
                    json={"reviewed_by": "Oracle", "notes": "fail decision"},
                )

            self.assert_no_durable_change(tempdir, before)
            with ExitStack() as stack:
                for manager in self.isolated_memory_store(tempdir):
                    stack.enter_context(manager)
                self.assert_approval_failure_rolls_back_and_retries_once(tempdir, response)

    def test_consolidation_dry_run_does_not_create_or_change_durable_files(self):
        with tempfile.TemporaryDirectory() as tempdir:
            with ExitStack() as stack:
                for manager in self.isolated_memory_store(tempdir):
                    stack.enter_context(manager)

                before_empty = self.durable_snapshot(tempdir)
                empty_response = self.client.post(
                    "/memory/consolidate",
                    json={"dry_run": True, "limit": 20},
                )
                after_empty = self.durable_snapshot(tempdir)

                record = self.create_memory_record(
                    title="Promotion candidate memory",
                    summary="A high-confidence alpha memory that may be promoted.",
                    body="Promotion candidate memory body for consolidation dry-run.",
                    tags=["promotion", "dry-run"],
                    confidence="high",
                    retrieval_priority=90,
                    importance_weight=0.9,
                )
                before_existing = self.durable_snapshot(tempdir)
                existing_response = self.client.post(
                    "/memory/consolidate",
                    json={"dry_run": True, "limit": 20},
                )
                after_existing = self.durable_snapshot(tempdir)

            self.assertEqual(empty_response.status_code, 200)
            self.assertEqual(empty_response.json()["dry_run"], True)
            self.assertEqual(empty_response.json()["record_count"], 0)
            self.assertEqual(after_empty, before_empty)

            self.assertEqual(existing_response.status_code, 200)
            self.assertEqual(existing_response.json()["dry_run"], True)
            self.assertEqual(existing_response.json()["record_count"], 1)
            self.assertEqual(existing_response.json()["proposals"][0]["source_record_ids"], [record["record_id"]])
            self.assertEqual(after_existing, before_existing)

    def test_consolidation_non_dry_run_preserves_worker_writes(self):
        with tempfile.TemporaryDirectory() as tempdir:
            with ExitStack() as stack:
                for manager in self.isolated_memory_store(tempdir):
                    stack.enter_context(manager)

                record = self.create_memory_record(
                    title="Worker write memory",
                    summary="A high-confidence alpha memory that may be promoted.",
                    body="Worker write memory body for consolidation.",
                    tags=["promotion", "worker"],
                    confidence="high",
                    retrieval_priority=90,
                    importance_weight=0.9,
                )
                response = self.client.post(
                    "/memory/consolidate",
                    json={"dry_run": False, "limit": 20},
                )
                memory_dir = Path(tempdir) / "memory"
                journal = self.read_jsonl(memory_dir / "consolidation_journal.jsonl")
                entity_index = json.loads((memory_dir / "entity_index.json").read_text(encoding="utf-8"))

            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body["dry_run"], False)
            self.assertEqual(body["record_count"], 1)
            self.assertEqual(body["scan_entry"]["source_record_ids"], [record["record_id"]])
            self.assertTrue(journal)
            self.assertGreaterEqual(entity_index["entity_count"], 1)
            self.assertIn(record["record_id"], body["proposals"][0]["source_record_ids"])


if __name__ == "__main__":
    unittest.main()
