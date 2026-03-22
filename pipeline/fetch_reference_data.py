from pathlib import Path

import pandas as pd


def load_reference_series(data_dir: str | Path) -> dict[str, pd.DataFrame]:
    root = Path(data_dir)
    return {
        "benchmarks": _load_series_dir(root / "benchmarks"),
        "risk_proxies": _load_series_dir(root / "risk_proxies"),
    }


def _load_series_dir(directory: Path) -> pd.DataFrame:
    if not directory.exists():
        return pd.DataFrame()

    frames: list[pd.Series] = []
    for csv_path in sorted(directory.glob("*.csv")):
        frame = pd.read_csv(csv_path)
        if "date" not in frame.columns:
            continue

        frame["date"] = frame["date"].astype(str)
        if "return" in frame.columns:
            series = frame.set_index("date")["return"].astype(float)
        elif "pct_chg" in frame.columns:
            series = frame.set_index("date")["pct_chg"].astype(float) / 100.0
        elif "close" in frame.columns:
            close = frame.set_index("date")["close"].astype(float)
            series = close.pct_change()
        else:
            continue

        series = series.dropna()
        if series.empty:
            continue
        series.name = csv_path.stem
        frames.append(series)

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, axis=1).sort_index()
