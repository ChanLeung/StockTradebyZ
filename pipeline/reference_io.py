from pathlib import Path

import yaml


def load_reference_config(path: str | Path) -> dict:
    config_path = Path(path)
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def pick_primary_index(code: str, mapping: dict[str, list[str]], priority: list[str]) -> str:
    available = mapping.get(code, [])
    for index_name in priority:
        if index_name in available:
            return index_name
    return priority[-1]
