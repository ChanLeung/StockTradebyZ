from types import SimpleNamespace
from pathlib import Path

import pandas as pd
import pytest

from agent.chart_renderer import render_review_chart


class FakeFigure:
    def __init__(self):
        self.layout = SimpleNamespace(
            annotations=[
                SimpleNamespace(text="旧标题1"),
                SimpleNamespace(text="旧标题2"),
            ]
        )
        self.yaxis_updates = []
        self.xaxis_updates = []
        self.write_calls = []

    def update_yaxes(self, **kwargs):
        self.yaxis_updates.append(kwargs)

    def update_xaxes(self, **kwargs):
        self.xaxis_updates.append(kwargs)

    def write_image(self, path, **kwargs):
        self.write_calls.append((path, kwargs))
        Path(path).write_bytes(b"fake-image")


def test_render_chart_uses_cache_key(tmp_path, price_frame, monkeypatch):
    calls = {"count": 0}

    def fake_make_daily_chart(df, code, bars, height):
        calls["count"] += 1
        return FakeFigure()

    monkeypatch.setattr("agent.chart_renderer.make_daily_chart", fake_make_daily_chart)

    path1 = render_review_chart(
        price_frame,
        cache_dir=tmp_path,
        review_type="buy",
        code="600000",
        as_of_date="2026-01-06",
    )
    path2 = render_review_chart(
        price_frame,
        cache_dir=tmp_path,
        review_type="buy",
        code="600000",
        as_of_date="2026-01-06",
    )

    assert path1 == path2
    assert path1.exists()
    assert path1.suffix == ".jpg"
    assert calls["count"] == 1


def test_render_chart_matches_original_daily_chart_elements(tmp_path, price_frame, monkeypatch):
    captured = {}
    figure = FakeFigure()

    enriched = pd.concat(
        [
            price_frame,
            pd.DataFrame(
                {
                    "date": pd.to_datetime(["2026-01-07"]),
                    "open": [11.1],
                    "close": [11.2],
                    "high": [11.3],
                    "low": [10.9],
                    "volume": [1600],
                }
            ),
        ],
        ignore_index=True,
    )

    def fake_make_daily_chart(df, code, bars, height):
        captured["df"] = df.copy()
        captured["code"] = code
        captured["bars"] = bars
        captured["height"] = height
        return figure

    monkeypatch.setattr("agent.chart_renderer.make_daily_chart", fake_make_daily_chart)

    path = render_review_chart(
        enriched,
        cache_dir=tmp_path,
        review_type="buy",
        code="600000",
        as_of_date="2026-01-06",
    )

    assert path.exists()
    assert path.suffix == ".jpg"
    assert captured["code"] == "600000"
    assert captured["bars"] == 120
    assert captured["height"] == 700
    assert captured["df"]["date"].max() == pd.Timestamp("2026-01-06")
    assert len(captured["df"]) == 3

    assert figure.layout.annotations[0].text == "600000 日均线"
    assert figure.layout.annotations[1].text == "成交量"
    assert {"title_text": "股票价格", "row": 1, "col": 1} in figure.yaxis_updates
    assert {"title_text": "成交量", "row": 2, "col": 1} in figure.yaxis_updates
    assert any(
        update.get("title_text") == "日期"
        and update.get("row") == 2
        and update.get("col") == 1
        for update in figure.xaxis_updates
    )

    assert len(figure.write_calls) == 1
    write_path, kwargs = figure.write_calls[0]
    assert write_path == str(path)
    assert kwargs == {"format": "jpg", "width": 1400, "height": 700, "scale": 2}


def test_render_chart_requires_history_on_or_before_as_of_date(tmp_path, price_frame):
    with pytest.raises(ValueError, match="没有可用于评审的历史数据"):
        render_review_chart(
            price_frame,
            cache_dir=tmp_path,
            review_type="buy",
            code="600000",
            as_of_date="2026-01-01",
        )
