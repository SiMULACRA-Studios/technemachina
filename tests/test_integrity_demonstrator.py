import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
DAEMON = ROOT / "daemon"
SCRIPTS = ROOT / "scripts"
FIXTURE = ROOT / "tests" / "fixtures" / "integrity_protected_memory.json"
for path in (DAEMON, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import integrity_demonstrator as integrity
import integrity_doctor
import run_integrity_demonstrator as runner


SESSION_ID = "019f7f87-37d5-7ec0-a82c-aca523a76785"


class IntegrityDemonstratorTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directories = []

    def tearDown(self):
        for temporary in self.temporary_directories:
            temporary.cleanup()

    def run_evidence(self, run_id: str = "test-run-001") -> dict:
        temporary = tempfile.TemporaryDirectory()
        self.temporary_directories.append(temporary)

        def attest(review_id: str, proposal_digest: str, bound_run_id: str):
            return integrity.make_attestation(
                session_id=SESSION_ID,
                run_id=bound_run_id,
                proposal_digest=proposal_digest,
                review_id=review_id,
                actor_label="Test Oracle",
                timestamp="2026-07-20T12:00:00+00:00",
                confirmation_mode="noninteractive_test_only",
            )

        evidence = integrity.run_demonstration(
            run_dir=Path(temporary.name) / "run",
            fixture_path=FIXTURE,
            session_id=SESSION_ID,
            baseline_commit="e05f900d1969ca51a7ef700bb42fd573628b6b91",
            source_git_commit="e05f900d1969ca51a7ef700bb42fd573628b6b91",
            branch="build-week/2026-integrity-demonstrator-019f7f87",
            run_id=run_id,
            attest=attest,
        )
        doctor = integrity_doctor.validate_evidence(evidence, require_final=False)
        evidence["integrity_doctor"] = doctor
        evidence["invariants"] = integrity.calculate_invariants(evidence)
        evidence["final_result"] = integrity.final_result(evidence["invariants"])
        return evidence

    def assert_doctor_fails(self, evidence: dict):
        result = integrity_doctor.validate_evidence(evidence)
        self.assertEqual(result["status"], "FAIL")

    def test_doctor_accepts_honestly_recorded_detached_clean_clone(self):
        evidence = self.run_evidence()
        evidence["current_branch"] = "(detached)"
        self.assertEqual(integrity_doctor.validate_evidence(evidence)["status"], "PASS")

    def test_canonicalization_determinism(self):
        left = {"z": 1, "a": {"two": 2, "one": 1}}
        right = {"a": {"one": 1, "two": 2}, "z": 1}
        self.assertEqual(integrity.canonical_json(left), integrity.canonical_json(right))
        self.assertEqual(integrity.canonical_json(left), '{"a":{"one":1,"two":2},"z":1}')

    def test_digest_determinism(self):
        value = {"records": [{"record_id": "two"}, {"record_id": "one"}]}
        self.assertEqual(integrity.sha256_value(value), integrity.sha256_value(copy.deepcopy(value)))

    def test_projection_order_is_stable(self):
        records = json.loads(FIXTURE.read_text(encoding="utf-8"))["records"]
        forward = integrity.protected_projection(records)
        reverse = integrity.protected_projection(list(reversed(records)))
        self.assertEqual(forward, reverse)
        self.assertEqual(
            [record["record_id"] for record in forward["records"]],
            ["mem_fixture_alpha_001", "mem_fixture_theta_001"],
        )

    def test_added_detection(self):
        before = {"records": [{"record_id": "one", "body": "stable"}]}
        after = {"records": before["records"] + [{"record_id": "two", "body": "new"}]}
        self.assertEqual(integrity.compare_projections(before, after)["added"], ["two"])

    def test_modified_detection(self):
        before = {"records": [{"record_id": "one", "body": "before"}]}
        after = {"records": [{"record_id": "one", "body": "after"}]}
        self.assertEqual(integrity.compare_projections(before, after)["modified"], ["one"])

    def test_removed_detection(self):
        before = {"records": [{"record_id": "one"}, {"record_id": "two"}]}
        after = {"records": [{"record_id": "one"}]}
        self.assertEqual(integrity.compare_projections(before, after)["removed"], ["two"])

    def test_rejected_proposal_does_not_enter_durable_memory(self):
        evidence = self.run_evidence()
        self.assertEqual(evidence["review_status"], "rejected")
        self.assertFalse(evidence["durable_memory_write_from_rejected_proposal"])
        self.assertTrue(evidence["invariants"]["proposal_not_durable"])

    def test_provenance_survives_in_governance_evidence(self):
        evidence = self.run_evidence()
        self.assertEqual(evidence["provenance"], evidence["proposal"]["provenance"])
        self.assertIn(SESSION_ID, evidence["provenance"])
        self.assertTrue(evidence["invariants"]["provenance_preserved"])

    def test_attestation_binds_session_run_proposal_review_and_action(self):
        evidence = self.run_evidence()
        attestation = evidence["local_human_attestation"]
        self.assertEqual(attestation["classification"], "local_human_attestation")
        self.assertEqual(attestation["codex_session_id"], SESSION_ID)
        self.assertEqual(attestation["run_id"], evidence["run_id"])
        self.assertEqual(attestation["proposal_digest"], evidence["proposal_digest"])
        self.assertEqual(attestation["review_id"], evidence["review_id"])
        self.assertEqual(attestation["action"], "reject")
        self.assertEqual(attestation["confirmation_mode"], "noninteractive_test_only")
        self.assertTrue(integrity.attestation_matches(evidence))

    def test_provider_exhaustion_attempts_every_configured_provider(self):
        evidence = self.run_evidence()
        self.assertEqual(
            [attempt["provider"] for attempt in evidence["provider_attempts"]],
            evidence["configured_demo_providers"],
        )

    def test_outcome_is_all_failed_and_winner_is_null(self):
        evidence = self.run_evidence()
        self.assertEqual(evidence["final_outcome"], "all_failed")
        self.assertIsNone(evidence["winning_provider"])

    def test_injected_failure_is_disclosed_for_every_attempt(self):
        evidence = self.run_evidence()
        for attempt in evidence["provider_attempts"]:
            self.assertTrue(attempt["deterministic"])
            self.assertTrue(attempt["injected"])
            self.assertIn("deterministic_injected_failure", attempt["error"])
        failed_audits = [
            event for event in evidence["observed_audit_events"]
            if event["event_type"] == "provider_failed"
        ]
        self.assertTrue(failed_audits)
        self.assertTrue(all("deterministic_injected_failure" in event["detail"] for event in failed_audits))

    def test_no_fabricated_assistant_output_is_written(self):
        evidence = self.run_evidence()
        self.assertFalse(evidence["assistant_output_written"])

    def test_audit_growth_is_accepted(self):
        evidence = self.run_evidence()
        self.assertGreater(evidence["audit_growth"]["after"], evidence["audit_growth"]["before"])
        self.assertTrue(evidence["invariants"]["audit_growth_expected"])

    def test_protected_digest_remains_unchanged(self):
        evidence = self.run_evidence()
        self.assertEqual(evidence["before_digest"], evidence["after_digest"])
        self.assertEqual(evidence["protected_memory_diff"], {"added": [], "modified": [], "removed": []})

    def test_complete_evidence_passes_integrity_doctor(self):
        evidence = self.run_evidence()
        result = integrity_doctor.validate_evidence(evidence)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(evidence["final_result"], "PASS")

    def test_tampered_evidence_fails_integrity_doctor(self):
        evidence = self.run_evidence()
        evidence["before_projection"]["records"][0]["body"] = "tampered"
        self.assert_doctor_fails(evidence)

    def test_missing_evidence_field_fails(self):
        evidence = self.run_evidence()
        del evidence["proposal_digest"]
        self.assert_doctor_fails(evidence)

    def test_mismatched_digest_fails(self):
        evidence = self.run_evidence()
        evidence["after_digest"] = "0" * 64
        self.assert_doctor_fails(evidence)

    def test_unexpected_durable_memory_mutation_fails(self):
        evidence = self.run_evidence()
        evidence["durable_memory_records_after"].append(evidence["proposal"])
        evidence["durable_memory_write_from_rejected_proposal"] = True
        self.assert_doctor_fails(evidence)

    def test_missing_expected_audit_event_fails(self):
        evidence = self.run_evidence()
        evidence["observed_audit_events"].pop()
        self.assert_doctor_fails(evidence)

    def test_tampered_session_or_baseline_fails(self):
        evidence = self.run_evidence()
        evidence["codex_session_id"] = "wrong-session"
        self.assert_doctor_fails(evidence)

        evidence = self.run_evidence()
        evidence["baseline_git_commit"] = "0" * 40
        self.assert_doctor_fails(evidence)

    def test_tampered_fixture_digest_fails(self):
        evidence = self.run_evidence()
        evidence["deterministic_fixture"]["digest"] = "0" * 64
        self.assert_doctor_fails(evidence)

    def test_tampered_routing_decision_fails(self):
        evidence = self.run_evidence()
        evidence["routing_decision"]["provider_path"] = ["openrouter"]
        self.assert_doctor_fails(evidence)

    def test_duplicate_record_id_fails_closed(self):
        evidence = self.run_evidence()
        evidence["after_projection"]["records"].append(
            copy.deepcopy(evidence["after_projection"]["records"][0])
        )
        self.assert_doctor_fails(evidence)

    def test_malformed_evidence_cli_returns_nonzero(self):
        temporary = tempfile.TemporaryDirectory()
        self.temporary_directories.append(temporary)
        evidence_path = Path(temporary.name) / "malformed.json"
        evidence_path.write_text("{not-json", encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, str(SCRIPTS / "integrity_doctor.py"), str(evidence_path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("RESULT: FAIL", completed.stdout)

    def test_interactive_attestation_requires_exact_review_bound_challenge(self):
        with self.assertRaisesRegex(RuntimeError, "confirmation was not provided"):
            runner.interactive_attestation(
                session_id=SESSION_ID,
                run_id="interactive-run",
                proposal_digest="a" * 64,
                review_id="review-123",
                actor_label="Test Oracle",
                input_fn=lambda _prompt: "REJECT wrong-review",
            )

        attestation = runner.interactive_attestation(
            session_id=SESSION_ID,
            run_id="interactive-run",
            proposal_digest="a" * 64,
            review_id="review-123",
            actor_label="Test Oracle",
            input_fn=lambda _prompt: "REJECT review-123",
        )
        self.assertEqual(attestation["confirmation_mode"], "interactive")
        self.assertEqual(attestation["review_id"], "review-123")

    def test_actor_label_rejects_email_or_path_material(self):
        for actor_label in ("person@label", "folder/name", ""):
            with self.subTest(actor_label=actor_label):
                with self.assertRaises(ValueError):
                    integrity.make_attestation(
                        session_id=SESSION_ID,
                        run_id="run",
                        proposal_digest="a" * 64,
                        review_id="review",
                        actor_label=actor_label,
                    )

    def test_run_directory_inside_repository_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "outside the repository"):
            runner.ensure_safe_run_dir(ROOT / "submission-output")

    def test_provider_executor_requires_explicit_disclosure(self):
        with self.assertRaisesRegex(ValueError, "requires a non-empty disclosure"):
            integrity.brain_router.route(
                "probe",
                provider="auto",
                provider_executor=lambda _provider, _prompt: "response",
            )

    def test_production_default_route_uses_normal_provider_without_injection(self):
        temporary = tempfile.TemporaryDirectory()
        self.temporary_directories.append(temporary)
        run_dir = Path(temporary.name) / "normal-route"
        with integrity.isolated_runtime_paths(run_dir) as paths:
            with (
                patch.object(
                    integrity.brain_router.openrouter_provider,
                    "query",
                    return_value="Normal provider response.",
                ) as openrouter_query,
                patch.object(
                    integrity.brain_router.gemini_provider,
                    "query",
                ) as gemini_query,
            ):
                response = integrity.brain_router.route("Normal production probe.")

            audit_events = integrity.load_jsonl(paths["audit_path"])

        self.assertEqual(response, "Normal provider response.")
        openrouter_query.assert_called_once_with("Normal production probe.")
        gemini_query.assert_not_called()
        self.assertEqual(audit_events[0]["detail"], "Routing prompt to provider.")
        self.assertEqual(audit_events[1]["event_type"], "provider_success")

    def test_doctor_failure_prevents_pass(self):
        evidence = self.run_evidence()
        evidence["integrity_doctor"] = {"status": "FAIL", "checks": []}
        evidence["invariants"] = integrity.calculate_invariants(evidence)
        evidence["final_result"] = integrity.final_result(evidence["invariants"])
        self.assertEqual(evidence["final_result"], "FAIL")
        self.assertEqual(integrity.exit_code_for_evidence(evidence), 1)

    def test_each_required_invariant_individually_forces_nonzero(self):
        evidence = self.run_evidence()
        self.assertEqual(integrity.exit_code_for_evidence(evidence), 0)
        for name in integrity.REQUIRED_INVARIANTS:
            with self.subTest(invariant=name):
                changed = copy.deepcopy(evidence)
                changed["invariants"][name] = False
                self.assertEqual(integrity.exit_code_for_evidence(changed), 1)

    def test_repeated_isolated_runs_are_deterministic_except_run_metadata(self):
        first = self.run_evidence("repeat-run-one")
        second = self.run_evidence("repeat-run-two")

        def stable_projection(evidence: dict) -> dict:
            value = copy.deepcopy(evidence)
            value.pop("run_id")
            value.pop("utc_timestamp")
            value.pop("review_id")
            value.pop("local_human_attestation")
            value.pop("review_decisions")
            value.pop("review_record")
            return value

        self.assertEqual(stable_projection(first), stable_projection(second))


if __name__ == "__main__":
    unittest.main()
