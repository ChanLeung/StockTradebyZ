import hashlib
from pathlib import Path


def build_cache_key(*parts: str) -> str:
    normalized = "||".join(str(part) for part in parts)
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def get_cache_path(cache_dir: str | Path, *parts: str, suffix: str = ".png") -> Path:
    target_dir = Path(cache_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir / f"{build_cache_key(*parts)}{suffix}"
