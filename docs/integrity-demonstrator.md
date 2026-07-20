# Technemachina Integrity Demonstrator

The Integrity Demonstrator is a fail-closed, offline proof that a rejected
AI-originated permanent-memory proposal does not change protected memory even
when every configured demonstration provider fails.

It is scoped to Build Week evidence. It does not claim cryptographic owner
authentication, replace the application Synapse doctor, or operate on living
user state.

## Build Week scope

The existing Technemachina daemon, governed-memory review/rejection functions,
provider router, audit log, and decision ledger are the pre-Build-Week
foundation reused by this demonstration. OpenAI Build Week added the isolated
runner, canonical protected-state proof, narrow disclosed provider-executor
seam, offline doctor, deterministic fixture, evidence formats, documentation,
and focused tests. This submission does not claim that the broad Technemachina
Daemon was built during Build Week.

## One-command demonstration

After installing the repository's declared daemon dependencies, run
from the repository root:

```bash
python3 scripts/run_integrity_demonstrator.py
```

The default is interactive. The runner displays the proposal digest and review
ID, discloses the authority limitation, and requires the operator to type the
exact `REJECT <review-id>` challenge. An absent or mismatched response fails the
run.

Automated tests may use the explicit nondefault mode:

```bash
python3 scripts/run_integrity_demonstrator.py --noninteractive-test-only
```

Evidence created through that flag records
`confirmation_mode: noninteractive_test_only`. It must not be represented as an
interactive confirmation.

The command creates a fresh temporary run directory and prints the exact paths
to `evidence.json` and `evidence.md`. It returns zero only for PASS.
An explicitly supplied `--run-dir` must be outside the repository and new or
empty.

The runner requires the qualifying Build Week branch in a normal working tree.
For clean-clone verification it also accepts an exact detached-HEAD checkout
and records `current_branch` as `(detached)` rather than claiming a branch is
checked out.

## Isolation boundary

The runner reads only the tracked fixture
`tests/fixtures/integrity_protected_memory.json`, repository Git identity, and
tracked source code. It redirects the authentic memory-review, audit, and
decision-ledger module paths into the new run directory before performing any
operation.

It does not import the FastAPI application and does not read or mutate:

- existing `logs/memory` or review queues;
- parent-directory Synapse sources;
- `daemon/database.db`;
- `.env` or provider credentials;
- ignored private runtime or living user state.

## Protected-memory contract

The protected projection includes these layers:

- `alpha`
- `theta`
- `delta`

It includes these record types:

- `project_fact`
- `decision`
- `procedure`
- `research_note`
- `external_reference`
- `risk_note`
- `doctrine_note`

Records are ordered by `record_id`. Dictionaries use lexicographically sorted
keys. JSON uses UTF-8 and compact `,` and `:` separators. No record field is
excluded or normalized as volatile. The projection is committed with SHA-256.
Added, modified, and removed record IDs are calculated independently.

Audit and decision ledgers are outside the protected projection and are
expected to grow with legitimate routing and rejection evidence.

## Governance and authority

The proposal is passed through the real `create_review_item` and
`reject_review` functions against isolated paths. Its provenance identifies it
as an AI proposal bound to the Codex session. The proposal payload is generated
deterministically from tracked demonstration code; the offline run does not
claim or perform live model inference.

The rejection evidence is classified exactly as:

```text
local_human_attestation
```

It binds the Codex session ID, run ID, proposal digest, review ID, reject
action, attested actor label, timestamp, and confirmation mode. This is a local
human attestation only. It is not authenticated identity, a digital signature,
or cryptographic proof of who the person is.

## Deterministic provider failure

`brain_router.route` has an optional keyword-only `provider_executor` seam.
Normal production calls omit it and behave exactly as before. Use of the seam
requires a nonempty disclosure string.

The demonstrator explicitly supplies an executor that raises a deterministic
503 error for each configured provider. Every failure and provider-attempt
audit detail identifies the injection seam and states that network access is
false. The real router still performs failover and writes the terminal
`all_failed` decision with a null winner.

The runner calls the router directly rather than `ai.query_model`, so it neither
creates chat history nor fabricates an assistant response.

## Offline validation

Validate an evidence artifact independently with:

```bash
python3 scripts/integrity_doctor.py /path/to/evidence.json
```

The doctor requires no servers, browser, ports, provider keys, private data, or
living state. It recomputes projection and proposal digests, record-ID diffs,
the tracked-fixture digest and projection, full isolated durable-store equality,
attestation bindings, rejection evidence, the safe routing-decision projection,
provider exhaustion, audit statuses/disclosures, ledger growth, qualifying
session/baseline bindings, invariant results, and final status. A missing,
inconsistent, malformed, or tampered field returns nonzero.

## Test commands

The test commands additionally require `tests/requirements.txt`.

```bash
python3 -m pytest -q tests/test_integrity_demonstrator.py
python3 -m pytest -q tests/test_memory_governance_lifecycle.py
python3 -m pytest -q tests/test_provider_failure_boundaries.py
python3 -m pytest -q tests/test_ledger_write_failure_boundary.py
```

Generated evidence remains in its explicitly printed temporary directory and
is not a replacement for a reviewed release artifact.

Repeated isolated runs have the same fixture, protected projection, digests,
proposal, provider order, failure disclosures, audit-event projection,
invariants, doctor result, and final result. The documented per-run metadata is
the run ID and UTC timestamp; review/decision IDs and timestamps; and the
attestation fields bound to those run-specific values.
