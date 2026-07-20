#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DAEMON = ROOT / "daemon"
if str(DAEMON) not in sys.path:
    sys.path.insert(0, str(DAEMON))

import integrity_demonstrator as integrity


REQUIRED_FIELDS = (
    "schema_version",
    "project_name",
    "codex_session_id",
    "baseline_git_commit",
    "source_git_commit",
    "current_branch",
    "run_id",
    "utc_timestamp",
    "deterministic_fixture",
    "protected_scope_definition",
    "before_projection",
    "before_digest",
    "after_projection",
    "after_digest",
    "protected_memory_diff",
    "added",
    "modified",
    "removed",
    "proposal_id",
    "proposal_digest",
    "proposal",
    "proposal_generation_mode",
    "provenance",
    "review_id",
    "review_status",
    "review_decisions",
    "review_record",
    "local_human_attestation",
    "provider_attempts",
    "configured_demo_providers",
    "routing_decision",
    "injected_failure_disclosure",
    "final_outcome",
    "winning_provider",
    "assistant_output_written",
    "durable_memory_write_from_rejected_proposal",
    "durable_memory_records_before",
    "durable_memory_records_after",
    "expected_audit_events",
    "observed_audit_events",
    "integrity_doctor",
    "invariants",
    "final_result",
)


def check(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "detail": detail}


def validate_evidence(
    evidence: dict[str, Any],
    *,
    require_final: bool = True,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    missing = [field for field in REQUIRED_FIELDS if field not in evidence]
    checks.append(check("required_fields", not missing, "missing=" + ",".join(missing)))

    if missing:
        return {"status": "FAIL", "checks": checks}

    before_projection = evidence["before_projection"]
    after_projection = evidence["after_projection"]
    try:
        actual_diff = integrity.compare_projections(before_projection, after_projection)
        durable_before_by_id = integrity._records_by_id(
            evidence["durable_memory_records_before"]
        )
        durable_after_by_id = integrity._records_by_id(
            evidence["durable_memory_records_after"]
        )
    except (TypeError, ValueError, AttributeError) as exc:
        checks.append(check(
            "evidence_structure",
            False,
            f"{type(exc).__name__}: {exc}",
        ))
        return {"status": "FAIL", "checks": checks}
    expected_events = evidence["expected_audit_events"]
    observed_events = evidence["observed_audit_events"]
    fixture_digest = str(evidence["deterministic_fixture"].get("digest", ""))
    fixture_path = ROOT / "tests" / "fixtures" / "integrity_protected_memory.json"
    fixture_bytes = fixture_path.read_bytes()
    fixture = json.loads(fixture_bytes.decode("utf-8"))
    fixture_projection = integrity.protected_projection(fixture["records"])
    routing_decision = evidence["routing_decision"]
    attestation = evidence["local_human_attestation"]

    checks.extend((
        check(
            "schema_version",
            evidence["schema_version"] == integrity.SCHEMA_VERSION,
            str(evidence["schema_version"]),
        ),
        check(
            "project_name",
            evidence["project_name"] == integrity.PROJECT_NAME,
            str(evidence["project_name"]),
        ),
        check(
            "submission_identity",
            evidence["codex_session_id"] == integrity.EXPECTED_SESSION_ID
            and evidence["baseline_git_commit"] == integrity.EXPECTED_BASELINE_COMMIT
            and evidence["current_branch"]
            in (integrity.EXPECTED_BRANCH, "(detached)")
            and len(str(evidence["source_git_commit"])) == 40
            and all(
                character in "0123456789abcdef"
                for character in str(evidence["source_git_commit"])
            ),
            "qualifying session, pre-Build-Week baseline, qualifying branch or "
            "detached clean-clone checkout, and source commit",
        ),
        check(
            "tracked_fixture",
            evidence["deterministic_fixture"].get("identity")
            == integrity.EXPECTED_FIXTURE_ID
            and fixture.get("fixture_id") == integrity.EXPECTED_FIXTURE_ID
            and fixture_digest == hashlib.sha256(fixture_bytes).hexdigest()
            and evidence["durable_memory_records_before"] == fixture["records"]
            and before_projection == fixture_projection,
            "identity, raw digest, durable records, and projection match tracked fixture",
        ),
        check(
            "protected_scope",
            evidence["protected_scope_definition"] == integrity.protected_scope_definition()
            and before_projection.get("scope") == integrity.protected_scope_definition()
            and after_projection.get("scope") == integrity.protected_scope_definition(),
            "scope contract matches implementation",
        ),
        check(
            "before_digest",
            evidence["before_digest"] == integrity.sha256_value(before_projection),
            "recomputed canonical projection digest",
        ),
        check(
            "after_digest",
            evidence["after_digest"] == integrity.sha256_value(after_projection),
            "recomputed canonical projection digest",
        ),
        check(
            "protected_diff",
            evidence["protected_memory_diff"] == actual_diff
            and evidence["added"] == actual_diff["added"]
            and evidence["modified"] == actual_diff["modified"]
            and evidence["removed"] == actual_diff["removed"],
            "added/modified/removed recomputed by record ID",
        ),
        check(
            "proposal_digest",
            evidence["proposal_digest"] == integrity.sha256_value(evidence["proposal"]),
            "recomputed proposal digest",
        ),
        check(
            "proposal_generation_mode",
            evidence["proposal_generation_mode"]
            == "deterministic_offline_ai_proposal_fixture",
            "proposal is deterministic and does not claim live model inference",
        ),
        check(
            "proposal_identity",
            evidence["proposal_id"] == evidence["proposal"].get("record_id"),
            "proposal ID matches proposal payload",
        ),
        check(
            "provenance",
            evidence["provenance"] == evidence["proposal"].get("provenance")
            and bool(evidence["provenance"]),
            "AI proposal provenance retained",
        ),
        check(
            "local_human_attestation",
            integrity.attestation_matches(evidence),
            "binding matches session, run, proposal, review, and reject action",
        ),
        check(
            "rejection_decision",
            evidence["review_record"].get("review_id") == evidence["review_id"]
            and evidence["review_record"].get("review_status") == "rejected"
            and evidence["review_status"] == "rejected"
            and evidence["review_record"].get("candidate_record") == evidence["proposal"]
            and evidence["review_record"].get("provenance") == evidence["provenance"]
            and any(
                decision.get("review_id") == evidence["review_id"]
                and decision.get("decision") == "rejected"
                and decision.get("record_id") == evidence["proposal_id"]
                and decision.get("reviewed_by") == attestation.get("attested_actor_label")
                for decision in evidence["review_decisions"]
            ),
            "review contains proposal/provenance and authentic decision is rejected",
        ),
        check(
            "protected_memory_unchanged",
            evidence["before_digest"] == evidence["after_digest"]
            and actual_diff == {"added": [], "modified": [], "removed": []},
            "digest and record-ID diff are unchanged",
        ),
        check(
            "rejected_proposal_not_durable",
            evidence["durable_memory_write_from_rejected_proposal"] is False
            and evidence["proposal_id"] not in durable_after_by_id,
            "rejected proposal ID is absent from the durable store",
        ),
        check(
            "durable_store_unchanged",
            integrity.canonical_json(evidence["durable_memory_records_before"])
            == integrity.canonical_json(evidence["durable_memory_records_after"])
            and set(durable_before_by_id) == set(durable_after_by_id),
            "full isolated durable store is unchanged; audit/review ledgers may grow",
        ),
        check(
            "provider_attempts",
            [item.get("provider") for item in evidence["provider_attempts"]]
            == list(integrity.EXPECTED_PROVIDER_ORDER)
            and evidence.get("configured_demo_providers")
            == list(integrity.EXPECTED_PROVIDER_ORDER),
            "all configured demonstration providers attempted in order",
        ),
        check(
            "routing_decision",
            routing_decision.get("router_mode") == "auto"
            and routing_decision.get("provider_order")
            == list(integrity.EXPECTED_PROVIDER_ORDER)
            and routing_decision.get("provider_path")
            == list(integrity.EXPECTED_PROVIDER_ORDER)
            and [
                failure.get("provider")
                for failure in routing_decision.get("provider_failures", [])
            ] == list(integrity.EXPECTED_PROVIDER_ORDER)
            and routing_decision.get("outcome") == evidence["final_outcome"]
            and routing_decision.get("winning_provider")
            == evidence["winning_provider"],
            "safe decision-ledger projection confirms attempts and terminal outcome",
        ),
        check(
            "injected_failure_disclosure",
            bool(evidence["provider_attempts"])
            and "deterministic_injected_failure=true" in evidence["injected_failure_disclosure"]
            and all(
                item.get("deterministic") is True
                and item.get("injected") is True
                and "deterministic_injected_failure" in str(item.get("error", ""))
                for item in evidence["provider_attempts"]
            )
            and all(
                "deterministic_injected_failure" in str(failure.get("error", ""))
                for failure in routing_decision.get("provider_failures", [])
            )
            and integrity.audit_injection_is_disclosed(observed_events),
            "every provider failure is deterministic, injected, and disclosed",
        ),
        check(
            "all_failed",
            evidence["final_outcome"] == "all_failed"
            and evidence["winning_provider"] is None,
            "truthful exhausted-provider outcome with no winner",
        ),
        check(
            "assistant_output",
            evidence["assistant_output_written"] is False,
            "no assistant response artifact written",
        ),
        check(
            "audit_events",
            expected_events
            == integrity.expected_audit_events(list(integrity.EXPECTED_PROVIDER_ORDER))
            and integrity.audit_sequence_matches(expected_events, observed_events)
            and evidence.get("audit_growth") == {"before": 0, "after": len(expected_events)},
            "expected legitimate audit growth observed",
        ),
        check(
            "decision_ledger_growth",
            evidence.get("decision_ledger_growth") == {"before": 0, "after": 1},
            "one terminal routing decision appended",
        ),
    ))

    if require_final:
        calculated = integrity.calculate_invariants(evidence)
        checks.extend((
            check(
                "stored_doctor_result",
                evidence["integrity_doctor"].get("status") == "PASS",
                "evidence records a passing offline doctor",
            ),
            check(
                "invariant_results",
                evidence["invariants"] == calculated
                and set(calculated) == set(integrity.REQUIRED_INVARIANTS),
                "stored invariant map matches independent calculation",
            ),
            check(
                "final_result",
                evidence["final_result"] == "PASS"
                and integrity.final_result(calculated) == "PASS",
                "final result fails closed over every required invariant",
            ),
        ))

    return {
        "status": "PASS" if all(item["passed"] for item in checks) else "FAIL",
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Offline validator for Technemachina integrity evidence."
    )
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    try:
        evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
        result = validate_evidence(evidence, require_final=True)
    except Exception as exc:
        result = {
            "status": "FAIL",
            "checks": [check("evidence_read", False, f"{type(exc).__name__}: {exc}")],
        }

    if args.json_output:
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    else:
        print("TECHNEMACHINA OFFLINE INTEGRITY DOCTOR")
        for item in result["checks"]:
            marker = "PASS" if item["passed"] else "FAIL"
            print(f"{marker}  {item['name']}: {item['detail']}")
        print(f"RESULT: {result['status']}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
