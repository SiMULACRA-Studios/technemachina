from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
import hashlib
import json

import audit_log
import brain_router
import decision_ledger
import memory_review_queue
import memory_taxonomy


SCHEMA_VERSION = "technemachina.integrity-evidence.v1"
PROJECT_NAME = "Technemachina: Integrity Demonstrator"
EXPECTED_SESSION_ID = "019f7f87-37d5-7ec0-a82c-aca523a76785"
EXPECTED_BASELINE_COMMIT = "e05f900d1969ca51a7ef700bb42fd573628b6b91"
EXPECTED_BRANCH = "build-week/2026-integrity-demonstrator-019f7f87"
EXPECTED_FIXTURE_ID = "technemachina-integrity-protected-memory-v1"
EXPECTED_PROVIDER_ORDER = ("openrouter", "gemini")
ATTESTATION_CLASSIFICATION = "local_human_attestation"
INJECTION_DISCLOSURE = (
    "deterministic_injected_failure=true; "
    "injection_seam=brain_router.provider_executor; network_access=false"
)
PROTECTED_LAYERS = ("alpha", "theta", "delta")
PROTECTED_RECORD_TYPES = (
    "project_fact",
    "decision",
    "procedure",
    "research_note",
    "external_reference",
    "risk_note",
    "doctrine_note",
)
VOLATILE_FIELDS_EXCLUDED: tuple[str, ...] = ()
REQUIRED_INVARIANTS = (
    "fixture_loaded",
    "attestation_binding_valid",
    "rejection_recorded",
    "proposal_not_durable",
    "durable_store_unchanged",
    "provenance_preserved",
    "protected_no_added",
    "protected_no_modified",
    "protected_no_removed",
    "protected_digest_unchanged",
    "provider_attempts_complete",
    "routing_decision_truthful",
    "provider_outcome_all_failed",
    "winning_provider_null",
    "injected_failure_disclosed",
    "assistant_output_not_written",
    "audit_growth_expected",
    "decision_ledger_growth_expected",
    "integrity_doctor_passed",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def protected_scope_definition() -> dict[str, Any]:
    return {
        "included_layers": list(PROTECTED_LAYERS),
        "included_record_types": list(PROTECTED_RECORD_TYPES),
        "record_order": "record_id ascending",
        "dictionary_key_order": "lexicographic via JSON sort_keys=true",
        "encoding": "UTF-8",
        "json_separators": [",", ":"],
        "volatile_fields_excluded": list(VOLATILE_FIELDS_EXCLUDED),
        "selection_rule": (
            "A record is protected when both its layer and record_type are in "
            "the explicit included sets. No record fields are excluded."
        ),
    }


def protected_projection(records: list[dict[str, Any]]) -> dict[str, Any]:
    selected = [
        dict(record)
        for record in records
        if (
            record.get("layer") in PROTECTED_LAYERS
            and record.get("record_type") in PROTECTED_RECORD_TYPES
        )
    ]
    selected.sort(key=lambda record: str(record.get("record_id", "")))
    _records_by_id(selected)
    return {
        "scope": protected_scope_definition(),
        "records": selected,
    }


def compare_projections(
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, list[str]]:
    before_by_id = _records_by_id(before.get("records", []))
    after_by_id = _records_by_id(after.get("records", []))
    before_ids = set(before_by_id)
    after_ids = set(after_by_id)
    return {
        "added": sorted(after_ids - before_ids),
        "modified": sorted(
            record_id
            for record_id in before_ids & after_ids
            if canonical_json(before_by_id[record_id])
            != canonical_json(after_by_id[record_id])
        ),
        "removed": sorted(before_ids - after_ids),
    }


def _records_by_id(records: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(records, list):
        raise ValueError("Projection records must be a list.")
    result = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Every projected record must be an object.")
        record_id = record.get("record_id")
        if not isinstance(record_id, str) or not record_id.strip():
            raise ValueError("Every projected record requires a non-empty record_id.")
        if record_id in result:
            raise ValueError(f"Duplicate projected record_id: {record_id}")
        result[record_id] = record
    return result


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    path.write_text(text + ("\n" if rows else ""), encoding="utf-8")


def build_proposal(session_id: str) -> dict[str, Any]:
    seed = {
        "record_type": "doctrine_note",
        "layer": "delta",
        "scope": "global_doctrine",
        "title": "AI-proposed permanent memory modification",
        "summary": "A deliberately rejected permanent-memory proposal.",
        "body": (
            "Demonstration proposal: permanently remember an AI-authored "
            "integrity claim. This proposal must be rejected and remain outside "
            "durable protected memory."
        ),
        "tags": ["build-week-2026", "integrity-demonstrator", "ai-proposal"],
        "source_type": "ai_proposal",
        "source_ref": f"codex-session:{session_id}",
        "source_title": "GPT-5.6 Sol qualifying session",
        "created_by": "Technemachina AI proposal generator",
        "provenance": (
            "AI-originated proposal created for the Technemachina Integrity "
            f"Demonstrator in Codex session {session_id}; human review required."
        ),
        "confidence": "medium",
        "risk_level": "medium",
        "attach_to_context": False,
        "retrieval_priority": 0,
        "recency_weight": 0.0,
        "importance_weight": 1.0,
    }
    seed_digest = sha256_value(seed)
    return {"record_id": f"proposal_{seed_digest[:20]}", **seed}


def make_attestation(
    *,
    session_id: str,
    run_id: str,
    proposal_digest: str,
    review_id: str,
    actor_label: str,
    timestamp: str | None = None,
    confirmation_mode: str = "interactive",
) -> dict[str, Any]:
    actor_label = actor_label.strip()
    if (
        not actor_label
        or len(actor_label) > 80
        or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ._-" for character in actor_label)
    ):
        raise ValueError(
            "Attested actor label must be 1-80 characters using letters, "
            "numbers, spaces, period, underscore, or hyphen."
        )
    return {
        "classification": ATTESTATION_CLASSIFICATION,
        "codex_session_id": session_id,
        "run_id": run_id,
        "proposal_digest": proposal_digest,
        "review_id": review_id,
        "action": "reject",
        "attested_actor_label": actor_label,
        "timestamp": timestamp or utc_now(),
        "confirmation_mode": confirmation_mode,
        "identity_assurance": (
            "Local human confirmation only; not authenticated identity, a "
            "digital signature, or cryptographic proof of who the person is."
        ),
    }


def attestation_matches(evidence: dict[str, Any]) -> bool:
    attestation = evidence.get("local_human_attestation", {})
    return all((
        attestation.get("classification") == ATTESTATION_CLASSIFICATION,
        attestation.get("codex_session_id") == evidence.get("codex_session_id"),
        attestation.get("run_id") == evidence.get("run_id"),
        attestation.get("proposal_digest") == evidence.get("proposal_digest"),
        attestation.get("review_id") == evidence.get("review_id"),
        attestation.get("action") == "reject",
        bool(attestation.get("attested_actor_label")),
        bool(attestation.get("timestamp")),
        attestation.get("confirmation_mode")
        in {"interactive", "noninteractive_test_only"},
    ))


@contextmanager
def isolated_runtime_paths(run_dir: Path):
    memory_dir = run_dir / "state" / "memory"
    audit_dir = run_dir / "state" / "audit"
    ledger_dir = run_dir / "state" / "decision"
    replacements = (
        (memory_review_queue, "MEMORY_DIR", memory_dir),
        (memory_review_queue, "REVIEW_QUEUE_PATH", memory_dir / "review_queue.jsonl"),
        (memory_review_queue, "REVIEW_DECISIONS_PATH", memory_dir / "review_decisions.jsonl"),
        (memory_review_queue, "APPROVAL_OPERATIONS_PATH", memory_dir / "approval_operations.jsonl"),
        (memory_taxonomy, "MEMORY_DIR", memory_dir),
        (memory_taxonomy, "MEMORY_RECORDS_PATH", memory_dir / "memory_records.jsonl"),
        (memory_taxonomy, "MEMORY_INDEX_PATH", memory_dir / "memory_index.json"),
        (audit_log, "LOG_DIR", audit_dir),
        (audit_log, "LOG_PATH", audit_dir / "audit_log.jsonl"),
        (decision_ledger, "LEDGER_DIR", ledger_dir),
        (decision_ledger, "LEDGER_PATH", ledger_dir / "decision_ledger.jsonl"),
    )
    original = [(module, name, getattr(module, name)) for module, name, _ in replacements]
    try:
        for module, name, value in replacements:
            setattr(module, name, value)
        yield {
            "memory_dir": memory_dir,
            "audit_path": audit_dir / "audit_log.jsonl",
            "decision_path": ledger_dir / "decision_ledger.jsonl",
            "assistant_output_path": run_dir / "state" / "assistant_output.jsonl",
        }
    finally:
        for module, name, value in original:
            setattr(module, name, value)


def expected_audit_events(providers: list[str]) -> list[dict[str, str]]:
    events = []
    for provider in providers:
        events.extend((
            {"event_type": "provider_attempt", "status": "started", "provider": provider},
            {"event_type": "provider_failed", "status": "failure", "provider": provider},
        ))
    events.append({"event_type": "all_providers_failed", "status": "failure", "provider": "auto"})
    return events


def audit_event_projection(events: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "event_type": str(event.get("event_type", "")),
            "status": str(event.get("status", "")),
            "provider": str(event.get("provider", "")),
            "detail": str(event.get("detail", "")),
        }
        for event in events
    ]


def audit_sequence_matches(
    expected: list[dict[str, str]],
    observed: list[dict[str, str]],
) -> bool:
    return [
        {
            "event_type": item.get("event_type"),
            "status": item.get("status"),
            "provider": item.get("provider"),
        }
        for item in observed
    ] == expected


def audit_injection_is_disclosed(observed: list[dict[str, str]]) -> bool:
    relevant = [
        item for item in observed
        if item.get("event_type") in {
            "provider_attempt",
            "provider_failed",
            "all_providers_failed",
        }
    ]
    return bool(relevant) and all(
        "deterministic_injected_failure" in item.get("detail", "")
        for item in relevant
    )


def calculate_invariants(evidence: dict[str, Any]) -> dict[str, bool]:
    diff = evidence.get("protected_memory_diff", {})
    provider_attempts = evidence.get("provider_attempts", [])
    configured = evidence.get("configured_demo_providers", [])
    decisions = evidence.get("review_decisions", [])
    rejected = any(
        item.get("review_id") == evidence.get("review_id")
        and item.get("decision") == "rejected"
        for item in decisions
    )
    routing_decision = evidence.get("routing_decision", {})
    durable_before = evidence.get("durable_memory_records_before", [])
    durable_after = evidence.get("durable_memory_records_after", [])
    return {
        "fixture_loaded": (
            evidence.get("deterministic_fixture", {}).get("identity")
            == EXPECTED_FIXTURE_ID
            and evidence.get("deterministic_fixture", {}).get("record_count") == 3
        ),
        "attestation_binding_valid": attestation_matches(evidence),
        "rejection_recorded": rejected,
        "proposal_not_durable": (
            not evidence.get("durable_memory_write_from_rejected_proposal", True)
            and evidence.get("proposal_id")
            not in {record.get("record_id") for record in durable_after}
        ),
        "durable_store_unchanged": canonical_json(durable_before) == canonical_json(durable_after),
        "provenance_preserved": evidence.get("provenance") == evidence.get("proposal", {}).get("provenance"),
        "protected_no_added": diff.get("added") == [],
        "protected_no_modified": diff.get("modified") == [],
        "protected_no_removed": diff.get("removed") == [],
        "protected_digest_unchanged": evidence.get("before_digest") == evidence.get("after_digest"),
        "provider_attempts_complete": (
            configured == list(EXPECTED_PROVIDER_ORDER)
            and [item.get("provider") for item in provider_attempts] == configured
        ),
        "routing_decision_truthful": (
            routing_decision.get("provider_order") == configured
            and routing_decision.get("provider_path") == configured
            and [
                failure.get("provider")
                for failure in routing_decision.get("provider_failures", [])
            ] == configured
            and routing_decision.get("outcome") == evidence.get("final_outcome")
            and routing_decision.get("winning_provider") == evidence.get("winning_provider")
        ),
        "provider_outcome_all_failed": evidence.get("final_outcome") == "all_failed",
        "winning_provider_null": evidence.get("winning_provider") is None,
        "injected_failure_disclosed": bool(provider_attempts) and all(
            item.get("deterministic") is True
            and item.get("injected") is True
            and "deterministic_injected_failure" in str(item.get("error", ""))
            for item in provider_attempts
        ),
        "assistant_output_not_written": evidence.get("assistant_output_written") is False,
        "audit_growth_expected": (
            evidence.get("audit_growth", {}).get("before") == 0
            and evidence.get("audit_growth", {}).get("after")
            == len(evidence.get("expected_audit_events", []))
            and evidence.get("expected_audit_events", [])
            == expected_audit_events(list(EXPECTED_PROVIDER_ORDER))
            and audit_sequence_matches(
                evidence.get("expected_audit_events", []),
                evidence.get("observed_audit_events", []),
            )
            and audit_injection_is_disclosed(evidence.get("observed_audit_events", []))
        ),
        "decision_ledger_growth_expected": evidence.get("decision_ledger_growth") == {"before": 0, "after": 1},
        "integrity_doctor_passed": evidence.get("integrity_doctor", {}).get("status") == "PASS",
    }


def final_result(invariants: dict[str, bool]) -> str:
    return "PASS" if all(invariants.get(name) is True for name in REQUIRED_INVARIANTS) else "FAIL"


def exit_code_for_evidence(evidence: dict[str, Any]) -> int:
    invariants = evidence.get("invariants", {})
    return 0 if evidence.get("final_result") == "PASS" and final_result(invariants) == "PASS" else 1


def run_demonstration(
    *,
    run_dir: Path,
    fixture_path: Path,
    session_id: str,
    baseline_commit: str,
    source_git_commit: str,
    branch: str,
    run_id: str,
    attest: Callable[[str, str, str], dict[str, Any]],
) -> dict[str, Any]:
    if run_dir.exists() and any(run_dir.iterdir()):
        raise ValueError("Integrity run directory must be new or empty.")
    run_dir.mkdir(parents=True, exist_ok=True)

    fixture_bytes = fixture_path.read_bytes()
    fixture = json.loads(fixture_bytes.decode("utf-8"))
    fixture_records = fixture.get("records", [])
    if fixture.get("fixture_id") != EXPECTED_FIXTURE_ID:
        raise ValueError("Unexpected integrity fixture identity.")
    _records_by_id(fixture_records)
    for fixture_record in fixture_records:
        memory_taxonomy.validate_memory(fixture_record)
    proposal = build_proposal(session_id)
    proposal_digest = sha256_value(proposal)
    providers = list(brain_router.PROVIDER_ORDER)
    if providers != list(EXPECTED_PROVIDER_ORDER):
        raise ValueError("Configured provider order does not match the demonstration contract.")

    with isolated_runtime_paths(run_dir) as paths:
        records_path = paths["memory_dir"] / "memory_records.jsonl"
        write_jsonl(records_path, fixture_records)
        before_records = load_jsonl(records_path)
        before_projection = protected_projection(before_records)
        before_digest = sha256_value(before_projection)

        review = memory_review_queue.create_review_item(
            candidate_record=proposal,
            suggested_action="reject",
            reason="AI-originated permanent-memory proposal requires human review.",
            source_refs=[proposal["source_ref"]],
            created_by="Technemachina Integrity Demonstrator",
        )
        review_id = review["review_id"]
        attestation = attest(review_id, proposal_digest, run_id)
        if attestation.get("action") != "reject":
            raise ValueError("The local human attestation must reject the proposal.")
        rejection = memory_review_queue.reject_review(
            review_id,
            reviewed_by=attestation.get("attested_actor_label", ""),
            notes="Rejected through explicit local human attestation.",
        )

        def deterministic_failure(provider: str, _prompt: str) -> str:
            raise RuntimeError(
                "503 deterministic_injected_failure "
                f"provider={provider}; {INJECTION_DISCLOSURE}"
            )

        routing_error = ""
        assistant_response = None
        try:
            assistant_response = brain_router.route(
                "Integrity demonstration provider-exhaustion probe.",
                provider="auto",
                provider_executor=deterministic_failure,
                injection_disclosure=INJECTION_DISCLOSURE,
            )
        except RuntimeError as exc:
            routing_error = str(exc)

        after_records = load_jsonl(records_path)
        after_projection = protected_projection(after_records)
        after_digest = sha256_value(after_projection)
        diff = compare_projections(before_projection, after_projection)
        durable_proposal = any(
            record.get("record_id") == proposal["record_id"]
            for record in after_records
        )
        review_decisions = load_jsonl(memory_review_queue.REVIEW_DECISIONS_PATH)
        audit_events = load_jsonl(paths["audit_path"])
        ledger = load_jsonl(paths["decision_path"])
        decision = ledger[-1] if ledger else {}
        routing_decision = {
            "router_mode": decision.get("router_mode"),
            "provider_order": decision.get("provider_order", []),
            "provider_path": decision.get("provider_path", []),
            "provider_failures": [
                {
                    "provider": failure.get("provider"),
                    "error": failure.get("error"),
                    "failover_decision": failure.get("failover_decision"),
                }
                for failure in decision.get("provider_failures", [])
            ],
            "winning_provider": decision.get("winning_provider"),
            "policy_result": decision.get("policy_result"),
            "outcome": decision.get("outcome"),
            "detail": decision.get("detail"),
        }
        provider_attempts = [
            {
                "provider": failure.get("provider"),
                "error": failure.get("error"),
                "deterministic": True,
                "injected": True,
                "disclosure": INJECTION_DISCLOSURE,
            }
            for failure in decision.get("provider_failures", [])
        ]
        expected_events = expected_audit_events(providers)
        observed_events = audit_event_projection(audit_events)

        evidence = {
            "schema_version": SCHEMA_VERSION,
            "project_name": PROJECT_NAME,
            "codex_session_id": session_id,
            "baseline_git_commit": baseline_commit,
            "source_git_commit": source_git_commit,
            "current_branch": branch,
            "run_id": run_id,
            "utc_timestamp": utc_now(),
            "deterministic_fixture": {
                "identity": fixture.get("fixture_id"),
                "digest": hashlib.sha256(fixture_bytes).hexdigest(),
                "record_count": len(fixture_records),
            },
            "protected_scope_definition": protected_scope_definition(),
            "before_projection": before_projection,
            "before_digest": before_digest,
            "after_projection": after_projection,
            "after_digest": after_digest,
            "protected_memory_diff": diff,
            "added": diff["added"],
            "modified": diff["modified"],
            "removed": diff["removed"],
            "proposal_id": proposal["record_id"],
            "proposal_digest": proposal_digest,
            "proposal": proposal,
            "proposal_generation_mode": "deterministic_offline_ai_proposal_fixture",
            "provenance": proposal["provenance"],
            "review_id": review_id,
            "review_status": rejection["review"]["review_status"],
            "review_record": rejection["review"],
            "review_decisions": review_decisions,
            "local_human_attestation": attestation,
            "configured_demo_providers": providers,
            "provider_attempts": provider_attempts,
            "injected_failure_disclosure": INJECTION_DISCLOSURE,
            "routing_error": routing_error,
            "routing_decision": routing_decision,
            "final_outcome": decision.get("outcome"),
            "winning_provider": decision.get("winning_provider"),
            "assistant_output_written": (
                assistant_response is not None
                or paths["assistant_output_path"].exists()
            ),
            "durable_memory_write_from_rejected_proposal": durable_proposal,
            "durable_memory_records_before": before_records,
            "durable_memory_records_after": after_records,
            "expected_audit_events": expected_events,
            "observed_audit_events": observed_events,
            "audit_growth": {"before": 0, "after": len(audit_events)},
            "decision_ledger_growth": {"before": 0, "after": len(ledger)},
            "integrity_doctor": {"status": "PENDING", "checks": []},
            "invariants": {},
            "final_result": "PENDING",
        }

    evidence["invariants"] = calculate_invariants(evidence)
    evidence["final_result"] = final_result(evidence["invariants"])
    return evidence


def render_markdown(evidence: dict[str, Any]) -> str:
    invariants = evidence.get("invariants", {})
    lines = [
        "# Technemachina Integrity Demonstrator Evidence",
        "",
        f"- Result: **{evidence.get('final_result')}**",
        f"- Session: `{evidence.get('codex_session_id')}`",
        f"- Run: `{evidence.get('run_id')}`",
        f"- Baseline: `{evidence.get('baseline_git_commit')}`",
        f"- Branch: `{evidence.get('current_branch')}`",
        "",
        "## Timeline",
        "",
        f"1. Loaded tracked fixture `{evidence.get('deterministic_fixture', {}).get('identity')}`.",
        f"2. Computed protected-memory digest `{evidence.get('before_digest')}`.",
        f"3. Created deterministic offline AI-proposal fixture `{evidence.get('proposal_id')}` with provenance; no live model inference was used.",
        f"4. Recorded `{ATTESTATION_CLASSIFICATION}` in `{evidence.get('local_human_attestation', {}).get('confirmation_mode')}` mode and rejected review `{evidence.get('review_id')}`.",
        "5. Injected disclosed deterministic failures through the provider-executor seam.",
        f"6. Router recorded `{evidence.get('final_outcome')}` with winning provider `{evidence.get('winning_provider')}`.",
        f"7. Protected-memory diff: added={evidence.get('added')}, modified={evidence.get('modified')}, removed={evidence.get('removed')}.",
        f"8. Offline integrity doctor: `{evidence.get('integrity_doctor', {}).get('status')}`.",
        "",
        "## Invariants",
        "",
    ]
    lines.extend(
        f"- {'PASS' if value else 'FAIL'} — `{name}`"
        for name, value in invariants.items()
    )
    lines.extend((
        "",
        "## Authority disclosure",
        "",
        evidence.get("local_human_attestation", {}).get("identity_assurance", ""),
        "",
    ))
    return "\n".join(lines)
