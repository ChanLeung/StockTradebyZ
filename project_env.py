from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"


def load_project_env(env_path: str | Path | None = None, *, override: bool = False) -> Path | None:
    path = Path(env_path) if env_path is not None else DEFAULT_ENV_PATH
    if not path.exists():
        return None

    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key.startswith("#"):
            continue

        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        if override or not os.environ.get(key):
            os.environ[key] = value

    return path
