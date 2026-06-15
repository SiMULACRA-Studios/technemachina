import os
from google import genai
from project_context import get_context_summary
from genome import get_genome_summary

SYSTEM_PROMPT = """
You are Technemachina Daemon, the local engineering Apprentice of Crybaby404 / Oracle.

You are powered by an external model provider, but you speak as the Daemon interface, not as Google or Gemini.

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

def get_client():
    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set in this terminal session.")

    return genai.Client(api_key=api_key)

def query(prompt: str) -> str:
    contents = (
        f"{SYSTEM_PROMPT}\n\n"
        f"Daemon Genome:\n{get_genome_summary()}\n\n"
        f"Runtime Brain Provider: gemini\n\n"
        f"Current Project Context:\n{get_context_summary()}\n\n"
        f"Important: If asked what brain/provider you are using right now, answer from the Runtime Brain Provider above.\n\n"
        f"User prompt:\n{prompt}"
    )

    models_to_try = [
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
    ]

    last_error = None

    for model_name in models_to_try:
        try:
            client = get_client()
            response = client.models.generate_content(
                model=model_name,
                contents=contents
            )
            return response.text
        except Exception as e:
            last_error = e
            continue

    return (
        "Technemachina Daemon body is online, but the external Gemini brain is temporarily unavailable. "
        "This is a provider/API issue, not a local project failure. "
        f"Last provider error: {type(last_error).__name__}: {last_error}"
    )
