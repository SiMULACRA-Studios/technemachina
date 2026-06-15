from pathlib import Path
import json
from datetime import datetime, timezone

DAEMON_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = DAEMON_DIR.parent
INVENTORY_PATH = DAEMON_DIR / "system_inventory.json"

def scan_inventory() -> dict:
    daemon_files = sorted([
        p.name for p in DAEMON_DIR.glob("*.py")
        if p.is_file()
    ])

    provider_files = []
    providers_dir = DAEMON_DIR / "providers"
    if providers_dir.exists():
        provider_files = sorted([
            p.name for p in providers_dir.glob("*.py")
            if p.is_file()
        ])

    config_files = []
    config_dir = DAEMON_DIR / "config"
    if config_dir.exists():
        config_files = sorted([
            p.name for p in config_dir.iterdir()
            if p.is_file()
        ])

    logs_dir = PROJECT_ROOT / "logs"
    log_files = []
    if logs_dir.exists():
        log_files = sorted([
            p.name for p in logs_dir.iterdir()
            if p.is_file()
        ])

    folders = sorted([
        p.name for p in PROJECT_ROOT.iterdir()
        if p.is_dir()
    ])

    inventory = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "project_root": str(PROJECT_ROOT),
        "daemon_dir": str(DAEMON_DIR),
        "folders": folders,
        "daemon_modules": daemon_files,
        "provider_modules": provider_files,
        "config_files": config_files,
        "log_files": log_files,
        "known_capabilities": [
            "FastAPI backend",
            "Browser frontend",
            "SQLite memory/history",
            "Gemini provider",
            "Brain router",
            "Audit logging",
            "Brain health endpoint",
            "Project context",
            "Context snapshots",
            "Basic risk classifier"
        ]
    }

    return inventory

def save_inventory() -> dict:
    inventory = scan_inventory()
    with open(INVENTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(inventory, f, indent=2)
    return inventory

def get_inventory_summary() -> str:
    inventory = save_inventory()

    return f"""
System Inventory Timestamp: {inventory["timestamp"]}

Daemon Modules:
{", ".join(inventory["daemon_modules"])}

Provider Modules:
{", ".join(inventory["provider_modules"])}

Config Files:
{", ".join(inventory["config_files"]) if inventory["config_files"] else "None"}

Log Files:
{", ".join(inventory["log_files"]) if inventory["log_files"] else "None"}

Known Capabilities:
{", ".join(inventory["known_capabilities"])}
"""
