from providers import gemini_provider
from providers import openrouter_provider
from audit_log import write_event
from failover_policy import should_try_next_provider
from decision_ledger import (
    new_decision,
    record_success,
    record_failure,
    record_halt,
    record_all_failed,
)


PROVIDER_ORDER = [
    "openrouter",
    "gemini",
]


def route(prompt: str, provider: str = "auto") -> str:
    """
    Multi-brain router for Technemachina Daemon.

    provider="auto":
        Try providers in PROVIDER_ORDER until one succeeds.

    provider="gemini" or "openrouter":
        Try only that specific provider.

    Restriction-aware doctrine:
        - technical/provider failures trigger automatic fallback
        - uncertain provider refusals may trigger fallback
        - confirmed unsafe requests do not trigger provider-shopping

    Decision Ledger:
        - records provider path
        - records failover decisions
        - records winning provider
        - records final outcome
    """

    normalized_provider = normalize_provider(provider)

    if normalized_provider and normalized_provider != "auto":
        decision = new_decision(
            prompt=prompt,
            router_mode=normalized_provider,
            provider_order=[normalized_provider],
        )

        try:
            response = route_specific(prompt, normalized_provider, decision)
            record_success(decision, normalized_provider, "Specific provider answered successfully.")
            return response
        except Exception as e:
            detail = f"{type(e).__name__}: {e}"
            record_all_failed(decision, detail)
            raise

    decision = new_decision(
        prompt=prompt,
        router_mode="auto",
        provider_order=PROVIDER_ORDER,
    )

    errors = []

    for provider_name in PROVIDER_ORDER:
        try:
            response = route_specific(prompt, provider_name, decision)
            record_success(decision, provider_name, f"{provider_name} answered successfully.")
            return response
        except Exception as e:
            detail = f"{type(e).__name__}: {e}"
            errors.append(f"{provider_name}: {detail}")

            should_continue, reason = should_try_next_provider(prompt, detail)
            record_failure(decision, provider_name, detail, reason)

            write_event(
                event_type="provider_failed",
                status="failure",
                provider=provider_name,
                detail=f"{detail} | failover_decision={reason}",
            )

            if not should_continue:
                write_event(
                    event_type="failover_halted",
                    status="halted",
                    provider=provider_name,
                    detail=reason,
                )
                record_halt(decision, provider_name, reason)

                return (
                    "Technemachina Daemon halted provider failover. "
                    "The request appears to fall outside safe or authorized use, "
                    "so I will not shop across providers for a loophole. "
                    f"Reason: {reason}"
                )

            continue

    failure_detail = " | ".join(errors)

    write_event(
        event_type="all_providers_failed",
        status="failure",
        provider="auto",
        detail=failure_detail,
    )

    record_all_failed(decision, failure_detail)

    return (
        "Technemachina Daemon body is online, but all configured external brains failed. "
        "This is a provider/API issue, not a local project failure. "
        "Failures: " + failure_detail
    )


def route_specific(prompt: str, provider: str, decision=None) -> str:
    normalized = normalize_provider(provider)

    if decision is not None:
        decision.provider_path.append(normalized)

    write_event(
        event_type="provider_attempt",
        status="started",
        provider=normalized,
        detail="Routing prompt to provider.",
    )

    if normalized == "gemini":
        response = gemini_provider.query(prompt)
        write_event(
            event_type="provider_success",
            status="success",
            provider="gemini",
            detail="Gemini answered successfully.",
        )
        return response

    if normalized == "openrouter":
        response = openrouter_provider.query(prompt)
        write_event(
            event_type="provider_success",
            status="success",
            provider="openrouter",
            detail="OpenRouter answered successfully.",
        )
        return response

    raise RuntimeError(f"Unknown provider requested: {provider}")


def normalize_provider(provider: str) -> str:
    if not provider:
        return "auto"

    value = provider.strip().lower()

    aliases = {
        "default": "auto",
        "auto": "auto",
        "cloud": "auto",
        "local": "auto",

        "gemini": "gemini",
        "gemini-2.5-flash": "gemini",
        "google": "gemini",

        "openrouter": "openrouter",
        "qwen": "openrouter",
        "deepseek": "openrouter",

        # Old frontend dropdown values
        "qwen2.5-coder:7b": "auto",
        "deepseek-r1:8b": "auto",

        # OpenAI-style/default frontend values route through auto
        "gpt-4.1-mini": "auto",
        "gpt-4o-mini": "auto",
        "gpt-4o": "auto",
        "openai": "auto",
    }

    return aliases.get(value, value)
