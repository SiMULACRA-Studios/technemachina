import json
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LEDGER_DIR = Path(__file__).resolve().parent.parent / "logs"
LEDGER_PATH = LEDGER_DIR / "decision_ledger.jsonl"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def prompt_preview(prompt: str, limit: int = 240) -> str:
    text = str(prompt).replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


@dataclass
class DecisionRecord:
    decision_id: str
    timestamp: str
    prompt_preview: str
    router_mode: str
    provider_order: list[str]
    provider_path: list[str] = field(default_factory=list)
    provider_failures: list[dict[str, Any]] = field(default_factory=list)
    winning_provider: str | None = None
    policy_result: str = "not_evaluated"
    outcome: str = "started"
    detail: str = ""


def new_decision(prompt: str, router_mode: str, provider_order: list[str]) -> DecisionRecord:
    return DecisionRecord(
        decision_id=str(uuid.uuid4()),
        timestamp=utc_now(),
        prompt_preview=prompt_preview(prompt),
        router_mode=router_mode,
        provider_order=list(provider_order),
    )


def write_decision(record: DecisionRecord) -> None:
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)

    line = json.dumps(asdict(record), ensure_ascii=False) + "\n"

    with open(LEDGER_PATH, "a+", encoding="utf-8") as f:
        position = f.tell()

        try:
            f.write(line)
        except OSError:
            try:
                f.truncate(position)
            except OSError:
                pass

            raise


def record_success(
    record: DecisionRecord,
    provider: str,
    detail: str = "Provider answered successfully."
) -> None:
    record.winning_provider = provider
    record.outcome = "success"
    record.detail = detail
    write_decision(record)


def record_failure(
    record: DecisionRecord,
    provider: str,
    error: str,
    failover_decision: str
) -> None:
    record.provider_failures.append({
        "provider": provider,
        "error": str(error),
        "failover_decision": failover_decision,
        "timestamp": utc_now(),
    })
    record.policy_result = failover_decision


def record_halt(
    record: DecisionRecord,
    provider: str,
    reason: str
) -> None:
    record.winning_provider = None
    record.outcome = "halted"
    record.detail = f"Failover halted at {provider}: {reason}"
    record.policy_result = reason
    write_decision(record)


def record_all_failed(
    record: DecisionRecord,
    detail: str
) -> None:
    record.winning_provider = None
    record.outcome = "all_failed"
    record.detail = detail
    write_decision(record)
