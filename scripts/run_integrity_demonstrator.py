#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DAEMON = ROOT / "daemon"
SCRIPTS = ROOT / "scripts"
FIXTURE = ROOT / "tests" / "fixtures" / "integrity_protected_memory.json"
if str(DAEMON) not in sys.path:
    sys.path.insert(0, str(DAEMON))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import integrity_demonstrator as integrity
import integrity_doctor


def git_value(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def new_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"integrity-{timestamp}-{uuid.uuid4().hex[:8]}"


def ensure_safe_run_dir(run_dir: Path) -> None:
    try:
        run_dir.relative_to(ROOT)
    except ValueError:
        pass
    else:
        raise ValueError("Integrity run directory must be outside the repository.")
    if run_dir.exists() and any(run_dir.iterdir()):
        raise ValueError("Integrity run directory must be new or empty.")


def interactive_attestation(
    *,
    session_id: str,
    run_id: str,
    proposal_digest: str,
    review_id: str,
    actor_label: str,
    input_fn=None,
) -> dict:
    input_fn = input_fn or input
    expected = f"REJECT {review_id}"
    print(f"Proposal digest: {proposal_digest}")
    print("Authority: local human attestation; identity is not authenticated.")
    entered = input_fn(f"Type '{expected}' to reject the proposal: ").strip()
    if entered != expected:
        raise RuntimeError("Explicit rejection confirmation was not provided.")
    return integrity.make_attestation(
        session_id=session_id,
        run_id=run_id,
        proposal_digest=proposal_digest,
        review_id=review_id,
        actor_label=actor_label,
        confirmation_mode="interactive",
    )


def write_evidence(run_dir: Path, evidence: dict) -> tuple[Path, Path]:
    json_path = run_dir / "evidence.json"
    markdown_path = run_dir / "evidence.md"
    json_path.write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(integrity.render_markdown(evidence), encoding="utf-8")
    return json_path, markdown_path


def run_doctor_cli(evidence_path: Path) -> tuple[int, dict]:
    completed = subprocess.run(
        [sys.executable, str(SCRIPTS / "integrity_doctor.py"), str(evidence_path), "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError:
        result = {
            "status": "FAIL",
            "checks": [{
                "name": "doctor_process_output",
                "passed": False,
                "detail": "Offline doctor did not return valid JSON.",
            }],
        }
    return completed.returncode, result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the isolated Technemachina Integrity Demonstrator."
    )
    parser.add_argument(
        "--session-id",
        default="019f7f87-37d5-7ec0-a82c-aca523a76785",
    )
    parser.add_argument("--actor-label", default="Oracle")
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument(
        "--noninteractive-test-only",
        action="store_true",
        help="Explicit test-only attestation mode; never enabled by default.",
    )
    args = parser.parse_args()

    run_id = new_run_id()
    run_dir = args.run_dir or Path(tempfile.mkdtemp(prefix=f"technemachina-{run_id}-"))
    run_dir = run_dir.resolve()
    ensure_safe_run_dir(run_dir)
    source_commit = git_value("rev-parse", "HEAD")
    baseline = integrity.EXPECTED_BASELINE_COMMIT
    branch = git_value("branch", "--show-current") or "(detached)"
    if args.session_id != integrity.EXPECTED_SESSION_ID:
        print("RESULT: FAIL — session ID does not match the qualifying session")
        return 1
    if branch not in (integrity.EXPECTED_BRANCH, "(detached)"):
        print(
            "RESULT: FAIL — expected the qualifying branch or a detached "
            f"clean-clone checkout, found {branch}"
        )
        return 1
    baseline_is_ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", baseline, source_commit],
        cwd=ROOT,
    ).returncode == 0
    if not baseline_is_ancestor:
        print("RESULT: FAIL — the pre-Build-Week baseline is not an ancestor of HEAD")
        return 1

    print("TECHNEMACHINA: INTEGRITY DEMONSTRATOR")
    print(f"Session: {args.session_id}")
    print(f"Run: {run_id}")
    print("Isolation: tracked fixture copied into a fresh run directory")

    def attest(review_id: str, proposal_digest: str, bound_run_id: str) -> dict:
        if args.noninteractive_test_only:
            print("Attestation: explicit noninteractive test-only mode")
            return integrity.make_attestation(
                session_id=args.session_id,
                run_id=bound_run_id,
                proposal_digest=proposal_digest,
                review_id=review_id,
                actor_label=args.actor_label,
                confirmation_mode="noninteractive_test_only",
            )
        return interactive_attestation(
            session_id=args.session_id,
            run_id=bound_run_id,
            proposal_digest=proposal_digest,
            review_id=review_id,
            actor_label=args.actor_label,
        )

    try:
        evidence = integrity.run_demonstration(
            run_dir=run_dir,
            fixture_path=FIXTURE,
            session_id=args.session_id,
            baseline_commit=baseline,
            source_git_commit=source_commit,
            branch=branch,
            run_id=run_id,
            attest=attest,
        )
    except Exception as exc:
        print(f"RESULT: FAIL — {type(exc).__name__}: {exc}")
        return 1

    core_doctor = integrity_doctor.validate_evidence(evidence, require_final=False)
    evidence["integrity_doctor"] = core_doctor
    evidence["invariants"] = integrity.calculate_invariants(evidence)
    evidence["final_result"] = integrity.final_result(evidence["invariants"])
    json_path, markdown_path = write_evidence(run_dir, evidence)

    doctor_code, doctor_result = run_doctor_cli(json_path)
    if doctor_code != 0 or doctor_result.get("status") != "PASS":
        evidence["integrity_doctor"] = doctor_result
        evidence["invariants"] = integrity.calculate_invariants(evidence)
        evidence["final_result"] = "FAIL"
        write_evidence(run_dir, evidence)
        print("Offline integrity doctor: FAIL")
        print(f"Evidence JSON: {json_path}")
        return 1

    evidence["integrity_doctor"] = doctor_result
    evidence["invariants"] = integrity.calculate_invariants(evidence)
    evidence["final_result"] = integrity.final_result(evidence["invariants"])
    json_path, markdown_path = write_evidence(run_dir, evidence)

    final_doctor_code, final_doctor = run_doctor_cli(json_path)
    if final_doctor_code != 0 or final_doctor.get("status") != "PASS":
        evidence["integrity_doctor"] = final_doctor
        evidence["invariants"] = integrity.calculate_invariants(evidence)
        evidence["final_result"] = "FAIL"
        write_evidence(run_dir, evidence)

    print("Timeline:")
    print("  1. Tracked deterministic fixture loaded")
    print(f"  2. Before digest {evidence['before_digest']}")
    print(f"  3. Deterministic offline AI-proposal fixture {evidence['proposal_id']} created")
    print(
        f"  4. Review {evidence['review_id']} rejected; attestation mode: "
        f"{evidence['local_human_attestation']['confirmation_mode']}"
    )
    print(f"  5. Providers attempted: {', '.join(evidence['configured_demo_providers'])}")
    print(f"  6. Routing outcome: {evidence['final_outcome']}; winner: null")
    print(f"  7. Protected diff: +{len(evidence['added'])} ~{len(evidence['modified'])} -{len(evidence['removed'])}")
    print(f"  8. After digest  {evidence['after_digest']}")
    print(f"  9. Offline integrity doctor: {evidence['integrity_doctor']['status']}")
    print(f"Evidence JSON: {json_path}")
    print(f"Evidence Markdown: {markdown_path}")
    print(f"RESULT: {evidence['final_result']}")
    return integrity.exit_code_for_evidence(evidence)


if __name__ == "__main__":
    raise SystemExit(main())
