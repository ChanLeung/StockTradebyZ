from pathlib import Path

import pandas as pd


def load_reference_series(data_dir: str | Path) -> dict[str, pd.DataFrame]:
    _ = Path(data_dir)
    return {
        "benchmarks": pd.DataFrame(),
        "risk_proxies": pd.DataFrame(),
    }
