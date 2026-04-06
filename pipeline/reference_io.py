import json
from pathlib import Path
import csv

import yaml


def load_reference_config(path: str | Path) -> dict:
    config_path = Path(path)
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_index_membership(path: str | Path) -> dict[str, list[str]]:
    snapshot_path = Path(path)
    if not snapshot_path.exists():
        return {}

    if snapshot_path.suffix.lower() == ".json":
        return json.loads(snapshot_path.read_text(encoding="utf-8"))

    with open(snapshot_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_stock_industry(path: str | Path) -> dict[str, str]:
    stocklist_path = Path(path)
    if not stocklist_path.exists():
        return {}

    mapping: dict[str, str] = {}
    with open(stocklist_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = str(row.get("symbol", "")).strip()
            industry = str(row.get("industry", "")).strip()
            if code and industry:
                mapping[code] = industry
    return mapping


def pick_primary_index(code: str, mapping: dict[str, list[str]], priority: list[str]) -> str:
    available = mapping.get(code, [])
    for index_name in priority:
        if index_name in available:
            return index_name
    return priority[-1]
