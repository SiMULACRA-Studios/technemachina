import json
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
            "memory_dir": memory_dir,
            "review_queue": memory_dir / "review_queue.jsonl",
            "review_decisions": memory_dir / "review_decisions.jsonl",
            "approval_operations": memory_dir / "approval_operations.jsonl",
            "memory_records": memory_dir / "memory_records.jsonl",
            "memory_index": memory_dir / "memory_index.json",
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

                missing = self.client.post(
                    "/knowledge/candidates/from-record",
                    json={"knowledge_record_id": "missing-record"},
                )

                self.assertEqual(missing.status_code, 200)
                self.assertEqual(
                    missing.json(),
                    {
                        "status": "error",
                        "detail": "knowledge_record_not_found",
                    },
                )


if __name__ == "__main__":
    unittest.main()
