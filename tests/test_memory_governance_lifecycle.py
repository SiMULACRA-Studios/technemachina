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
            patch.object(app.memory_review_queue, "APPROVAL_OPERATIONS_PATH", memory_dir / "approval_operations.jsonl"),
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

    def explicit_target_candidate_record(self, record_id: str = "candidate_target"):
        candidate = self.candidate_record()
        candidate["record_id"] = record_id
        return candidate

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
            "operations": self.read_jsonl(memory_dir / "approval_operations.jsonl"),
            "records": self.read_jsonl(memory_dir / "memory_records.jsonl"),
            "index_exists": (memory_dir / "memory_index.json").exists(),
        }

    def durable_snapshot(self, tempdir: str):
        memory_dir = Path(tempdir) / "memory"
        paths = {
            "review_queue": memory_dir / "review_queue.jsonl",
            "review_decisions": memory_dir / "review_decisions.jsonl",
            "approval_operations": memory_dir / "approval_operations.jsonl",
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

    def create_explicit_target_review(self, record_id: str = "candidate_target"):
        response = self.client.post(
            "/memory/review/enqueue",
            json={"candidate_record": deepcopy(self.explicit_target_candidate_record(record_id))},
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

    def expected_approval_ids(self, review_id: str):
        return {
            "operation_id": f"approval_{review_id}",
            "record_id": f"mem_{review_id}_approved",
            "decision_id": f"rd_{review_id}_approved",
        }

    def approval_index_count(self, tempdir: str):
        path = Path(tempdir) / "memory" / "memory_index.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8")).get("record_count")

    def write_jsonl(self, path: Path, rows: list[dict]):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + ("\n" if rows else ""),
            encoding="utf-8",
        )

    def approval_operation(
        self,
        review_id: str,
        item: dict,
        *,
        stage: str = "operation_started",
        status: str = "incomplete",
        **overrides,
    ):
        ids = app.memory_review_queue._stable_approval_ids(review_id, item)
        operation = {
            "operation_id": ids["operation_id"],
            "review_id": review_id,
            "candidate_identity": ids["candidate_identity"],
            "intended_memory_record_id": ids["memory_record_id"],
            "intended_decision_id": ids["decision_id"],
            "stage": stage,
            "status": status,
            "created_at": app.memory_review_queue.utc_now(),
            "updated_at": app.memory_review_queue.utc_now(),
            "completed_at": app.memory_review_queue.utc_now() if status == "complete" else None,
            "reviewed_by": "Oracle",
            "notes": "approval conflict fixture",
            "error": "",
        }
        operation.update(overrides)
        return operation

    def approval_decision(self, decision_review_id: str, ids: dict, **overrides):
        decision = {
            "decision_id": ids["decision_id"],
            "review_id": decision_review_id,
            "decision": "approved",
            "reviewed_by": "Oracle",
            "reviewed_at": app.memory_review_queue.utc_now(),
            "notes": "approval conflict fixture",
            "record_id": ids["record_id"],
            "queue_version": app.memory_review_queue.REVIEW_QUEUE_VERSION,
            "policy_version": app.memory_review_queue.POLICY_VERSION,
            "operation_id": ids["operation_id"],
        }
        decision.update(overrides)
        return decision

    def approval_memory(self, operation: dict, item: dict, **overrides):
        memory = app.memory_review_queue._approval_memory_payload(operation, item, "Oracle")
        memory["status"] = "active"
        memory["review_state"] = "oracle_approved"
        memory.update(overrides)
        memory["hash"] = app.memory_review_queue._memory_hash(memory)
        return memory

    def approval_conflict_response(self, review_id: str, reviewed_by: str = "Oracle"):
        return self.client.post(
            f"/memory/review/{review_id}/approve",
            json={"reviewed_by": reviewed_by, "notes": "conflict must stop"},
        )

    def visible_active_record_ids(self, tempdir: str):
        records = self.read_jsonl(Path(tempdir) / "memory" / "memory_records.jsonl")
        return [
            record["record_id"]
            for record in records
            if record.get("status") == "active"
        ]

    def assert_approval_conflict_no_mutation(self, tempdir: str, review_id: str, before: dict):
        before_visible = self.visible_active_record_ids(tempdir)
        response = self.approval_conflict_response(review_id)
        after_visible = self.visible_active_record_ids(tempdir)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "approval_state_conflict")
        self.assertNotIn("RuntimeError", response.text)
        self.assertNotIn(str(Path(tempdir)), response.text)
        self.assert_no_durable_change(tempdir, before)
        self.assertEqual(before_visible, after_visible)

    def approved_review_with_incomplete_operation(self):
        review_id = self.create_review()
        queue = app.memory_review_queue.load_queue(include_closed=True)
        item = queue[0]
        item["review_status"] = "approved"
        item["reviewed_at"] = app.memory_review_queue.utc_now()
        item["reviewed_by"] = "Oracle"
        item["notes"] = "approved but incomplete"
        app.memory_review_queue.save_queue(queue)
        operation = self.approval_operation(review_id, item)
        self.write_jsonl(app.memory_review_queue.APPROVAL_OPERATIONS_PATH, [operation])
        return review_id, item, operation

    def assert_completed_once(
        self,
        tempdir: str,
        review_id: str,
        *,
        expected_reviewer: str = "Oracle",
        repeat_reviewer: str = "Oracle",
    ):
        ids = self.expected_approval_ids(review_id)
        state = self.snapshot(tempdir)
        self.assertEqual(state["queue"][0]["review_status"], "approved")
        self.assertEqual(state["queue"][0]["reviewed_by"], expected_reviewer)
        self.assertEqual([record["record_id"] for record in state["records"]], [ids["record_id"]])
        self.assertEqual(state["records"][0]["created_by"], expected_reviewer)
        self.assertEqual(state["records"][0]["status"], "active")
        self.assertEqual(state["records"][0]["review_state"], "oracle_approved")
        self.assertEqual([decision["decision_id"] for decision in state["decisions"]], [ids["decision_id"]])
        self.assertEqual(state["decisions"][0]["reviewed_by"], expected_reviewer)
        self.assertEqual(state["operations"][0]["operation_id"], ids["operation_id"])
        self.assertEqual(state["operations"][0]["reviewed_by"], expected_reviewer)
        self.assertEqual(state["operations"][0]["status"], "complete")
        self.assertEqual(state["operations"][0]["stage"], "complete")
        self.assertEqual(self.approval_index_count(tempdir), 1)

        retrieval = self.client.post(
            "/memory/search",
            json={"query": "memory governance lifecycle probe", "include_revoked": False},
        )
        self.assertEqual(retrieval.status_code, 200)
        self.assertEqual(
            [result["record_id"] for result in retrieval.json()["results"]],
            [ids["record_id"]],
        )

        repeated = self.client.post(
            f"/memory/review/{review_id}/approve",
            json={"reviewed_by": repeat_reviewer, "notes": "repeat approval"},
        )
        self.assertEqual(repeated.status_code, 409)
        self.assertEqual(repeated.json()["detail"], "invalid_review_transition")

    def assert_retry_completes_once(
        self,
        tempdir: str,
        review_id: str,
        *,
        retry_reviewer: str = "Oracle",
        expected_reviewer: str = "Oracle",
    ):
        retry = self.client.post(
            f"/memory/review/{review_id}/approve",
            json={"reviewed_by": retry_reviewer, "notes": "retry approval"},
        )
        self.assertEqual(retry.status_code, 200)
        self.assert_completed_once(
            tempdir,
            review_id,
            expected_reviewer=expected_reviewer,
            repeat_reviewer=retry_reviewer,
        )
        return retry

    def assert_forward_failure_then_retry(self, tempdir: str, review_id: str, response):
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("/tmp/secret approval failure", response.text)
        self.assertNotIn("RuntimeError", response.text)
        self.assert_retry_completes_once(tempdir, review_id)

    def assert_draft_memory_hidden(self, tempdir: str, review_id: str):
        ids = self.expected_approval_ids(review_id)
        state = self.snapshot(tempdir)
        self.assertEqual([record["record_id"] for record in state["records"]], [ids["record_id"]])
        self.assertEqual(state["records"][0]["status"], "draft")
        self.assertEqual(state["records"][0]["review_state"], "needs_review")
        self.assertEqual(self.approval_index_count(tempdir), 0)

        default_records = self.client.get("/memory/records")
        self.assertEqual(default_records.status_code, 200)
        self.assertNotIn(
            ids["record_id"],
            [record["record_id"] for record in default_records.json()["records"]],
        )

        direct_records = self.client.get("/memory/records", params={"include_revoked": True})
        self.assertEqual(direct_records.status_code, 200)
        direct = {
            record["record_id"]: record
            for record in direct_records.json()["records"]
        }
        self.assertEqual(direct[ids["record_id"]]["status"], "draft")

        search = self.client.post(
            "/memory/search",
            json={"query": "memory governance lifecycle probe", "include_revoked": True},
        )
        self.assertEqual(search.status_code, 200)
        self.assertNotIn(
            ids["record_id"],
            [result["record_id"] for result in search.json()["results"]],
        )

        dry_run = self.client.post(
            "/memory/consolidate",
            json={"dry_run": True, "limit": 20},
        )
        self.assertEqual(dry_run.status_code, 200)
        self.assertEqual(dry_run.json()["record_count"], 0)

    def test_initial_approval_operation_failure_has_no_side_effect_and_retries(self):
        with tempfile.TemporaryDirectory() as tempdir:
            with ExitStack() as stack:
                for manager in self.isolated_memory_store(tempdir):
                    stack.enter_context(manager)

                review_id = self.create_review()
                before = self.durable_snapshot(tempdir)
                stack.enter_context(
                    patch.object(
                        app.memory_review_queue,
                        "_save_approval_operations",
                        side_effect=RuntimeError("/tmp/secret approval failure"),
                    )
                )
                response = self.client.post(
                    f"/memory/review/{review_id}/approve",
                    json={"reviewed_by": "Oracle", "notes": "operation fail"},
                )

            self.assertEqual(response.status_code, 500)
            self.assertNotIn("/tmp/secret approval failure", response.text)
            self.assert_no_durable_change(tempdir, before)
            with ExitStack() as stack:
                for manager in self.isolated_memory_store(tempdir):
                    stack.enter_context(manager)
                self.assert_retry_completes_once(tempdir, review_id)

    def test_missing_explicit_candidate_target_stops_before_approval_effects(self):
        with tempfile.TemporaryDirectory() as tempdir:
            with ExitStack() as stack:
                for manager in self.isolated_memory_store(tempdir):
                    stack.enter_context(manager)

                review_id = self.create_explicit_target_review()
                before = self.durable_snapshot(tempdir)
                response = self.client.post(
                    f"/memory/review/{review_id}/approve",
                    json={"reviewed_by": "ReviewerA", "notes": "missing target"},
                )

            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json()["detail"], "approval_state_conflict")
            self.assertNotIn("candidate_target", response.text)
            self.assertNotIn(str(Path(tempdir)), response.text)
            self.assert_no_durable_change(tempdir, before)
            with ExitStack() as stack:
                for manager in self.isolated_memory_store(tempdir):
                    stack.enter_context(manager)
                state = self.snapshot(tempdir)
                self.assertFalse(state["operations"])
                self.assertFalse(state["decisions"])
                self.assertFalse(state["records"])

    def test_partial_explicit_target_approval_state_does_not_advance_when_target_remains_missing(self):
        with tempfile.TemporaryDirectory() as tempdir:
            with ExitStack() as stack:
                for manager in self.isolated_memory_store(tempdir):
                    stack.enter_context(manager)

                review_id = self.create_explicit_target_review()
                item = app.memory_review_queue.load_queue(include_closed=True)[0]
                operation = self.approval_operation(
                    review_id,
                    item,
                    stage="decision_recorded",
                    reviewed_by="ReviewerA",
                )
                ids = {
                    "operation_id": operation["operation_id"],
                    "record_id": operation["intended_memory_record_id"],
                    "decision_id": operation["intended_decision_id"],
                }
                decision = self.approval_decision(
                    review_id,
                    ids,
                    reviewed_by="ReviewerA",
                    notes="existing partial approval",
                )
                self.write_jsonl(app.memory_review_queue.APPROVAL_OPERATIONS_PATH, [operation])
                self.write_jsonl(app.memory_review_queue.REVIEW_DECISIONS_PATH, [decision])

                before = self.durable_snapshot(tempdir)
                response = self.client.post(
                    f"/memory/review/{review_id}/approve",
                    json={"reviewed_by": "ReviewerB", "notes": "retry missing target"},
                )

            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json()["detail"], "approval_state_conflict")
            self.assertNotIn("candidate_target", response.text)
            self.assert_no_durable_change(tempdir, before)
            with ExitStack() as stack:
                for manager in self.isolated_memory_store(tempdir):
                    stack.enter_context(manager)
                state = self.snapshot(tempdir)
                self.assertEqual(len(state["operations"]), 1)
                self.assertEqual(state["operations"][0]["stage"], "decision_recorded")
                self.assertEqual(state["operations"][0]["reviewed_by"], "ReviewerA")
                self.assertEqual(len(state["decisions"]), 1)
                self.assertEqual(state["decisions"][0]["reviewed_by"], "ReviewerA")
                self.assertFalse(state["records"])

    def test_decision_write_failure_leaves_operation_only_and_retries(self):
        with tempfile.TemporaryDirectory() as tempdir:
            with ExitStack() as stack:
                for manager in self.isolated_memory_store(tempdir):
                    stack.enter_context(manager)

                review_id = self.create_review()
                stack.enter_context(
                    patch.object(
                        app.memory_review_queue,
                        "_save_decisions",
                        side_effect=RuntimeError("/tmp/secret approval failure"),
                    )
                )
                response = self.client.post(
                    f"/memory/review/{review_id}/approve",
                    json={"reviewed_by": "Oracle", "notes": "decision fail"},
                )

            with ExitStack() as stack:
                for manager in self.isolated_memory_store(tempdir):
                    stack.enter_context(manager)
                state = self.snapshot(tempdir)
                self.assertEqual(state["queue"][0]["review_status"], "pending")
                self.assertEqual(state["operations"][0]["stage"], "operation_started")
                self.assertFalse(state["decisions"])
                self.assertFalse(state["records"])
                self.assert_forward_failure_then_retry(tempdir, review_id, response)

    def test_memory_persistence_failure_leaves_decision_only_and_retries_without_duplicate_decision(self):
        with tempfile.TemporaryDirectory() as tempdir:
            with ExitStack() as stack:
                for manager in self.isolated_memory_store(tempdir):
                    stack.enter_context(manager)

                review_id = self.create_review()
                stack.enter_context(
                    patch.object(
                        app.memory_review_queue,
                        "_save_memory_records",
                        side_effect=RuntimeError("/tmp/secret approval failure"),
                    )
                )
                response = self.client.post(
                    f"/memory/review/{review_id}/approve",
                    json={"reviewed_by": "Oracle", "notes": "memory fail"},
                )

            with ExitStack() as stack:
                for manager in self.isolated_memory_store(tempdir):
                    stack.enter_context(manager)
                ids = self.expected_approval_ids(review_id)
                state = self.snapshot(tempdir)
                self.assertEqual(state["queue"][0]["review_status"], "pending")
                self.assertEqual([decision["decision_id"] for decision in state["decisions"]], [ids["decision_id"]])
                self.assertFalse(state["records"])
                self.assert_forward_failure_then_retry(tempdir, review_id, response)

    def test_stage_persistence_failure_reconciles_actual_decision_state_on_retry(self):
        with tempfile.TemporaryDirectory() as tempdir:
            with ExitStack() as stack:
                for manager in self.isolated_memory_store(tempdir):
                    stack.enter_context(manager)

                review_id = self.create_review()
                original = app.memory_review_queue._save_approval_operations
                call_count = {"count": 0}

                def fail_second_stage_write(rows):
                    call_count["count"] += 1
                    if call_count["count"] == 2:
                        raise RuntimeError("/tmp/secret approval failure")
                    return original(rows)

                stack.enter_context(
                    patch.object(
                        app.memory_review_queue,
                        "_save_approval_operations",
                        side_effect=fail_second_stage_write,
                    )
                )
                response = self.client.post(
                    f"/memory/review/{review_id}/approve",
                    json={"reviewed_by": "Oracle", "notes": "stage fail"},
                )

            with ExitStack() as stack:
                for manager in self.isolated_memory_store(tempdir):
                    stack.enter_context(manager)
                ids = self.expected_approval_ids(review_id)
                state = self.snapshot(tempdir)
                self.assertEqual(state["operations"][0]["stage"], "operation_started")
                self.assertEqual([decision["decision_id"] for decision in state["decisions"]], [ids["decision_id"]])
                self.assertFalse(state["records"])
                self.assert_forward_failure_then_retry(tempdir, review_id, response)

    def test_review_state_failure_leaves_memory_and_decision_recoverable(self):
        with tempfile.TemporaryDirectory() as tempdir:
            with ExitStack() as stack:
                for manager in self.isolated_memory_store(tempdir):
                    stack.enter_context(manager)

                review_id = self.create_review()
                stack.enter_context(
                    patch.object(
                        app.memory_review_queue,
                        "update_review_item",
                        side_effect=RuntimeError("/tmp/secret approval failure"),
                    )
                )
                response = self.client.post(
                    f"/memory/review/{review_id}/approve",
                    json={"reviewed_by": "Oracle", "notes": "queue fail"},
                )

            with ExitStack() as stack:
                for manager in self.isolated_memory_store(tempdir):
                    stack.enter_context(manager)
                ids = self.expected_approval_ids(review_id)
                state = self.snapshot(tempdir)
                self.assertEqual(state["queue"][0]["review_status"], "pending")
                self.assertEqual([record["record_id"] for record in state["records"]], [ids["record_id"]])
                self.assertEqual(state["records"][0]["status"], "draft")
                self.assertEqual(state["records"][0]["review_state"], "needs_review")
                self.assertEqual([decision["decision_id"] for decision in state["decisions"]], [ids["decision_id"]])
                self.assert_draft_memory_hidden(tempdir, review_id)
                self.assert_forward_failure_then_retry(tempdir, review_id, response)

    def test_active_promotion_failure_leaves_draft_until_retry_promotes_same_memory(self):
        with tempfile.TemporaryDirectory() as tempdir:
            with ExitStack() as stack:
                for manager in self.isolated_memory_store(tempdir):
                    stack.enter_context(manager)

                review_id = self.create_review()
                original = app.memory_review_queue._save_memory_records
                call_count = {"count": 0}

                def fail_second_memory_save(rows):
                    call_count["count"] += 1
                    if call_count["count"] == 2:
                        raise RuntimeError("/tmp/secret approval failure")
                    return original(rows)

                stack.enter_context(
                    patch.object(
                        app.memory_review_queue,
                        "_save_memory_records",
                        side_effect=fail_second_memory_save,
                    )
                )
                response = self.client.post(
                    f"/memory/review/{review_id}/approve",
                    json={"reviewed_by": "Oracle", "notes": "promotion fail"},
                )

            with ExitStack() as stack:
                for manager in self.isolated_memory_store(tempdir):
                    stack.enter_context(manager)
                state = self.snapshot(tempdir)
                self.assertEqual(state["queue"][0]["review_status"], "approved")
                self.assertEqual(len(state["decisions"]), 1)
                self.assert_draft_memory_hidden(tempdir, review_id)
                self.assert_forward_failure_then_retry(tempdir, review_id, response)

    def test_index_failure_rebuilds_on_retry_without_duplicate_memory_or_decision(self):
        with tempfile.TemporaryDirectory() as tempdir:
            with ExitStack() as stack:
                for manager in self.isolated_memory_store(tempdir):
                    stack.enter_context(manager)

                review_id = self.create_review()
                stack.enter_context(
                    patch.object(
                        app.memory_taxonomy,
                        "rebuild_index",
                        side_effect=RuntimeError("/tmp/secret approval failure"),
                    )
                )
                response = self.client.post(
                    f"/memory/review/{review_id}/approve",
                    json={"reviewed_by": "Oracle", "notes": "index fail"},
                )

            with ExitStack() as stack:
                for manager in self.isolated_memory_store(tempdir):
                    stack.enter_context(manager)
                state = self.snapshot(tempdir)
                self.assertEqual(state["queue"][0]["review_status"], "approved")
                self.assertEqual(len(state["records"]), 1)
                self.assertEqual(len(state["decisions"]), 1)
                self.assert_forward_failure_then_retry(tempdir, review_id, response)

    def test_completion_marker_failure_recovers_before_completed_state_409(self):
        with tempfile.TemporaryDirectory() as tempdir:
            with ExitStack() as stack:
                for manager in self.isolated_memory_store(tempdir):
                    stack.enter_context(manager)

                review_id = self.create_review()
                original = app.memory_review_queue._mark_approval_operation

                def fail_complete(operation, stage, status="incomplete", error=""):
                    if stage == "complete":
                        raise RuntimeError("/tmp/secret approval failure")
                    return original(operation, stage, status=status, error=error)

                stack.enter_context(
                    patch.object(app.memory_review_queue, "_mark_approval_operation", side_effect=fail_complete)
                )
                response = self.client.post(
                    f"/memory/review/{review_id}/approve",
                    json={"reviewed_by": "Oracle", "notes": "completion fail"},
                )

            with ExitStack() as stack:
                for manager in self.isolated_memory_store(tempdir):
                    stack.enter_context(manager)
                state = self.snapshot(tempdir)
                self.assertEqual(state["queue"][0]["review_status"], "approved")
                self.assertEqual(state["operations"][0]["stage"], "memory_indexed")
                self.assert_forward_failure_then_retry(tempdir, review_id, response)

    def test_different_reviewer_recovery_preserves_initial_approval_attribution(self):
        def decision_write_failure(stack):
            stack.enter_context(
                patch.object(
                    app.memory_review_queue,
                    "_save_decisions",
                    side_effect=RuntimeError("/tmp/secret approval failure"),
                )
            )

        def decision_stage_failure(stack):
            original = app.memory_review_queue._save_approval_operations
            call_count = {"count": 0}

            def fail_second_stage_write(rows):
                call_count["count"] += 1
                if call_count["count"] == 2:
                    raise RuntimeError("/tmp/secret approval failure")
                return original(rows)

            stack.enter_context(
                patch.object(
                    app.memory_review_queue,
                    "_save_approval_operations",
                    side_effect=fail_second_stage_write,
                )
            )

        def draft_memory_failure(stack):
            stack.enter_context(
                patch.object(
                    app.memory_review_queue,
                    "_save_memory_records",
                    side_effect=RuntimeError("/tmp/secret approval failure"),
                )
            )

        def review_approval_failure(stack):
            stack.enter_context(
                patch.object(
                    app.memory_review_queue,
                    "update_review_item",
                    side_effect=RuntimeError("/tmp/secret approval failure"),
                )
            )

        def active_promotion_failure(stack):
            original = app.memory_review_queue._save_memory_records
            call_count = {"count": 0}

            def fail_second_memory_save(rows):
                call_count["count"] += 1
                if call_count["count"] == 2:
                    raise RuntimeError("/tmp/secret approval failure")
                return original(rows)

            stack.enter_context(
                patch.object(
                    app.memory_review_queue,
                    "_save_memory_records",
                    side_effect=fail_second_memory_save,
                )
            )

        def index_failure(stack):
            stack.enter_context(
                patch.object(
                    app.memory_taxonomy,
                    "rebuild_index",
                    side_effect=RuntimeError("/tmp/secret approval failure"),
                )
            )

        def completion_marker_failure(stack):
            original = app.memory_review_queue._mark_approval_operation

            def fail_complete(operation, stage, status="incomplete", error=""):
                if stage == "complete":
                    raise RuntimeError("/tmp/secret approval failure")
                return original(operation, stage, status=status, error=error)

            stack.enter_context(
                patch.object(app.memory_review_queue, "_mark_approval_operation", side_effect=fail_complete)
            )

        cases = [
            ("after_operation_creation", decision_write_failure, "operation_started"),
            ("after_decision_write", decision_stage_failure, "operation_started"),
            ("after_decision_stage", draft_memory_failure, "decision_recorded"),
            ("after_draft_creation", review_approval_failure, "memory_draft"),
            ("after_review_approval", active_promotion_failure, "review_approved"),
            ("after_active_promotion", index_failure, "memory_active"),
            ("after_index_rebuild", completion_marker_failure, "memory_indexed"),
        ]

        for name, install_failure, expected_stage in cases:
            with self.subTest(name=name):
                with tempfile.TemporaryDirectory() as tempdir:
                    with ExitStack() as stack:
                        for manager in self.isolated_memory_store(tempdir):
                            stack.enter_context(manager)

                        review_id = self.create_review()
                        install_failure(stack)
                        response = self.client.post(
                            f"/memory/review/{review_id}/approve",
                            json={"reviewed_by": "ReviewerA", "notes": f"{name} failure"},
                        )

                    self.assertEqual(response.status_code, 500)
                    self.assertNotIn("/tmp/secret approval failure", response.text)

                    with ExitStack() as stack:
                        for manager in self.isolated_memory_store(tempdir):
                            stack.enter_context(manager)
                        before = self.snapshot(tempdir)
                        self.assertEqual(before["operations"][0]["reviewed_by"], "ReviewerA")
                        self.assertEqual(before["operations"][0]["stage"], expected_stage)
                        if before["decisions"]:
                            self.assertEqual(before["decisions"][0]["reviewed_by"], "ReviewerA")
                        if before["records"]:
                            self.assertEqual(before["records"][0]["created_by"], "ReviewerA")

                        self.assert_retry_completes_once(
                            tempdir,
                            review_id,
                            retry_reviewer="ReviewerB",
                            expected_reviewer="ReviewerA",
                        )

    def test_reviewer_attribution_conflicts_stop_without_mutation(self):
        cases = [
            ("operation_decision_reviewer_mismatch", {}, {"reviewed_by": "ReviewerB"}, None),
            ("operation_memory_creator_mismatch", {}, None, {"created_by": "ReviewerB"}),
            (
                "mixed_decision_memory_reviewer_mismatch",
                {},
                {"reviewed_by": "ReviewerB"},
                {"created_by": "ReviewerB"},
            ),
            ("missing_operation_reviewer", {"reviewed_by": None}, None, None),
            ("empty_operation_reviewer", {"reviewed_by": ""}, None, None),
            ("missing_decision_reviewer", {}, {"reviewed_by": None}, None),
            ("missing_memory_created_by", {}, None, {"created_by": None}),
        ]

        for name, operation_overrides, decision_overrides, memory_overrides in cases:
            with self.subTest(name=name):
                with tempfile.TemporaryDirectory() as tempdir:
                    with ExitStack() as stack:
                        for manager in self.isolated_memory_store(tempdir):
                            stack.enter_context(manager)

                        review_id = self.create_review()
                        item = app.memory_review_queue.load_queue(include_closed=True)[0]
                        operation_fixture = {"reviewed_by": "ReviewerA"}
                        operation_fixture.update(operation_overrides)
                        operation = self.approval_operation(
                            review_id,
                            item,
                            **operation_fixture,
                        )
                        self.write_jsonl(app.memory_review_queue.APPROVAL_OPERATIONS_PATH, [operation])
                        ids = self.expected_approval_ids(review_id)
                        if decision_overrides is not None:
                            decision_fixture = {"reviewed_by": "ReviewerA"}
                            decision_fixture.update(decision_overrides)
                            decision = self.approval_decision(
                                review_id,
                                ids,
                                **decision_fixture,
                            )
                            self.write_jsonl(app.memory_review_queue.REVIEW_DECISIONS_PATH, [decision])
                        if memory_overrides is not None:
                            memory_fixture = {"created_by": "ReviewerA"}
                            memory_fixture.update(memory_overrides)
                            memory = self.approval_memory(
                                operation,
                                item,
                                **memory_fixture,
                            )
                            self.write_jsonl(app.memory_taxonomy.MEMORY_RECORDS_PATH, [memory])

                        before = self.durable_snapshot(tempdir)
                        self.assert_approval_conflict_no_mutation(tempdir, review_id, before)

    def test_different_reviewer_initial_approval_concurrency_uses_one_authoritative_approver(self):
        import concurrent.futures

        with tempfile.TemporaryDirectory() as tempdir:
            with ExitStack() as stack:
                for manager in self.isolated_memory_store(tempdir):
                    stack.enter_context(manager)

                review_id = self.create_review()

                def approve(reviewer):
                    return self.client.post(
                        f"/memory/review/{review_id}/approve",
                        json={"reviewed_by": reviewer, "notes": f"concurrent {reviewer}"},
                    )

                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                    responses = list(executor.map(approve, ["ReviewerA", "ReviewerB"]))

                statuses = sorted(response.status_code for response in responses)
                self.assertIn(statuses, ([200, 200], [200, 409]))
                state = self.snapshot(tempdir)
                self.assertEqual(len(state["operations"]), 1)
                self.assertEqual(len(state["decisions"]), 1)
                self.assertEqual(len(state["records"]), 1)
                effective_reviewer = state["operations"][0]["reviewed_by"]
                self.assertIn(effective_reviewer, {"ReviewerA", "ReviewerB"})
                self.assertEqual(state["queue"][0]["reviewed_by"], effective_reviewer)
                self.assertEqual(state["decisions"][0]["reviewed_by"], effective_reviewer)
                self.assertEqual(state["records"][0]["created_by"], effective_reviewer)
                self.assert_completed_once(
                    tempdir,
                    review_id,
                    expected_reviewer=effective_reviewer,
                    repeat_reviewer="ReviewerB",
                )

    def test_different_reviewer_concurrent_recovery_preserves_initial_approver(self):
        import concurrent.futures

        with tempfile.TemporaryDirectory() as tempdir:
            with ExitStack() as stack:
                for manager in self.isolated_memory_store(tempdir):
                    stack.enter_context(manager)

                review_id = self.create_review()
                stack.enter_context(
                    patch.object(
                        app.memory_review_queue,
                        "_save_memory_records",
                        side_effect=RuntimeError("/tmp/secret approval failure"),
                    )
                )
                response = self.client.post(
                    f"/memory/review/{review_id}/approve",
                    json={"reviewed_by": "ReviewerA", "notes": "fail before draft"},
                )

            self.assertEqual(response.status_code, 500)
            with ExitStack() as stack:
                for manager in self.isolated_memory_store(tempdir):
                    stack.enter_context(manager)

                def approve(reviewer):
                    return self.client.post(
                        f"/memory/review/{review_id}/approve",
                        json={"reviewed_by": reviewer, "notes": f"recovery {reviewer}"},
                    )

                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                    responses = list(executor.map(approve, ["ReviewerB", "ReviewerC"]))

                statuses = sorted(response.status_code for response in responses)
                self.assertIn(statuses, ([200, 200], [200, 409]))
                self.assert_completed_once(
                    tempdir,
                    review_id,
                    expected_reviewer="ReviewerA",
                    repeat_reviewer="ReviewerC",
                )

    def test_different_reviewer_recovery_racing_with_other_actions_keeps_approval_consistent(self):
        import concurrent.futures

        def alternate_request(action, review_id):
            if action == "edit":
                return self.client.post(
                    f"/memory/review/{review_id}/edit",
                    json={
                        "patch": {"title": "Edited during approval recovery"},
                        "reviewed_by": "ReviewerB",
                        "notes": "edit race",
                    },
                )
            return self.client.post(
                f"/memory/review/{review_id}/{action}",
                json={"reviewed_by": "ReviewerB", "notes": f"{action} race"},
            )

        for action in ("reject", "defer", "edit"):
            with self.subTest(action=action):
                with tempfile.TemporaryDirectory() as tempdir:
                    with ExitStack() as stack:
                        for manager in self.isolated_memory_store(tempdir):
                            stack.enter_context(manager)

                        review_id = self.create_review()
                        stack.enter_context(
                            patch.object(
                                app.memory_review_queue,
                                "_save_memory_records",
                                side_effect=RuntimeError("/tmp/secret approval failure"),
                            )
                        )
                        response = self.client.post(
                            f"/memory/review/{review_id}/approve",
                            json={"reviewed_by": "ReviewerA", "notes": "fail before draft"},
                        )

                    self.assertEqual(response.status_code, 500)
                    with ExitStack() as stack:
                        for manager in self.isolated_memory_store(tempdir):
                            stack.enter_context(manager)

                        def approve():
                            return self.client.post(
                                f"/memory/review/{review_id}/approve",
                                json={"reviewed_by": "ReviewerB", "notes": "recover"},
                            )

                        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                            approve_response, alternate_response = list(
                                executor.map(lambda call: call(), [approve, lambda: alternate_request(action, review_id)])
                            )

                        self.assertEqual(approve_response.status_code, 200)
                        self.assertEqual(alternate_response.status_code, 409)
                        self.assertEqual(alternate_response.json()["detail"], "invalid_review_transition")
                        self.assert_completed_once(
                            tempdir,
                            review_id,
                            expected_reviewer="ReviewerA",
                            repeat_reviewer="ReviewerB",
                        )

    def test_approval_operation_provenance_conflicts_stop_without_mutation(self):
        cases = [
            (
                "review_id_mismatch",
                {"review_id": "rev_other"},
            ),
            (
                "candidate_identity_mismatch",
                {"candidate_identity": app.memory_review_queue._candidate_identity({"other": "candidate"})},
            ),
            (
                "intended_memory_id_mismatch",
                {"intended_memory_record_id": "mem_rev_other_approved"},
            ),
            (
                "intended_decision_id_mismatch",
                {"intended_decision_id": "rd_rev_other_approved"},
            ),
            (
                "unknown_stage",
                {"stage": "unknown_stage"},
            ),
            (
                "contradictory_stage_status",
                {"stage": "complete", "status": "incomplete"},
            ),
            (
                "complete_missing_effects",
                {"stage": "complete", "status": "complete", "completed_at": app.memory_review_queue.utc_now()},
            ),
        ]

        for name, overrides in cases:
            with self.subTest(name=name):
                with tempfile.TemporaryDirectory() as tempdir:
                    with ExitStack() as stack:
                        for manager in self.isolated_memory_store(tempdir):
                            stack.enter_context(manager)

                        review_id, item, operation = self.approved_review_with_incomplete_operation()
                        operation.update(overrides)
                        self.write_jsonl(app.memory_review_queue.APPROVAL_OPERATIONS_PATH, [operation])
                        before = self.durable_snapshot(tempdir)
                        self.assert_approval_conflict_no_mutation(tempdir, review_id, before)

    def test_existing_approval_decision_conflicts_stop_without_mutation(self):
        cases = [
            ("wrong_review_id", {"review_id": "rev_other"}),
            ("wrong_action", {"decision": "rejected"}),
            ("wrong_record_id", {"record_id": "mem_rev_other_approved"}),
            ("wrong_operation_id", {"operation_id": "approval_rev_other"}),
            ("wrong_queue_version", {"queue_version": "other_version"}),
        ]

        for name, overrides in cases:
            with self.subTest(name=name):
                with tempfile.TemporaryDirectory() as tempdir:
                    with ExitStack() as stack:
                        for manager in self.isolated_memory_store(tempdir):
                            stack.enter_context(manager)

                        review_id, item, operation = self.approved_review_with_incomplete_operation()
                        ids = self.expected_approval_ids(review_id)
                        decision = self.approval_decision(review_id, ids, **overrides)
                        self.write_jsonl(app.memory_review_queue.REVIEW_DECISIONS_PATH, [decision])
                        before = self.durable_snapshot(tempdir)
                        self.assert_approval_conflict_no_mutation(tempdir, review_id, before)

    def test_existing_approval_memory_conflicts_stop_without_mutation(self):
        cases = [
            ("wrong_source_ref", {"source_ref": "audit:other"}),
            ("wrong_provenance", {"provenance": "Unrelated provenance."}),
            ("wrong_title", {"title": "UNRELATED CONFLICTING MEMORY CONTENT"}),
            ("wrong_body", {"body": "Unrelated body."}),
            ("wrong_record_type", {"record_type": "thread_memory"}),
            ("revoked_status", {"status": "revoked", "review_state": "oracle_approved"}),
            ("superseded_status", {"status": "superseded", "review_state": "oracle_approved"}),
            ("expired_status", {"status": "expired", "review_state": "oracle_approved"}),
            ("draft_wrong_review_state", {"status": "draft", "review_state": "oracle_approved"}),
        ]

        for name, overrides in cases:
            with self.subTest(name=name):
                with tempfile.TemporaryDirectory() as tempdir:
                    with ExitStack() as stack:
                        for manager in self.isolated_memory_store(tempdir):
                            stack.enter_context(manager)

                        review_id, item, operation = self.approved_review_with_incomplete_operation()
                        memory = self.approval_memory(operation, item, **overrides)
                        self.write_jsonl(app.memory_taxonomy.MEMORY_RECORDS_PATH, [memory])
                        before = self.durable_snapshot(tempdir)
                        self.assert_approval_conflict_no_mutation(tempdir, review_id, before)

    def test_combined_approval_conflicts_stop_without_mutation(self):
        cases = [
            "approved_operation_review_id_conflict",
            "pending_conflicting_decision_with_matching_draft",
            "pending_matching_decision_with_conflicting_memory",
            "approved_conflicting_decision_and_memory",
            "operation_candidate_conflict_with_valid_effects",
            "operation_intended_ids_conflict_with_objects_at_deterministic_ids",
        ]

        for name in cases:
            with self.subTest(name=name):
                with tempfile.TemporaryDirectory() as tempdir:
                    with ExitStack() as stack:
                        for manager in self.isolated_memory_store(tempdir):
                            stack.enter_context(manager)

                        if name.startswith("pending"):
                            review_id = self.create_review()
                            item = app.memory_review_queue.load_queue(include_closed=True)[0]
                            ids = self.expected_approval_ids(review_id)
                            operation = self.approval_operation(review_id, item)
                            self.write_jsonl(app.memory_review_queue.APPROVAL_OPERATIONS_PATH, [operation])
                        else:
                            review_id, item, operation = self.approved_review_with_incomplete_operation()
                            ids = self.expected_approval_ids(review_id)

                        if name == "approved_operation_review_id_conflict":
                            operation["review_id"] = "rev_other"
                            self.write_jsonl(app.memory_review_queue.APPROVAL_OPERATIONS_PATH, [operation])
                        elif name == "pending_conflicting_decision_with_matching_draft":
                            self.write_jsonl(app.memory_review_queue.REVIEW_DECISIONS_PATH, [
                                self.approval_decision(review_id, ids, decision="rejected")
                            ])
                            self.write_jsonl(app.memory_taxonomy.MEMORY_RECORDS_PATH, [
                                self.approval_memory(operation, item, status="draft", review_state="needs_review")
                            ])
                        elif name == "pending_matching_decision_with_conflicting_memory":
                            self.write_jsonl(app.memory_review_queue.REVIEW_DECISIONS_PATH, [
                                self.approval_decision(review_id, ids)
                            ])
                            self.write_jsonl(app.memory_taxonomy.MEMORY_RECORDS_PATH, [
                                self.approval_memory(operation, item, title="UNRELATED CONFLICTING MEMORY CONTENT")
                            ])
                        elif name == "approved_conflicting_decision_and_memory":
                            self.write_jsonl(app.memory_review_queue.REVIEW_DECISIONS_PATH, [
                                self.approval_decision(review_id, ids, decision="rejected")
                            ])
                            self.write_jsonl(app.memory_taxonomy.MEMORY_RECORDS_PATH, [
                                self.approval_memory(operation, item, source_ref="audit:other")
                            ])
                        elif name == "operation_candidate_conflict_with_valid_effects":
                            operation["candidate_identity"] = app.memory_review_queue._candidate_identity({"other": "candidate"})
                            self.write_jsonl(app.memory_review_queue.APPROVAL_OPERATIONS_PATH, [operation])
                            self.write_jsonl(app.memory_review_queue.REVIEW_DECISIONS_PATH, [
                                self.approval_decision(review_id, ids)
                            ])
                            self.write_jsonl(app.memory_taxonomy.MEMORY_RECORDS_PATH, [
                                self.approval_memory(operation, item)
                            ])
                        elif name == "operation_intended_ids_conflict_with_objects_at_deterministic_ids":
                            operation["intended_memory_record_id"] = "mem_rev_other_approved"
                            operation["intended_decision_id"] = "rd_rev_other_approved"
                            self.write_jsonl(app.memory_review_queue.APPROVAL_OPERATIONS_PATH, [operation])
                            matching_operation = self.approval_operation(review_id, item)
                            self.write_jsonl(app.memory_review_queue.REVIEW_DECISIONS_PATH, [
                                self.approval_decision(review_id, ids)
                            ])
                            self.write_jsonl(app.memory_taxonomy.MEMORY_RECORDS_PATH, [
                                self.approval_memory(matching_operation, item)
                            ])

                        before = self.durable_snapshot(tempdir)
                        self.assert_approval_conflict_no_mutation(tempdir, review_id, before)

    def test_stale_approval_operation_after_candidate_edit_stops_without_mutation(self):
        with tempfile.TemporaryDirectory() as tempdir:
            with ExitStack() as stack:
                for manager in self.isolated_memory_store(tempdir):
                    stack.enter_context(manager)

                review_id = self.create_review()
                item = app.memory_review_queue.load_queue(include_closed=True)[0]
                operation = self.approval_operation(review_id, item)
                self.write_jsonl(app.memory_review_queue.APPROVAL_OPERATIONS_PATH, [operation])
                before_edit = self.durable_snapshot(tempdir)

                edit = self.client.post(
                    f"/memory/review/{review_id}/edit",
                    json={
                        "patch": {"title": "Edited memory probe"},
                        "reviewed_by": "Oracle",
                        "notes": "candidate changed after operation",
                    },
                )
                self.assertEqual(edit.status_code, 409)
                self.assertEqual(edit.json()["detail"], "invalid_review_transition")
                self.assert_no_durable_change(tempdir, before_edit)

                queue = app.memory_review_queue.load_queue(include_closed=True)
                queue[0]["candidate_record"]["title"] = "Edited memory probe"
                queue[0]["diff"] = app.memory_review_queue.build_diff(
                    queue[0].get("original_record", {}),
                    queue[0]["candidate_record"],
                )
                app.memory_review_queue.save_queue(queue)
                before = self.durable_snapshot(tempdir)
                self.assert_approval_conflict_no_mutation(tempdir, review_id, before)

    def test_arbitrary_approved_review_without_operation_remains_closed(self):
        with tempfile.TemporaryDirectory() as tempdir:
            with ExitStack() as stack:
                for manager in self.isolated_memory_store(tempdir):
                    stack.enter_context(manager)

                review_id = self.create_review()
                queue = app.memory_review_queue.load_queue(include_closed=True)
                queue[0]["review_status"] = "approved"
                queue[0]["reviewed_at"] = app.memory_review_queue.utc_now()
                queue[0]["reviewed_by"] = "Oracle"
                queue[0]["notes"] = "closed without operation evidence"
                app.memory_review_queue.save_queue(queue)
                before = self.durable_snapshot(tempdir)
                response = self.approval_conflict_response(review_id)

            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json()["detail"], "invalid_review_transition")
            self.assert_no_durable_change(tempdir, before)

    def test_literal_approved_review_with_matching_operation_recovers_through_approval_endpoint(self):
        with tempfile.TemporaryDirectory() as tempdir:
            with ExitStack() as stack:
                for manager in self.isolated_memory_store(tempdir):
                    stack.enter_context(manager)

                review_id = self.create_review()
                queue = app.memory_review_queue.load_queue(include_closed=True)
                queue[0]["review_status"] = "approved"
                queue[0]["reviewed_at"] = app.memory_review_queue.utc_now()
                queue[0]["reviewed_by"] = "Oracle"
                queue[0]["notes"] = "legacy incomplete approval"
                app.memory_review_queue.save_queue(queue)
                operation = self.approval_operation(review_id, queue[0])
                self.write_jsonl(app.memory_review_queue.APPROVAL_OPERATIONS_PATH, [operation])
                self.assertFalse(self.read_jsonl(Path(tempdir) / "memory" / "review_decisions.jsonl"))
                self.assertFalse((Path(tempdir) / "memory" / "memory_records.jsonl").exists())

                response = self.client.post(
                    f"/memory/review/{review_id}/approve",
                    json={"reviewed_by": "Oracle", "notes": "recover literal"},
                )

            self.assertEqual(response.status_code, 200)
            with ExitStack() as stack:
                for manager in self.isolated_memory_store(tempdir):
                    stack.enter_context(manager)
                self.assert_completed_once(tempdir, review_id)

    def test_literal_pending_review_with_decision_and_active_memory_recovers_without_duplicates(self):
        with tempfile.TemporaryDirectory() as tempdir:
            with ExitStack() as stack:
                for manager in self.isolated_memory_store(tempdir):
                    stack.enter_context(manager)

                review_id = self.create_review()
                ids = self.expected_approval_ids(review_id)
                queue = app.memory_review_queue.load_queue(include_closed=True)
                item = queue[0]
                operation = app.memory_review_queue._ensure_approval_operation(
                    review_id,
                    item,
                    reviewed_by="Oracle",
                    notes="literal contradiction",
                )
                operation = app.memory_review_queue._mark_approval_operation(operation, "memory_draft")
                decision = {
                    "decision_id": ids["decision_id"],
                    "review_id": review_id,
                    "decision": "approved",
                    "reviewed_by": "Oracle",
                    "reviewed_at": app.memory_review_queue.utc_now(),
                    "notes": "literal contradiction",
                    "record_id": ids["record_id"],
                    "queue_version": app.memory_review_queue.REVIEW_QUEUE_VERSION,
                    "policy_version": app.memory_review_queue.POLICY_VERSION,
                    "operation_id": ids["operation_id"],
                }
                self.write_jsonl(Path(tempdir) / "memory" / "review_decisions.jsonl", [decision])
                memory = app.memory_review_queue._approval_memory_payload(operation, item, "Oracle")
                memory["status"] = "active"
                memory["review_state"] = "oracle_approved"
                memory["hash"] = app.memory_review_queue._memory_hash(memory)
                self.write_jsonl(Path(tempdir) / "memory" / "memory_records.jsonl", [memory])
                app.memory_taxonomy.rebuild_index()

                before_search = self.client.post(
                    "/memory/search",
                    json={"query": "memory governance lifecycle probe", "include_revoked": False},
                )
                self.assertEqual(
                    [result["record_id"] for result in before_search.json()["results"]],
                    [ids["record_id"]],
                )

                response = self.client.post(
                    f"/memory/review/{review_id}/approve",
                    json={"reviewed_by": "Oracle", "notes": "recover literal contradiction"},
                )

            self.assertEqual(response.status_code, 200)
            with ExitStack() as stack:
                for manager in self.isolated_memory_store(tempdir):
                    stack.enter_context(manager)
                self.assert_completed_once(tempdir, review_id)

    def test_concurrent_recovery_of_literal_contradiction_does_not_duplicate_effects(self):
        import concurrent.futures

        with tempfile.TemporaryDirectory() as tempdir:
            with ExitStack() as stack:
                for manager in self.isolated_memory_store(tempdir):
                    stack.enter_context(manager)

                review_id = self.create_review()
                ids = self.expected_approval_ids(review_id)
                item = app.memory_review_queue.load_queue(include_closed=True)[0]
                operation = app.memory_review_queue._ensure_approval_operation(
                    review_id,
                    item,
                    reviewed_by="Oracle",
                    notes="literal contradiction",
                )
                app.memory_review_queue._mark_approval_operation(operation, "memory_draft")
                self.write_jsonl(Path(tempdir) / "memory" / "review_decisions.jsonl", [{
                    "decision_id": ids["decision_id"],
                    "review_id": review_id,
                    "decision": "approved",
                    "reviewed_by": "Oracle",
                    "reviewed_at": app.memory_review_queue.utc_now(),
                    "notes": "literal contradiction",
                    "record_id": ids["record_id"],
                    "queue_version": app.memory_review_queue.REVIEW_QUEUE_VERSION,
                    "policy_version": app.memory_review_queue.POLICY_VERSION,
                    "operation_id": ids["operation_id"],
                }])
                memory = app.memory_review_queue._approval_memory_payload(operation, item, "Oracle")
                memory["status"] = "active"
                memory["review_state"] = "oracle_approved"
                memory["hash"] = app.memory_review_queue._memory_hash(memory)
                self.write_jsonl(Path(tempdir) / "memory" / "memory_records.jsonl", [memory])
                app.memory_taxonomy.rebuild_index()

                def approve():
                    return self.client.post(
                        f"/memory/review/{review_id}/approve",
                        json={"reviewed_by": "Oracle", "notes": "concurrent recovery"},
                    )

                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                    responses = list(executor.map(lambda _: approve(), range(2)))

                statuses = sorted(response.status_code for response in responses)
                self.assertIn(statuses, ([200, 200], [200, 409]))
                self.assert_completed_once(tempdir, review_id)

    def test_concurrent_same_review_approval_does_not_duplicate_effects(self):
        import concurrent.futures

        with tempfile.TemporaryDirectory() as tempdir:
            with ExitStack() as stack:
                for manager in self.isolated_memory_store(tempdir):
                    stack.enter_context(manager)

                review_id = self.create_review()

                def approve():
                    return self.client.post(
                        f"/memory/review/{review_id}/approve",
                        json={"reviewed_by": "Oracle", "notes": "concurrent"},
                    )

                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                    responses = list(executor.map(lambda _: approve(), range(2)))

                statuses = sorted(response.status_code for response in responses)
                self.assertIn(statuses, ([200, 200], [200, 409]))
                state = self.snapshot(tempdir)
                self.assertEqual(len(state["records"]), 1)
                self.assertEqual(len(state["decisions"]), 1)
                self.assertEqual(len(state["operations"]), 1)
                self.assertEqual(state["queue"][0]["review_status"], "approved")
                self.assertEqual(self.approval_index_count(tempdir), 1)

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
