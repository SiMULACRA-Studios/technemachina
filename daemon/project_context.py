from pathlib import Path
import json
from datetime import datetime, timezone

CONTEXT_PATH = Path(__file__).resolve().parent / "project_context.json"

DEFAULT_CONTEXT = {
    "project_name": "Technemachina Daemon",
    "current_version": "v0.1.7",
    "status": "Brain health monitor online",
    "primary_user": "Crybaby404",
    "user_title": "Oracle",
    "assistant_title": "Master",
    "daemon_role": "Apprentice",
    "active_provider": "gemini",
    "current_objective": "Build stable project awareness and context retention",
    "locked_milestones": [
        "v0.1.5 Brain Online",
        "v0.1.6 Audit Log Online",
        "v0.1.7 Brain Health Monitor Online"
    ],
    "next_modules": [
        "project_context.py",
        "daemon_genome.md",
        "knowledge_ingest.py",
        "patterns.py",
        "sandbox/"
    ],
    "doctrine": [
        "The Apprentice may evolve.",
        "The Oracle must authorize evolution.",
        "The Master maintains doctrine and guides architecture.",
        "The Daemon may propose improvements but may not execute privileged changes without approval."
    ],
    "last_updated": None
}

def init_context() -> dict:
    if not CONTEXT_PATH.exists():
        context = DEFAULT_CONTEXT.copy()
        context["last_updated"] = datetime.now(timezone.utc).isoformat()
        save_context(context)
        return context

    return load_context()

def load_context() -> dict:
    with open(CONTEXT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_context(context: dict) -> None:
    context["last_updated"] = datetime.now(timezone.utc).isoformat()
    with open(CONTEXT_PATH, "w", encoding="utf-8") as f:
        json.dump(context, f, indent=2)

def get_context_summary() -> str:
    context = init_context()

    system_inventory = context.get("system_inventory", {})

    return f"""
Project: {context.get("project_name")}
Version: {context.get("current_version")}
Status: {context.get("status")}
Primary User: {context.get("primary_user")} / {context.get("user_title")}
Assistant Role: {context.get("assistant_title")}
Daemon Role: {context.get("daemon_role")}
Active Provider: {context.get("active_provider")}
Current Objective: {context.get("current_objective")}
Locked Milestones: {", ".join(context.get("locked_milestones", []))}
Next Modules: {", ".join(context.get("next_modules", []))}
Daemon Modules: {", ".join(system_inventory.get("daemon_modules", []))}
Provider Modules: {", ".join(system_inventory.get("provider_modules", []))}
Config Files: {", ".join(system_inventory.get("config_files", [])) if system_inventory.get("config_files") else "None"}
Log Files: {", ".join(system_inventory.get("log_files", [])) if system_inventory.get("log_files") else "None"}
Known Capabilities: {", ".join(system_inventory.get("known_capabilities", []))}
Doctrine: {" | ".join(context.get("doctrine", []))}
"""

def save_context_snapshot(label: str = "snapshot") -> str:
    """
    Save a dated snapshot of the current project context.
    This helps Technemachina Daemon preserve its own development state over time.
    """
    from datetime import datetime, timezone

    context = init_context()

    snapshot_dir = Path(__file__).resolve().parent.parent / "logs" / "context_snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_label = label.replace(" ", "_").replace("/", "_")
    snapshot_path = snapshot_dir / f"context_{safe_label}_{timestamp}.json"

    with open(snapshot_path, "w", encoding="utf-8") as f:
        json.dump(context, f, indent=2)

    return str(snapshot_path)
