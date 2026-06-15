from memory import save_message
from brain_router import route
from audit_log import write_event


def normalize_provider(model_name: str) -> str:
    incoming = (model_name or "").lower().strip()

    # Old frontend dropdown values should use router auto mode.
    # Auto mode can fail over between configured providers.
    if incoming in {
        "",
        "default",
        "auto",
        "cloud",
        "local",
        "qwen2.5-coder:7b",
        "deepseek-r1:8b",
        "gpt-4.1-mini",
        "gpt-4o-mini",
        "gpt-4o",
        "openai",
    }:
        return "auto"

    if incoming in {"gemini", "gemini-2.5-flash", "google"}:
        return "gemini"

    if incoming in {"openrouter", "qwen", "deepseek"}:
        return "openrouter"

    return "auto"


def query_model(prompt: str, model_name: str = "auto") -> str:
    provider = normalize_provider(model_name)

    if not prompt.strip():
        write_event("chat", "failed", provider=provider, detail="empty prompt")
        raise ValueError("Prompt cannot be empty.")

    save_message("user", prompt)

    try:
        answer = route(prompt, provider=provider)
        save_message("assistant", answer)
        write_event("chat", "success", provider=provider)
        return answer
    except Exception as e:
        write_event("chat", "failed", provider=provider, detail=str(e))
        raise
