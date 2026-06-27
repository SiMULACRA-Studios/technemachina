import json
import inspect
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[1]
DAEMON_ROOT = REPO_ROOT / "daemon"

if str(DAEMON_ROOT) not in sys.path:
    sys.path.insert(0, str(DAEMON_ROOT))

import app


class KnowledgeIngestCandidateBridgeTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(
            app.app,
            base_url="http://localhost",
            raise_server_exceptions=False,
        )

    def isolated_stores(self, tempdir: str):
        root = Path(tempdir)
        knowledge_dir = root / "knowledge"
        memory_dir = root / "memory"

        paths = {
            "knowledge_dir": knowledge_dir,
            "records": knowledge_dir / "knowledge_records.jsonl",
            "sources": knowledge_dir / "knowledge_sources.json",
            "candidates": knowledge_dir / "knowledge_candidates.jsonl",
            "operations": knowledge_dir / "knowledge_operations.json",
            "memory_dir": memory_dir,
            "review_queue": memory_dir / "review_queue.jsonl",
            "review_decisions": memory_dir / "review_decisions.jsonl",
            "approval_operations": memory_dir / "approval_operations.jsonl",
            "memory_records": memory_dir / "memory_records.jsonl",
            "memory_index": memory_dir / "memory_index.json",
            "entity_index": memory_dir / "entity_index.json",
        }

        patches = (
            patch.object(app.knowledge_ingest, "KNOWLEDGE_DIR", knowledge_dir),
            patch.object(app.knowledge_ingest, "RECORDS_PATH", paths["records"]),
            patch.object(app.knowledge_ingest, "SOURCES_PATH", paths["sources"]),
            patch.object(
                app.knowledge_ingest,
                "KNOWLEDGE_CANDIDATES_PATH",
                paths["candidates"],
            ),
            patch.object(
                app.knowledge_operations,
                "OPERATIONS_PATH",
                paths["operations"],
            ),
            patch.object(app.memory_review_queue, "MEMORY_DIR", memory_dir),
            patch.object(
                app.memory_review_queue,
                "REVIEW_QUEUE_PATH",
                paths["review_queue"],
            ),
            patch.object(
                app.memory_review_queue,
                "REVIEW_DECISIONS_PATH",
                paths["review_decisions"],
            ),
            patch.object(
                app.memory_review_queue,
                "APPROVAL_OPERATIONS_PATH",
                paths["approval_operations"],
            ),
            patch.object(app.memory_taxonomy, "MEMORY_DIR", memory_dir),
            patch.object(
                app.memory_taxonomy,
                "MEMORY_RECORDS_PATH",
                paths["memory_records"],
            ),
            patch.object(
                app.memory_taxonomy,
                "MEMORY_INDEX_PATH",
                paths["memory_index"],
            ),
            patch.object(app.memory_consolidation_worker, "MEMORY_DIR", memory_dir),
            patch.object(
                app.memory_consolidation_worker,
                "ENTITY_INDEX_PATH",
                paths["entity_index"],
            ),
        )

        return paths, patches

    def read_jsonl(self, path: Path):
        if not path.exists():
            return []

        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def read_operations(self, path: Path):
        if not path.exists():
            return []

        return json.loads(path.read_text(encoding="utf-8")).get("operations", [])

    def read_sources(self, path: Path):
        if not path.exists():
            return {"sources": {}}

        return json.loads(path.read_text(encoding="utf-8"))

    def post_text(self, title: str, body: str, source_path: str):
        return self.client.post(
            "/knowledge/ingest-text",
            json={
                "title": title,
                "body": body,
                "source_type": "text",
                "source_path": source_path,
                "origin": "manual",
                "tags": [],
                "created_by": "Test Oracle",
                "provenance": "Isolated knowledge-ingest regression fixture.",
            },
        )

    def assert_no_sensitive_operation_fields(self, payload):
        forbidden_keys = {
            "path",
            "source_path",
            "request_fingerprint",
            "content_hash",
            "canonical_inputs",
            "canonical_request_inputs",
            "intended_source_payload",
            "intended_record_payload",
            "intended_duplicate_event_payload",
        }

        def walk(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    self.assertNotIn(key, forbidden_keys)
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)
            elif isinstance(value, str):
                self.assertFalse(Path(value).is_absolute(), value)

        walk(payload)

    def assert_ingest_source_record_coherence(
        self,
        paths: dict[str, Path],
        *,
        expected_duplicate: bool,
        excluded_source_id: str | None = None,
        operation_index: int = -1,
    ):
        operation = self.read_operations(paths["operations"])[operation_index]
        registry = self.read_sources(paths["sources"])
        records = self.read_jsonl(paths["records"])
        source_id = operation["intended_identities"]["source_id"]
        source_payload = operation["intended_effect_payloads"]["source"]
        record_payload = operation["intended_effect_payloads"]["record"]
        durable_source = registry["sources"][source_id]
        durable_record = next(
            record
            for record in records
            if record["record_id"] == record_payload["record_id"]
        )

        self.assertEqual(source_id, source_payload["source_id"])
        self.assertEqual(source_id, record_payload["source_id"])
        self.assertEqual(source_id, durable_source["source_id"])
        self.assertEqual(source_id, durable_record["source_id"])
        if excluded_source_id is not None:
            self.assertNotEqual(durable_record["source_id"], excluded_source_id)
        if expected_duplicate:
            self.assertTrue(source_id.startswith("ksrc_dup_"))
            events = [
                event
                for event in registry.get("duplicate_events", [])
                if event["source_id"] == source_id
            ]
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["duplicate_of"], durable_source["duplicate_of"])
        else:
            self.assertFalse(source_id.startswith("ksrc_dup_"))
            self.assertIsNone(durable_source["duplicate_of"])
            self.assertEqual(durable_source["duplicate_reason"], "")
            self.assertEqual(record_payload["duplicate_reason"], "")
            self.assertEqual(record_payload["duplicate_of"], None)
            self.assertFalse(registry.get("duplicate_events", []))

        self.assertEqual(operation["state"], "complete")
        return operation, durable_source, durable_record

    def store_bytes(self, paths: dict[str, Path]):
        snapshot = {}

        for name, path in paths.items():
            if not path.exists():
                snapshot[name] = None
            elif path.is_dir():
                snapshot[name] = "<DIR>"
            else:
                snapshot[name] = path.read_bytes()

        return snapshot

    def assert_no_store_mutation(self, before: dict[str, bytes | None], paths: dict[str, Path]):
        self.assertEqual(self.store_bytes(paths), before)

    def ingest_eligible_record(self):
        response = self.client.post(
            "/knowledge/ingest-text",
            json={
                "title": "Governed candidate bridge",
                "body": (
                    "Architecture doctrine must preserve governance review "
                    "before durable memory writes."
                ),
                "source_type": "text",
                "source_path": "/tmp/governed-candidate.md",
                "origin": "manual",
                "tags": ["architecture", "governance"],
                "created_by": "Test Oracle",
                "provenance": "Isolated knowledge-ingest regression fixture.",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "success")
        return payload

    def test_ordinary_ingest_endpoint_still_succeeds(self):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tempdir:
            paths, patches = self.isolated_stores(tempdir)
            with ExitStack() as stack:
                for item in patches:
                    stack.enter_context(item)

                payload = self.ingest_eligible_record()

                self.assertEqual(len(self.read_jsonl(paths["records"])), 1)
                self.assertEqual(payload["record"]["lane"], "knowledge")
                self.assertFalse(payload["record"]["memory_write_allowed"])
                self.assertFalse(payload["record"]["candidate_path_allowed"])

    def assert_whitespace_body_rejected_without_mutation(self, body: str):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tempdir:
            paths, patches = self.isolated_stores(tempdir)
            with ExitStack() as stack:
                for item in patches:
                    stack.enter_context(item)

                before = self.store_bytes(paths)

                with (
                    patch.object(
                        app.knowledge_ingest,
                        "ingest_text",
                        side_effect=AssertionError("ingest_text must not be called"),
                    ) as ingest_mock,
                    patch.object(
                        app.knowledge_ingest,
                        "ensure_store",
                        side_effect=AssertionError("ensure_store must not be called"),
                    ) as ensure_mock,
                ):
                    response = self.client.post(
                        "/knowledge/ingest-text",
                        json={
                            "title": "Whitespace knowledge body",
                            "body": body,
                            "source_type": "text",
                            "source_path": "/tmp/whitespace-body.md",
                            "origin": "manual",
                        },
                    )

                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.json(),
                    {"detail": "Knowledge body is empty."},
                )
                self.assertNotEqual(response.status_code, 200)
                self.assertNotEqual(response.json().get("status"), "success")
                ingest_mock.assert_not_called()
                ensure_mock.assert_not_called()
                self.assert_no_store_mutation(before, paths)
                self.assertEqual(self.read_jsonl(paths["records"]), [])
                self.assertEqual(self.read_jsonl(paths["candidates"]), [])
                self.assertEqual(self.read_jsonl(paths["review_queue"]), [])
                self.assertEqual(self.read_jsonl(paths["approval_operations"]), [])
                self.assertEqual(self.read_jsonl(paths["review_decisions"]), [])
                self.assertEqual(self.read_jsonl(paths["memory_records"]), [])
                self.assertFalse(paths["memory_index"].exists())
                self.assertFalse(paths["entity_index"].exists())

    def test_single_space_body_returns_validation_error_without_mutation(self):
        self.assert_whitespace_body_rejected_without_mutation(" ")

    def test_multi_space_body_returns_validation_error_without_mutation(self):
        self.assert_whitespace_body_rejected_without_mutation("     ")

    def test_tab_only_body_returns_validation_error_without_mutation(self):
        self.assert_whitespace_body_rejected_without_mutation("\t")

    def test_newline_only_body_returns_validation_error_without_mutation(self):
        self.assert_whitespace_body_rejected_without_mutation("\n")

    def test_mixed_ascii_whitespace_body_returns_validation_error_without_mutation(self):
        self.assert_whitespace_body_rejected_without_mutation(" \t\n ")

    def test_literal_empty_and_missing_body_remain_validation_errors(self):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tempdir:
            paths, patches = self.isolated_stores(tempdir)
            with ExitStack() as stack:
                for item in patches:
                    stack.enter_context(item)

                before = self.store_bytes(paths)

                with (
                    patch.object(
                        app.knowledge_ingest,
                        "normalize_text",
                        side_effect=AssertionError("route must not execute"),
                    ) as normalize_mock,
                    patch.object(
                        app.knowledge_ingest,
                        "ingest_text",
                        side_effect=AssertionError("ingest_text must not be called"),
                    ) as ingest_mock,
                    patch.object(
                        app.knowledge_ingest,
                        "ensure_store",
                        side_effect=AssertionError("ensure_store must not be called"),
                    ) as ensure_mock,
                ):
                    literal_empty = self.client.post(
                        "/knowledge/ingest-text",
                        json={
                            "title": "Literal empty body",
                            "body": "",
                            "source_type": "text",
                            "source_path": "/tmp/literal-empty.md",
                            "origin": "manual",
                        },
                    )
                    missing_body = self.client.post(
                        "/knowledge/ingest-text",
                        json={
                            "title": "Missing body",
                            "source_type": "text",
                            "source_path": "/tmp/missing-body.md",
                            "origin": "manual",
                        },
                    )

                self.assertEqual(literal_empty.status_code, 422)
                self.assertEqual(missing_body.status_code, 422)
                self.assertIsInstance(literal_empty.json()["detail"], list)
                self.assertIsInstance(missing_body.json()["detail"], list)
                normalize_mock.assert_not_called()
                ingest_mock.assert_not_called()
                ensure_mock.assert_not_called()
                self.assert_no_store_mutation(before, paths)

    def test_duplicate_and_search_behavior_are_preserved(self):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tempdir:
            paths, patches = self.isolated_stores(tempdir)
            with ExitStack() as stack:
                for item in patches:
                    stack.enter_context(item)

                body = "Duplicate doctrine body must preserve exact hash behavior."
                first = self.client.post(
                    "/knowledge/ingest-text",
                    json={
                        "title": "Duplicate source",
                        "body": body,
                        "source_type": "text",
                        "source_path": "/tmp/duplicate-a.md",
                        "origin": "manual",
                    },
                )
                duplicate = self.client.post(
                    "/knowledge/ingest-text",
                    json={
                        "title": "Duplicate source copy",
                        "body": body,
                        "source_type": "text",
                        "source_path": "/tmp/duplicate-b.md",
                        "origin": "manual",
                    },
                )

                self.assertEqual(first.status_code, 200)
                self.assertEqual(first.json()["status"], "success")
                self.assertEqual(duplicate.status_code, 200)
                self.assertEqual(duplicate.json()["status"], "duplicate")
                self.assertEqual(
                    duplicate.json()["duplicate_reason"],
                    "exact_content_hash_match",
                )
                self.assertEqual(len(self.read_jsonl(paths["records"])), 2)

                default_search = self.client.get(
                    "/knowledge/search",
                    params={"query": "duplicate doctrine"},
                )
                duplicate_search = self.client.get(
                    "/knowledge/search",
                    params={
                        "query": "duplicate doctrine",
                        "include_duplicates": True,
                    },
                )

                self.assertEqual(default_search.status_code, 200)
                self.assertEqual(default_search.json()["returned_count"], 1)
                self.assertEqual(default_search.json()["skipped"]["duplicates"], 1)
                self.assertEqual(duplicate_search.status_code, 200)
                self.assertEqual(duplicate_search.json()["returned_count"], 2)

    def test_large_valid_ingest_still_succeeds(self):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tempdir:
            paths, patches = self.isolated_stores(tempdir)
            with ExitStack() as stack:
                for item in patches:
                    stack.enter_context(item)

                response = self.client.post(
                    "/knowledge/ingest-text",
                    json={
                        "title": "Large body",
                        "body": "x" * 100000,
                        "source_type": "text",
                        "source_path": "/tmp/large-body.md",
                        "origin": "manual",
                    },
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["status"], "success")
                self.assertEqual(len(self.read_jsonl(paths["records"])), 1)

    def test_public_from_record_endpoint_creates_governed_candidate(self):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tempdir:
            paths, patches = self.isolated_stores(tempdir)
            with ExitStack() as stack:
                for item in patches:
                    stack.enter_context(item)

                ingest = self.ingest_eligible_record()
                record = ingest["record"]
                source = ingest["source"]
                expected_score = app.knowledge_ingest.knowledge_candidate_score(
                    record,
                    source,
                )

                response = self.client.post(
                    "/knowledge/candidates/from-record",
                    json={
                        "knowledge_record_id": record["record_id"],
                        "created_by": "Test Oracle",
                    },
                )

                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertEqual(payload["status"], "success")

                candidate = payload["candidate"]
                self.assertEqual(candidate["knowledge_record_id"], record["record_id"])
                self.assertEqual(candidate["source_id"], record["source_id"])
                self.assertEqual(candidate["source_kind"], "knowledge")
                self.assertEqual(candidate["source_title"], record["source_title"])
                self.assertEqual(candidate["source_path"], record["source_path"])
                self.assertIn(record["record_id"], candidate["provenance"])
                self.assertIn(record["source_id"], candidate["provenance"])
                self.assertIn(record["provenance"], candidate["provenance"])
                self.assertEqual(candidate["candidate_score"], expected_score["score"])
                self.assertEqual(candidate["signals"], expected_score["signals"])
                self.assertEqual(candidate["confidence"], expected_score["confidence"])
                self.assertEqual(candidate["importance"], expected_score["importance"])
                self.assertEqual(candidate["review_status"], "candidate_created")
                self.assertFalse(candidate["memory_write_allowed"])
                self.assertTrue(candidate["candidate_path_allowed"])

                self.assertEqual(len(self.read_jsonl(paths["candidates"])), 1)
                self.assertEqual(self.read_jsonl(paths["review_queue"]), [])
                self.assertEqual(self.read_jsonl(paths["review_decisions"]), [])
                self.assertEqual(self.read_jsonl(paths["approval_operations"]), [])
                self.assertEqual(self.read_jsonl(paths["memory_records"]), [])
                self.assertEqual(self.read_jsonl(paths["review_queue"]), [])
                self.assertFalse(paths["memory_index"].exists())
                self.assertFalse(paths["entity_index"].exists())

                candidates = self.client.get("/knowledge/candidates")
                self.assertEqual(candidates.status_code, 200)
                self.assertEqual(
                    [item["candidate_id"] for item in candidates.json()["candidates"]],
                    [candidate["candidate_id"]],
                )

                status = self.client.get("/knowledge/candidates/status")
                self.assertEqual(status.status_code, 200)
                self.assertEqual(status.json()["counts"], {"candidate_created": 1})

                bridge = self.client.get("/knowledge/candidates/bridge-status")
                self.assertEqual(bridge.status_code, 200)
                self.assertEqual(bridge.json()["counts"]["candidate_created"], 1)
                self.assertEqual(
                    bridge.json()["record_states"][0]["bridge_state"],
                    "candidate_created",
                )

    def test_repeated_candidate_creation_returns_existing_candidate(self):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tempdir:
            paths, patches = self.isolated_stores(tempdir)
            with ExitStack() as stack:
                for item in patches:
                    stack.enter_context(item)

                record = self.ingest_eligible_record()["record"]

                first = self.client.post(
                    "/knowledge/candidates/from-record",
                    json={"knowledge_record_id": record["record_id"]},
                )
                second = self.client.post(
                    "/knowledge/candidates/from-record",
                    json={"knowledge_record_id": record["record_id"]},
                )

                self.assertEqual(first.status_code, 200)
                self.assertEqual(second.status_code, 200)
                first_candidate = first.json()["candidate"]
                second_payload = second.json()
                self.assertEqual(second_payload["status"], "existing_candidate")
                self.assertEqual(
                    second_payload["candidate"]["candidate_id"],
                    first_candidate["candidate_id"],
                )
                self.assertEqual(second_payload["bridge_state"], "candidate_created")
                self.assertEqual(len(self.read_jsonl(paths["candidates"])), 1)

    def test_below_threshold_and_missing_record_behavior_are_preserved(self):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tempdir:
            paths, patches = self.isolated_stores(tempdir)
            with ExitStack() as stack:
                for item in patches:
                    stack.enter_context(item)

                low_signal = self.client.post(
                    "/knowledge/ingest-text",
                    json={
                        "title": "Plain note",
                        "body": "plain words only",
                        "source_type": "text",
                        "source_path": "/tmp/plain-note.md",
                        "origin": "manual",
                    },
                )
                self.assertEqual(low_signal.status_code, 200)
                record = low_signal.json()["record"]

                below = self.client.post(
                    "/knowledge/candidates/from-record",
                    json={"knowledge_record_id": record["record_id"]},
                )

                self.assertEqual(below.status_code, 200)
                self.assertEqual(below.json()["status"], "not_created")
                self.assertEqual(below.json()["reason"], "candidate_score_too_low")
                self.assertLess(below.json()["score"]["score"], 0.25)
                self.assertEqual(self.read_jsonl(paths["candidates"]), [])

                before_missing = self.store_bytes(paths)
                missing = self.client.post(
                    "/knowledge/candidates/from-record",
                    json={"knowledge_record_id": "missing-record"},
                )

                self.assertEqual(missing.status_code, 400)
                self.assertEqual(missing.json(), {"detail": "knowledge_record_not_found"})
                self.assert_no_store_mutation(before_missing, paths)

    def test_missing_candidate_enqueue_returns_client_error_without_mutation(self):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tempdir:
            paths, patches = self.isolated_stores(tempdir)
            with ExitStack() as stack:
                for item in patches:
                    stack.enter_context(item)

                before = self.store_bytes(paths)

                response = self.client.post(
                    "/knowledge/candidates/missing-candidate/enqueue",
                    json={"reviewed_by": "Test Oracle"},
                )

                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.json(),
                    {"detail": "knowledge_candidate_not_found"},
                )
                self.assert_no_store_mutation(before, paths)

    def test_missing_candidate_record_returns_client_error_without_initializing_stores(self):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tempdir:
            paths, patches = self.isolated_stores(tempdir)
            with ExitStack() as stack:
                for item in patches:
                    stack.enter_context(item)

                before = self.store_bytes(paths)

                response = self.client.post(
                    "/knowledge/candidates/from-record",
                    json={"knowledge_record_id": "missing-record"},
                )

                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json(), {"detail": "knowledge_record_not_found"})
                self.assert_no_store_mutation(before, paths)

    def test_valid_candidate_enqueue_remains_successful_and_governed(self):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tempdir:
            paths, patches = self.isolated_stores(tempdir)
            with ExitStack() as stack:
                for item in patches:
                    stack.enter_context(item)

                record = self.ingest_eligible_record()["record"]
                created = self.client.post(
                    "/knowledge/candidates/from-record",
                    json={"knowledge_record_id": record["record_id"]},
                )
                candidate = created.json()["candidate"]

                response = self.client.post(
                    f"/knowledge/candidates/{candidate['candidate_id']}/enqueue",
                    json={"reviewed_by": "Test Oracle", "notes": "enqueue review"},
                )

                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertEqual(payload["status"], "success")
                self.assertEqual(payload["candidate"]["review_status"], "candidate_queued")
                self.assertEqual(
                    payload["candidate"]["candidate_id"],
                    candidate["candidate_id"],
                )
                self.assertEqual(len(self.read_jsonl(paths["review_queue"])), 1)
                self.assertEqual(
                    [item["review_status"] for item in self.read_jsonl(paths["candidates"])],
                    ["candidate_created", "candidate_queued"],
                )
                self.assertEqual(self.read_jsonl(paths["approval_operations"]), [])
                self.assertEqual(self.read_jsonl(paths["review_decisions"]), [])
                self.assertEqual(self.read_jsonl(paths["memory_records"]), [])
                self.assertFalse(paths["memory_index"].exists())
                self.assertFalse(paths["entity_index"].exists())

    def test_binding_safety_and_operation_helpers_avoid_candidate_builder_alias(self):
        self.assertEqual(
            str(inspect.signature(app.knowledge_ingest.register_source)),
            "(*, source_title: 'str', source_type: 'str', source_path: 'str', origin: 'str', tags: 'list[str]', hash_value: 'str', duplicate_of: 'str | None' = None, duplicate_reason: 'str' = '') -> 'dict[str, Any]'",
        )
        self.assertEqual(app.knowledge_ingest.ensure_store.__code__.co_firstlineno, 60)
        self.assertEqual(app.knowledge_ingest.save_sources.__code__.co_firstlineno, 111)
        self.assertEqual(app.knowledge_ingest.write_record.__code__.co_firstlineno, 139)
        self.assertEqual(app.knowledge_ingest.write_knowledge_candidate.__code__.co_firstlineno, 1282)
        self.assertIn("_write_sources_atomically", app.knowledge_ingest.ensure_store.__code__.co_names)
        self.assertIn("_write_sources_atomically", app.knowledge_ingest.save_sources.__code__.co_names)
        self.assertIn("_append_jsonl_line_durably", app.knowledge_ingest.write_record.__code__.co_names)
        self.assertIn(
            "_append_jsonl_line_durably",
            app.knowledge_ingest.write_knowledge_candidate.__code__.co_names,
        )
        self.assertIn(
            "_previous_build_candidate_from_knowledge_v028c1b",
            app.knowledge_ingest.build_candidate_from_knowledge.__code__.co_names,
        )

        forbidden = "_previous_build_candidate_from_knowledge_v028c1b"
        for name, helper in inspect.getmembers(app.knowledge_ingest, inspect.isfunction):
            if "operation" not in name and "source_registry" not in name and "enqueue" not in name:
                continue
            if name == "build_candidate_from_knowledge":
                continue

            self.assertNotIn(forbidden, helper.__code__.co_names, name)
            self.assertNotIn(forbidden, inspect.getsource(helper), name)
            self.assertNotIn(forbidden, repr(helper.__defaults__), name)
            self.assertNotIn(forbidden, repr(helper.__kwdefaults__), name)
            self.assertIsNone(helper.__closure__, name)

    def test_source_registry_initialization_and_save_are_atomic(self):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tempdir:
            paths, patches = self.isolated_stores(tempdir)
            with ExitStack() as stack:
                for item in patches:
                    stack.enter_context(item)

                app.knowledge_ingest.ensure_store()
                self.assertTrue(paths["sources"].exists())
                self.assertEqual(json.loads(paths["sources"].read_text())["sources"], {})

                before = paths["sources"].read_bytes()
                with patch.object(
                    app.knowledge_ingest,
                    "_write_sources_atomically",
                    side_effect=RuntimeError("atomic source save failed"),
                ):
                    with self.assertRaises(RuntimeError):
                        app.knowledge_ingest.save_sources({"created_at": "x", "sources": {"bad": {}}})

                self.assertEqual(paths["sources"].read_bytes(), before)
                self.assertEqual(json.loads(paths["sources"].read_text())["sources"], {})

    def test_prepare_failure_creates_no_domain_objects(self):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tempdir:
            paths, patches = self.isolated_stores(tempdir)
            with ExitStack() as stack:
                for item in patches:
                    stack.enter_context(item)

                with patch.object(
                    app.knowledge_operations,
                    "prepare_operation",
                    side_effect=RuntimeError("prepare failed"),
                ):
                    response = self.client.post(
                        "/knowledge/ingest-text",
                        json={
                            "title": "Prepare failure",
                            "body": "prepare failure body",
                            "source_type": "text",
                            "source_path": "/tmp/prepare-failure.md",
                            "origin": "manual",
                        },
                    )

                self.assertEqual(response.status_code, 500)
                self.assertEqual(len(self.read_jsonl(paths["records"])), 0)
                self.assertEqual(len(self.read_jsonl(paths["candidates"])), 0)
                sources = json.loads(paths["sources"].read_text(encoding="utf-8"))
                self.assertEqual(sources["sources"], {})
                self.assertEqual(self.read_operations(paths["operations"]), [])

    def test_source_registration_orphan_recovers_on_retry(self):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tempdir:
            paths, patches = self.isolated_stores(tempdir)
            with ExitStack() as stack:
                for item in patches:
                    stack.enter_context(item)

                with patch.object(
                    app.knowledge_ingest,
                    "write_record",
                    side_effect=RuntimeError("record write failed"),
                ):
                    failed = self.client.post(
                        "/knowledge/ingest-text",
                        json={
                            "title": "Recoverable source",
                            "body": "recoverable source doctrine",
                            "source_type": "text",
                            "source_path": "/tmp/recoverable-source.md",
                            "origin": "manual",
                        },
                    )

                self.assertEqual(failed.status_code, 500)
                self.assertEqual(len(json.loads(paths["sources"].read_text())["sources"]), 1)
                self.assertEqual(len(self.read_jsonl(paths["records"])), 0)
                operations = self.read_operations(paths["operations"])
                self.assertEqual(len(operations), 1)
                self.assertEqual(operations[0]["state"], "in_progress")
                self.assertIn("source_durable", operations[0]["effect_progress"])
                intended_record_id = operations[0]["intended_identities"]["record_id"]

                retry = self.client.post(
                    "/knowledge/ingest-text",
                    json={
                        "title": "Recoverable source",
                        "body": "recoverable source doctrine",
                        "source_type": "text",
                        "source_path": "/tmp/recoverable-source.md",
                        "origin": "manual",
                    },
                )

                self.assertEqual(retry.status_code, 200)
                self.assertEqual(retry.json()["record"]["record_id"], intended_record_id)
                self.assertEqual(len(json.loads(paths["sources"].read_text())["sources"]), 1)
                self.assertEqual(len(self.read_jsonl(paths["records"])), 1)
                completed = self.read_operations(paths["operations"])[0]
                self.assertEqual(completed["state"], "complete")
                self.assertIn("record_durable", completed["effect_progress"])

    def test_record_progress_and_completion_failures_recover_without_duplicates(self):
        for patched_name in ("record_operation_progress", "complete_operation"):
            with self.subTest(patched_name=patched_name):
                with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tempdir:
                    paths, patches = self.isolated_stores(tempdir)
                    with ExitStack() as stack:
                        for item in patches:
                            stack.enter_context(item)

                        real = getattr(app.knowledge_operations, patched_name)
                        calls = {"count": 0}

                        def fail_once(*args, **kwargs):
                            calls["count"] += 1
                            if calls["count"] == 1:
                                raise RuntimeError(f"{patched_name} failed")
                            return real(*args, **kwargs)

                        with patch.object(app.knowledge_operations, patched_name, side_effect=fail_once):
                            failed = self.client.post(
                                "/knowledge/ingest-text",
                                json={
                                    "title": f"{patched_name} recovery",
                                    "body": f"{patched_name} recovery doctrine",
                                    "source_type": "text",
                                    "source_path": f"/tmp/{patched_name}.md",
                                    "origin": "manual",
                                },
                            )

                        self.assertEqual(failed.status_code, 500)
                        retry = self.client.post(
                            "/knowledge/ingest-text",
                            json={
                                "title": f"{patched_name} recovery",
                                "body": f"{patched_name} recovery doctrine",
                                "source_type": "text",
                                "source_path": f"/tmp/{patched_name}.md",
                                "origin": "manual",
                            },
                        )

                        self.assertEqual(retry.status_code, 200)
                        self.assertEqual(len(self.read_jsonl(paths["records"])), 1)
                        self.assertEqual(len(json.loads(paths["sources"].read_text())["sources"]), 1)
                        self.assertEqual(self.read_operations(paths["operations"])[0]["state"], "complete")

    def test_duplicate_source_and_event_persist_atomically(self):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tempdir:
            paths, patches = self.isolated_stores(tempdir)
            with ExitStack() as stack:
                for item in patches:
                    stack.enter_context(item)

                body = "duplicate atomic body"
                first = self.client.post(
                    "/knowledge/ingest-text",
                    json={"title": "Source A", "body": body, "source_type": "text", "source_path": "/tmp/a.md"},
                )
                duplicate = self.client.post(
                    "/knowledge/ingest-text",
                    json={"title": "Source B", "body": body, "source_type": "text", "source_path": "/tmp/b.md"},
                )

                self.assertEqual(first.status_code, 200)
                self.assertEqual(duplicate.status_code, 200)
                registry = json.loads(paths["sources"].read_text())
                duplicate_source_id = duplicate.json()["source"]["source_id"]
                events = [
                    event
                    for event in registry.get("duplicate_events", [])
                    if event["source_id"] == duplicate_source_id
                ]
                self.assertEqual(len(events), 1)
                self.assertEqual(events[0]["duplicate_reason"], "exact_content_hash_match")

    def test_duplicate_source_missing_event_conflicts_on_retry(self):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tempdir:
            paths, patches = self.isolated_stores(tempdir)
            with ExitStack() as stack:
                for item in patches:
                    stack.enter_context(item)

                body = "duplicate conflict body"
                first = self.client.post(
                    "/knowledge/ingest-text",
                    json={"title": "Source A", "body": body, "source_type": "text", "source_path": "/tmp/a.md"},
                )
                self.assertEqual(first.status_code, 200)

                with patch.object(
                    app.knowledge_operations,
                    "record_operation_progress",
                    side_effect=RuntimeError("progress failed"),
                ):
                    failed = self.client.post(
                        "/knowledge/ingest-text",
                        json={"title": "Source B", "body": body, "source_type": "text", "source_path": "/tmp/b.md"},
                    )
                self.assertEqual(failed.status_code, 500)

                registry = json.loads(paths["sources"].read_text())
                registry["duplicate_events"] = []
                paths["sources"].write_text(json.dumps(registry), encoding="utf-8")

                retry = self.client.post(
                    "/knowledge/ingest-text",
                    json={"title": "Source B", "body": body, "source_type": "text", "source_path": "/tmp/b.md"},
                )
                self.assertEqual(retry.status_code, 409)
                self.assertEqual(retry.json(), {"detail": "knowledge_operation_conflict"})

    def test_pending_nonduplicate_becoming_duplicate_recovers_with_refreshed_record_source(self):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tempdir:
            paths, patches = self.isolated_stores(tempdir)
            with ExitStack() as stack:
                for item in patches:
                    stack.enter_context(item)

                body = "pending transition duplicate body"
                with patch.object(
                    app.knowledge_ingest,
                    "_persist_operation_source_registry_effect",
                    side_effect=RuntimeError("source effect held"),
                ):
                    original = self.post_text("Original", body, "/tmp/original.md")

                self.assertEqual(original.status_code, 500)
                pending = self.read_operations(paths["operations"])[0]
                obsolete_source_id = pending["intended_identities"]["source_id"]
                self.assertFalse(obsolete_source_id.startswith("ksrc_dup_"))

                intervening = self.post_text("Intervening", body, "/tmp/intervening.md")
                self.assertEqual(intervening.status_code, 200)
                self.assertEqual(intervening.json()["source"]["source_id"], obsolete_source_id)

                retry = self.post_text("Original", body, "/tmp/original.md")
                self.assertEqual(retry.status_code, 200)
                self.assertEqual(retry.json()["status"], "duplicate")

                operation, durable_source, durable_record = self.assert_ingest_source_record_coherence(
                    paths,
                    expected_duplicate=True,
                    excluded_source_id=obsolete_source_id,
                    operation_index=0,
                )
                self.assertEqual(durable_source["duplicate_of"], obsolete_source_id)
                self.assertEqual(durable_record["duplicate_of"], obsolete_source_id)
                self.assertEqual(len(self.read_jsonl(paths["records"])), 2)
                self.assertEqual(len(self.read_sources(paths["sources"])["sources"]), 2)
                transition_details = [
                    item["detail"]
                    for item in operation["transition_history"]
                ]
                last_refresh_index = max(
                    index
                    for index, detail in enumerate(transition_details)
                    if detail == "intent_refreshed"
                )
                source_durable_index = transition_details.index("source_durable_durable")
                self.assertLess(last_refresh_index, source_durable_index)

                later_duplicate = self.post_text("Later duplicate", body, "/tmp/later.md")
                self.assertEqual(later_duplicate.status_code, 200)
                self.assertEqual(later_duplicate.json()["status"], "duplicate")
                self.assertEqual(
                    later_duplicate.json()["duplicate_reason"],
                    "exact_content_hash_match",
                )

    def test_pending_duplicate_becoming_nonduplicate_remains_isolated_and_coherent(self):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tempdir:
            paths, patches = self.isolated_stores(tempdir)
            with ExitStack() as stack:
                for item in patches:
                    stack.enter_context(item)

                body = "duplicate to nonduplicate body"
                seed = self.post_text("Seed", body, "/tmp/seed.md")
                self.assertEqual(seed.status_code, 200)
                with patch.object(
                    app.knowledge_ingest,
                    "_persist_operation_source_registry_effect",
                    side_effect=RuntimeError("source effect held"),
                ):
                    pending_response = self.post_text("Pending", body, "/tmp/pending.md")
                self.assertEqual(pending_response.status_code, 500)
                pending = self.read_operations(paths["operations"])[-1]
                obsolete_duplicate_id = pending["intended_identities"]["source_id"]
                self.assertTrue(obsolete_duplicate_id.startswith("ksrc_dup_"))

                registry = self.read_sources(paths["sources"])
                registry["sources"] = {}
                registry["duplicate_events"] = []
                paths["sources"].write_text(json.dumps(registry), encoding="utf-8")

                retry = self.post_text("Pending", body, "/tmp/pending.md")
                self.assertEqual(retry.status_code, 200)
                self.assertEqual(retry.json()["status"], "success")

                operation, durable_source, durable_record = self.assert_ingest_source_record_coherence(
                    paths,
                    expected_duplicate=False,
                    excluded_source_id=obsolete_duplicate_id,
                )
                self.assertFalse(durable_record["source_id"].startswith("ksrc_dup_"))
                self.assertIsNone(durable_source["duplicate_of"])
                self.assertEqual(durable_source["duplicate_reason"], "")
                self.assertEqual(operation["intended_effect_payloads"]["duplicate_event"], None)

    def test_pending_duplicate_target_refresh_keeps_duplicate_source_id(self):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tempdir:
            paths, patches = self.isolated_stores(tempdir)
            with ExitStack() as stack:
                for item in patches:
                    stack.enter_context(item)

                body = "duplicate target refresh body"
                seed = self.post_text("Seed A", body, "/tmp/seed-a.md")
                self.assertEqual(seed.status_code, 200)
                with patch.object(
                    app.knowledge_ingest,
                    "_persist_operation_source_registry_effect",
                    side_effect=RuntimeError("source effect held"),
                ):
                    pending_response = self.post_text("Pending", body, "/tmp/pending.md")
                self.assertEqual(pending_response.status_code, 500)
                pending = self.read_operations(paths["operations"])[-1]
                stable_duplicate_id = pending["intended_identities"]["source_id"]
                original_target = pending["intended_effect_payloads"]["source"]["duplicate_of"]

                registry = self.read_sources(paths["sources"])
                target = dict(registry["sources"][original_target])
                target["source_id"] = "ksrc_manual_refresh_target"
                target["source_title"] = "Seed B"
                registry["sources"] = {target["source_id"]: target}
                paths["sources"].write_text(json.dumps(registry), encoding="utf-8")

                retry = self.post_text("Pending", body, "/tmp/pending.md")
                self.assertEqual(retry.status_code, 200)
                self.assertEqual(retry.json()["status"], "duplicate")

                operation, durable_source, durable_record = self.assert_ingest_source_record_coherence(
                    paths,
                    expected_duplicate=True,
                )
                self.assertEqual(operation["intended_identities"]["source_id"], stable_duplicate_id)
                self.assertEqual(durable_record["source_id"], stable_duplicate_id)
                self.assertEqual(durable_source["duplicate_of"], "ksrc_manual_refresh_target")
                self.assertNotEqual(durable_source["duplicate_of"], original_target)

    def test_update_operation_intent_failure_blocks_duplicate_transition_effects_then_recovers(self):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tempdir:
            paths, patches = self.isolated_stores(tempdir)
            with ExitStack() as stack:
                for item in patches:
                    stack.enter_context(item)

                body = "intent refresh failure body"
                with patch.object(
                    app.knowledge_ingest,
                    "_persist_operation_source_registry_effect",
                    side_effect=RuntimeError("source effect held"),
                ):
                    original = self.post_text("Original", body, "/tmp/original.md")
                self.assertEqual(original.status_code, 500)
                pending = self.read_operations(paths["operations"])[0]
                obsolete_source_id = pending["intended_identities"]["source_id"]

                intervening = self.post_text("Intervening", body, "/tmp/intervening.md")
                self.assertEqual(intervening.status_code, 200)
                before_sources = self.read_sources(paths["sources"])
                before_records = list(self.read_jsonl(paths["records"]))

                with patch.object(
                    app.knowledge_operations,
                    "update_operation_intent",
                    side_effect=RuntimeError("intent refresh failed"),
                ) as intent_mock:
                    failed = self.post_text("Original", body, "/tmp/original.md")

                self.assertEqual(failed.status_code, 500)
                intent_mock.assert_called_once()
                self.assertEqual(self.read_sources(paths["sources"]), before_sources)
                self.assertEqual(self.read_jsonl(paths["records"]), before_records)
                still_pending = self.read_operations(paths["operations"])[0]
                self.assertNotEqual(still_pending["state"], "complete")
                self.assertEqual(still_pending["intended_identities"]["source_id"], obsolete_source_id)

                retry = self.post_text("Original", body, "/tmp/original.md")
                self.assertEqual(retry.status_code, 200)
                self.assertEqual(retry.json()["status"], "duplicate")
                self.assert_ingest_source_record_coherence(
                    paths,
                    expected_duplicate=True,
                    excluded_source_id=obsolete_source_id,
                    operation_index=0,
                )

    def test_record_fsync_failure_is_retried_without_new_record_id(self):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tempdir:
            paths, patches = self.isolated_stores(tempdir)
            with ExitStack() as stack:
                for item in patches:
                    stack.enter_context(item)

                real_append = app.knowledge_ingest._append_jsonl_line_durably

                def fail_record_append(path, payload):
                    if path == paths["records"]:
                        raise RuntimeError("record fsync failed")
                    return real_append(path, payload)

                with patch.object(
                    app.knowledge_ingest,
                    "_append_jsonl_line_durably",
                    side_effect=fail_record_append,
                ):
                    failed = self.client.post(
                        "/knowledge/ingest-text",
                        json={
                            "title": "Record fsync",
                            "body": "record fsync doctrine",
                            "source_type": "text",
                            "source_path": "/tmp/record-fsync.md",
                            "origin": "manual",
                        },
                    )

                self.assertEqual(failed.status_code, 500)
                operation = self.read_operations(paths["operations"])[0]
                self.assertNotIn("record_durable", operation["effect_progress"])
                intended_record_id = operation["intended_identities"]["record_id"]

                with patch.object(
                    app.knowledge_ingest,
                    "make_record_id",
                    side_effect=AssertionError("record ID must be reused"),
                ):
                    retry = self.client.post(
                        "/knowledge/ingest-text",
                        json={
                            "title": "Record fsync",
                            "body": "record fsync doctrine",
                            "source_type": "text",
                            "source_path": "/tmp/record-fsync.md",
                            "origin": "manual",
                        },
                    )

                self.assertEqual(retry.status_code, 200)
                self.assertEqual(retry.json()["record"]["record_id"], intended_record_id)
                self.assertEqual(len(self.read_jsonl(paths["records"])), 1)

    def test_duplicate_record_id_conflicts_without_persistent_index(self):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tempdir:
            paths, patches = self.isolated_stores(tempdir)
            with ExitStack() as stack:
                for item in patches:
                    stack.enter_context(item)

                first = self.client.post(
                    "/knowledge/ingest-text",
                    json={
                        "title": "Conflict record",
                        "body": "conflict record body",
                        "source_type": "text",
                        "source_path": "/tmp/conflict-record.md",
                    },
                )
                self.assertEqual(first.status_code, 200)
                record = first.json()["record"]
                with paths["records"].open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record) + "\n")

                with self.assertRaises(app.knowledge_operations.KnowledgeOperationConflict):
                    app.knowledge_ingest.find_record_by_id(record["record_id"])

                self.assertFalse((paths["knowledge_dir"] / "record_index.json").exists())

    def test_enqueue_candidate_event_failure_recovers_on_retry(self):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tempdir:
            paths, patches = self.isolated_stores(tempdir)
            with ExitStack() as stack:
                for item in patches:
                    stack.enter_context(item)

                record = self.ingest_eligible_record()["record"]
                created = self.client.post(
                    "/knowledge/candidates/from-record",
                    json={"knowledge_record_id": record["record_id"]},
                )
                candidate = created.json()["candidate"]
                before_events = len(self.read_jsonl(paths["candidates"]))
                before_reviews = len(self.read_jsonl(paths["review_queue"]))
                before_operations = len(self.read_jsonl(paths["approval_operations"]))
                before_decisions = len(self.read_jsonl(paths["review_decisions"]))
                before_memory = len(self.read_jsonl(paths["memory_records"]))
                index_before = self.store_bytes(
                    {
                        "memory_index": paths["memory_index"],
                        "entity_index": paths["entity_index"],
                    }
                )

                def fail_candidate_event(candidate_event):
                    raise RuntimeError("simulated candidate event failure")

                with patch.object(
                    app.knowledge_ingest,
                    "write_knowledge_candidate",
                    side_effect=fail_candidate_event,
                ):
                    response = self.client.post(
                        f"/knowledge/candidates/{candidate['candidate_id']}/enqueue",
                        json={"reviewed_by": "Test Oracle"},
                    )

                self.assertEqual(response.status_code, 500)
                self.assertEqual(len(self.read_jsonl(paths["candidates"])), before_events)
                self.assertEqual(len(self.read_jsonl(paths["review_queue"])), before_reviews + 1)
                operation = self.read_operations(paths["operations"])[-1]
                self.assertEqual(operation["operation_kind"], "knowledge_candidate_enqueue")
                self.assertEqual(operation["state"], "in_progress")
                self.assertIn("review_durable", operation["effect_progress"])
                self.assertNotIn("candidate_event_durable", operation["effect_progress"])
                self.assertEqual(
                    len(self.read_jsonl(paths["approval_operations"])),
                    before_operations,
                )
                self.assertEqual(
                    len(self.read_jsonl(paths["review_decisions"])),
                    before_decisions,
                )
                self.assertEqual(len(self.read_jsonl(paths["memory_records"])), before_memory)
                self.assertEqual(
                    self.store_bytes(
                        {
                            "memory_index": paths["memory_index"],
                            "entity_index": paths["entity_index"],
                        }
                    ),
                    index_before,
                )

                retry = self.client.post(
                    f"/knowledge/candidates/{candidate['candidate_id']}/enqueue",
                    json={"reviewed_by": "Test Oracle"},
                )

                self.assertEqual(retry.status_code, 200)
                self.assertEqual(len(self.read_jsonl(paths["review_queue"])), before_reviews + 1)
                self.assertEqual(len(self.read_jsonl(paths["candidates"])), before_events + 1)
                self.assertEqual(
                    [item["review_status"] for item in self.read_jsonl(paths["candidates"])],
                    ["candidate_created", "candidate_queued"],
                )
                self.assertEqual(self.read_operations(paths["operations"])[-1]["state"], "complete")

    def test_candidate_event_fsync_failure_and_completion_failure_recover(self):
        for patched_name in ("_append_jsonl_line_durably", "complete_operation"):
            with self.subTest(patched_name=patched_name):
                with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tempdir:
                    paths, patches = self.isolated_stores(tempdir)
                    with ExitStack() as stack:
                        for item in patches:
                            stack.enter_context(item)

                        record = self.ingest_eligible_record()["record"]
                        created = self.client.post(
                            "/knowledge/candidates/from-record",
                            json={"knowledge_record_id": record["record_id"]},
                        )
                        candidate = created.json()["candidate"]

                        if patched_name == "_append_jsonl_line_durably":
                            real_append = app.knowledge_ingest._append_jsonl_line_durably

                            def fail_candidate_append(path, payload):
                                if path == paths["candidates"] and payload.get("review_status") == "candidate_queued":
                                    raise RuntimeError("candidate fsync failed")
                                return real_append(path, payload)

                            patcher = patch.object(
                                app.knowledge_ingest,
                                "_append_jsonl_line_durably",
                                side_effect=fail_candidate_append,
                            )
                        else:
                            real_complete = app.knowledge_operations.complete_operation
                            calls = {"count": 0}

                            def fail_complete_once(*args, **kwargs):
                                calls["count"] += 1
                                if calls["count"] == 1:
                                    raise RuntimeError("completion failed")
                                return real_complete(*args, **kwargs)

                            patcher = patch.object(
                                app.knowledge_operations,
                                "complete_operation",
                                side_effect=fail_complete_once,
                            )

                        with patcher:
                            failed = self.client.post(
                                f"/knowledge/candidates/{candidate['candidate_id']}/enqueue",
                                json={"reviewed_by": "Test Oracle"},
                            )

                        self.assertEqual(failed.status_code, 500)
                        retry = self.client.post(
                            f"/knowledge/candidates/{candidate['candidate_id']}/enqueue",
                            json={"reviewed_by": "Test Oracle"},
                        )

                        self.assertEqual(retry.status_code, 200)
                        self.assertEqual(len(self.read_jsonl(paths["review_queue"])), 1)
                        self.assertEqual(
                            [item["review_status"] for item in self.read_jsonl(paths["candidates"])],
                            ["candidate_created", "candidate_queued"],
                        )
                        self.assertEqual(self.read_operations(paths["operations"])[-1]["state"], "complete")

    def test_review_ambiguity_and_source_refs_only_collision_conflict(self):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tempdir:
            paths, patches = self.isolated_stores(tempdir)
            with ExitStack() as stack:
                for item in patches:
                    stack.enter_context(item)

                record = self.ingest_eligible_record()["record"]
                created = self.client.post(
                    "/knowledge/candidates/from-record",
                    json={"knowledge_record_id": record["record_id"]},
                )
                candidate = created.json()["candidate"]
                app.memory_review_queue.create_review_item(
                    candidate_record={"title": "collision"},
                    source_refs=[candidate["candidate_id"]],
                    original_record={"candidate_id": "other-candidate"},
                )
                response = self.client.post(
                    f"/knowledge/candidates/{candidate['candidate_id']}/enqueue",
                    json={"reviewed_by": "Test Oracle"},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(self.read_jsonl(paths["review_queue"])), 2)

                # Two canonical pending matches are ambiguous and must fail closed.
                app.memory_review_queue.create_review_item(
                    candidate_record={"title": "duplicate canonical"},
                    original_record=candidate,
                )
                conflict = self.client.post(
                    f"/knowledge/candidates/{candidate['candidate_id']}/enqueue",
                    json={"reviewed_by": "Test Oracle"},
                )
                self.assertEqual(conflict.status_code, 409)
                self.assertEqual(conflict.json(), {"detail": "knowledge_operation_conflict"})

    def test_operation_inventory_reports_detectable_pending_and_completed_state(self):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tempdir:
            paths, patches = self.isolated_stores(tempdir)
            with ExitStack() as stack:
                for item in patches:
                    stack.enter_context(item)

                with patch.object(
                    app.knowledge_ingest,
                    "write_record",
                    side_effect=RuntimeError("record write failed"),
                ):
                    self.client.post(
                        "/knowledge/ingest-text",
                        json={
                            "title": "Inventory",
                            "body": "inventory doctrine",
                            "source_type": "text",
                            "source_path": "/tmp/inventory.md",
                        },
                    )

                before_inventory = self.store_bytes(paths)
                inventory = self.client.get("/knowledge/operations")
                self.assertEqual(inventory.status_code, 200)
                payload = inventory.json()
                self.assertEqual(set(payload), {"counts", "operations"})
                self.assert_no_sensitive_operation_fields(payload)
                self.assertEqual(payload["counts"]["pending"], 1)
                item = payload["operations"][0]
                self.assertEqual(item["operation_kind"], "knowledge_ingest")
                self.assertTrue(item["intended_source_id"])
                self.assertTrue(item["intended_record_id"])
                self.assertIn("source_durable", item["effect_progress"])
                self.assertEqual(self.store_bytes(paths), before_inventory)


if __name__ == "__main__":
    unittest.main()
