from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_REVIEW_CONFIG: dict[str, Any] = {
    "candidates": "data/candidates/candidates_latest.json",
    "kline_dir": "data/kline",
    "output_dir": "data/review",
    "prompt_path": "agent/prompts/buy_prompt.md",
    "request_delay": 5,
    "skip_existing": False,
    "suggest_min_score": 4.0,
}

BUY_REVIEW_CONFIG_PATH = _ROOT / "config" / "buy_review.yaml"
LEGACY_BUY_REVIEW_CONFIG_PATH = _ROOT / "config" / "gemini_review.yaml"
SELL_REVIEW_CONFIG_PATH = _ROOT / "config" / "sell_review.yaml"
LEGACY_SELL_REVIEW_CONFIG_PATH = _ROOT / "config" / "gemini_sell_review.yaml"


def _resolve_cfg_path(path_like: str | Path, base_dir: Path = _ROOT) -> Path:
    path = Path(path_like)
    return path if path.is_absolute() else (base_dir / path)


def load_review_config(
    config_path: Path,
    *,
    prompt_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    default_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not config_path.exists():
        raise FileNotFoundError(f"找不到配置文件：{config_path}")

    with open(config_path, "r", encoding="utf-8") as file:
        raw = yaml.safe_load(file) or {}

    config = {
        **DEFAULT_REVIEW_CONFIG,
        **(default_overrides or {}),
        **raw,
    }
    if prompt_path is not None:
        config["prompt_path"] = str(prompt_path)
    if output_dir is not None:
        config["output_dir"] = str(output_dir)

    config["candidates"] = _resolve_cfg_path(config["candidates"])
    config["kline_dir"] = _resolve_cfg_path(config["kline_dir"])
    config["output_dir"] = _resolve_cfg_path(config["output_dir"])
    config["prompt_path"] = _resolve_cfg_path(config["prompt_path"])
    return config
