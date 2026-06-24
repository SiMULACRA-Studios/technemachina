# Technemachina Daemon Security / Governance Map

Version: v0.2.6 Draft  
Project Version Anchored: v0.2.5 — Decision Ledger Online  
Status: Documentation / Research Governance Milestone  
Primary User: Crybaby404 / Oracle  
Assistant Role: Master  
Daemon Role: Apprentice  

---

## v0.2.5 — Decision Ledger (MILESTONE COMPLETE)

State: ONLINE  
Status: LOCKED AND BACKED UP

Confirmed:

- `decision_ledger.py` exists and is functional.
- `decision_ledger.jsonl` exists and is append-only.
- Provider path recording works.
- Failover reason recording works.
- Winning provider recording works.
- Policy result recording works.
- Project context updated.
- v0.2.5 backup created and verified.

The Daemon now records decision traces, not just events. Every routed request is now inspectable, replayable, and tied to a formal audit record.

This is the first major architectural artifact of Technemachina Daemon.

---

# 1. Purpose

This document maps Technemachina Daemon to recognized security and AI governance frameworks.

The goal is not to claim full compliance. The goal is to create a clear, defensible baseline that shows how the system is being designed toward secure, observable, auditable, and human-authorized operation.

Frameworks used:

1. OWASP ASVS 5.0.0 — application security baseline.
2. CIS Critical Security Controls — operational hygiene, logging, inventory, and monitoring.
3. NIST AI RMF 1.0 — AI governance, risk mapping, measurement, and management.

---

# 2. Project Thesis

Technemachina Daemon is a local-first, stateful AI orchestration system for development and research workflows, designed to make multi-provider model routing, failover decisions, memory use, safety policy, and privacy-aware research modes visible, auditable, and human-authorized.

External description:

Technemachina Daemon is a local-first AI orchestration and observability platform.

Internal description:

Technemachina Daemon is a multi-brain engineering Apprentice that routes, remembers, logs, and explains itself under Oracle authorization.

---

# 3. Current Architecture

Current version:

`v0.2.5 — Decision Ledger Online`

Core modules:

- `app.py`
- `brain_router.py`
- `decision_ledger.py`
- `audit_log.py`
- `failover_policy.py`
- `brain_status.py`
- `inventory.py`
- `project_context.py`
- `genome.py`
- `memory.py`
- `monitor.py`
- `risk.py`
- `tools.py`

Provider modules:

- `providers/gemini_provider.py`
- `providers/openrouter_provider.py`

Configuration:

- `config/daemon_genome.md`

Logs:

- `logs/audit_log.jsonl`
- `logs/decision_ledger.jsonl`

Current provider order:

```text
auto: openrouter -> gemini
