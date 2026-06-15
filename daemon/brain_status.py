import os
from datetime import datetime, timezone

from brain_router import PROVIDER_ORDER


def provider_light(name: str, enabled: bool, detail: str = "") -> dict:
    return {
        "provider": name,
        "light": "green" if enabled else "red",
        "enabled": enabled,
        "detail": detail,
    }


def get_brain_status() -> dict:
    gemini_key = bool(os.environ.get("GEMINI_API_KEY"))
    openrouter_key = bool(os.environ.get("OPENROUTER_API_KEY"))
    perplexity_key = bool(os.environ.get("PERPLEXITY_API_KEY"))
    groq_key = bool(os.environ.get("GROQ_API_KEY"))
    openai_key = bool(os.environ.get("OPENAI_API_KEY"))

    providers = [
        provider_light(
            "gemini",
            gemini_key,
            "GEMINI_API_KEY detected" if gemini_key else "GEMINI_API_KEY missing",
        ),
        provider_light(
            "openrouter",
            openrouter_key,
            "OPENROUTER_API_KEY detected" if openrouter_key else "OPENROUTER_API_KEY missing",
        ),
        provider_light(
            "perplexity",
            perplexity_key,
            "PERPLEXITY_API_KEY detected but research brain not integrated yet" if perplexity_key else "PERPLEXITY_API_KEY missing / research brain not integrated yet",
        ),
        provider_light(
            "groq",
            groq_key,
            "GROQ_API_KEY detected but provider not integrated yet" if groq_key else "GROQ_API_KEY missing / provider not integrated yet",
        ),
        provider_light(
            "openai",
            openai_key,
            "OPENAI_API_KEY detected but provider disabled until funded/enabled" if openai_key else "OPENAI_API_KEY missing / disabled until funded",
        ),
        provider_light(
            "local",
            False,
            "Local model provider not installed/enabled yet",
        ),
    ]

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "router_order": PROVIDER_ORDER,
        "providers": providers,
        "legend": {
            "green": "enabled / configured",
            "red": "disabled / missing / unavailable",
        },
    }
