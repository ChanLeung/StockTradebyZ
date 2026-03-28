from pathlib import Path

import pandas as pd

from agent.review_cache import get_cache_path
from dashboard.components.charts import make_daily_chart


_RENDERER_VERSION = "plotly_daily_v2_jpg"
_DEFAULT_BARS = 120


def _prepare_review_frame(df: pd.DataFrame, *, as_of_date: str) -> pd.DataFrame:
    prepared = df.copy()
    prepared["date"] = pd.to_datetime(prepared["date"])
    prepared = prepared.sort_values("date").reset_index(drop=True)
    prepared = prepared[prepared["date"] <= pd.Timestamp(as_of_date)].reset_index(drop=True)
    if prepared.empty:
        raise ValueError(f"没有可用于评审的历史数据（as_of_date={as_of_date}）")
    return prepared


def _apply_review_labels(fig, *, code: str) -> None:
    if getattr(fig.layout, "annotations", None):
        if len(fig.layout.annotations) >= 1:
            fig.layout.annotations[0].text = f"{code} 日均线"
        if len(fig.layout.annotations) >= 2:
            fig.layout.annotations[1].text = "成交量"

    fig.update_yaxes(title_text="股票价格", row=1, col=1)
    fig.update_yaxes(title_text="成交量", row=2, col=1)
    fig.update_xaxes(title_text="日期", showticklabels=True, tickformat="%Y-%m-%d", row=2, col=1)


def render_review_chart(
    df: pd.DataFrame,
    *,
    cache_dir: str | Path,
    review_type: str,
    code: str,
    as_of_date: str,
    width: int = 1400,
    height: int = 700,
) -> Path:
    output_path = get_cache_path(
        cache_dir,
        code,
        as_of_date,
        review_type,
        str(width),
        str(height),
        _RENDERER_VERSION,
        suffix=".jpg",
    )
    if output_path.exists():
        return output_path

    prepared = _prepare_review_frame(df, as_of_date=as_of_date)
    fig = make_daily_chart(prepared, code=code, bars=_DEFAULT_BARS, height=height)
    _apply_review_labels(fig, code=code)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.write_image(str(output_path), format="jpg", width=width, height=height, scale=2)
    return output_path
