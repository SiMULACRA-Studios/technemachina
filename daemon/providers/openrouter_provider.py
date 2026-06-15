import os
import json
import urllib.request
import urllib.error

from project_context import get_context_summary
from genome import get_genome_summary

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

SYSTEM_PROMPT = """
You are Technemachina Daemon, the local engineering Apprentice of Crybaby404 / Oracle.

You are being routed through OpenRouter as a fallback brain.
You speak as Technemachina Daemon, not as OpenRouter or the underlying model.

Your purpose:
- teach coding
- explain systems
- debug errors
- compare technologies
- help build practical engineering projects
- suggest safe improvements to this local Daemon wrapper

Behavior rules:
- Be direct.
- Give practical answers.
- Prioritize working code.
- When asked for code, provide usable draft code.
- You may suggest patches to your own local files.
- You may not execute commands, install packages, delete files, or apply patches yourself.
- If a patch changes the Daemon, label it as a draft patch.
- Do not ask for extra authorization just to suggest code.
- Approval is required before the user runs or applies a patch.
- Do not claim you update your own model weights.
- Explain that local capabilities improve through files, modules, logs, context, approved code changes, and future knowledge systems.
"""

DEFAULT_MODELS = [
    "qwen/qwen-2.5-coder:free",
    "deepseek/deepseek-r1:free",
    "openrouter/free",
]


def get_api_key() -> str:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set in this terminal session.")
    return api_key


def get_model_list() -> list[str]:
    raw = os.environ.get("OPENROUTER_MODELS")
    if not raw:
        return DEFAULT_MODELS

    models = [m.strip() for m in raw.split(",") if m.strip()]
    return models or DEFAULT_MODELS


def call_openrouter(model_name: str, prompt: str) -> str:
    api_key = get_api_key()

    full_prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"Daemon Genome:\n{get_genome_summary()}\n\n"
        f"Runtime Brain Provider: openrouter\n"
        f"Runtime Provider Model: {model_name}\n\n"
        f"Current Project Context:\n{get_context_summary()}\n\n"
        f"Important: If asked what brain/provider you are using right now, answer from the Runtime Brain Provider above, not from the stored project context.\n\n"
        f"User prompt:\n{prompt}"
    )

    payload = {
        "model": model_name,
        "messages": [
            {
                "role": "user",
                "content": full_prompt,
            }
        ],
        "temperature": 0.3,
    }

    data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        OPENROUTER_URL,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://127.0.0.1:8000",
            "X-OpenRouter-Title": "Technemachina Daemon",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            raw_body = response.read().decode("utf-8")
            parsed = json.loads(raw_body)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenRouter HTTP {e.code}: {error_body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"OpenRouter network error: {e}") from e
    except json.JSONDecodeError as e:
        raise RuntimeError(f"OpenRouter returned invalid JSON: {e}") from e

    if "error" in parsed:
        message = parsed["error"].get("message", parsed["error"])
        code = parsed["error"].get("code", "unknown")
        raise RuntimeError(f"OpenRouter nested error {code}: {message}")

    try:
        content = parsed["choices"][0]["message"]["content"]
    except Exception as e:
        raise RuntimeError(f"OpenRouter response missing content: {parsed}") from e

    if not content or not str(content).strip():
        raise RuntimeError("OpenRouter returned empty content.")

    return str(content).strip()


def query(prompt: str) -> str:
    errors = []

    for model_name in get_model_list():
        try:
            return call_openrouter(model_name, prompt)
        except Exception as e:
            errors.append(f"{model_name}: {type(e).__name__}: {e}")
            continue

    raise RuntimeError("All OpenRouter models failed. " + " | ".join(errors))
