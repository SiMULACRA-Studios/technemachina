"""Minimal local .env loader for Technemachina.

Loads simple KEY=VALUE entries without overriding variables that are already
present in the process environment.
"""

from __future__ import annotations

import os
from pathlib import Path


def load_project_env(project_root: Path) -> list[str]:
    env_path = project_root / ".env"

    if not env_path.exists():
        return []

    loaded: list[str] = []

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip()

        if not name:
            continue

        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in {"'", '"'}
        ):
            value = value[1:-1]

        if name not in os.environ:
            os.environ[name] = value
            loaded.append(name)

    return loaded
