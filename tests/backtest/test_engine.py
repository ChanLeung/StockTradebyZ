import pandas as pd
import pytest

from backtest.cli import build_parser, load_local_backtest_bundle
from backtest.engine import run_backtest
from pipeline.schemas import Candidate


def test_engine_runs_close_to_next_open_cycle():
    data_bundle = {
        "daily_candidates": {
            "2026-01-06": [
                Candidate(
                    code="600000",
                    date="2026-01-06",
                    strategy="b1",
                    close=10.5,
                    turnover_n=1000.0,
                    buy_review_score=4.5,
                )
            ]
        },
        "next_open_prices": {
            "2026-01-07": {
                "600000": 10.8,
            }
        },
        "stock_to_index": {
            "600000": "HS300",
        },
        "benchmark_returns": pd.DataFrame({"HS300": [0.01]}, index=["2026-01-07"]),
    }

    result = run_backtest({"max_positions": 10}, data_bundle)

    assert len(result.daily_snapshots) == 1
    assert len(result.trades) == 1
    assert result.daily_snapshots[0].date == "2026-01-07"


def test_backtest_cli_parses_quant_plus_ai_mode():
    parser = build_parser()

    args = parser.parse_args(["--mode", "quant_plus_ai"])

    assert args.mode == "quant_plus_ai"


def test_engine_applies_sell_decisions_on_next_open():
    data_bundle = {
        "daily_candidates": {
            "2026-01-06": [
                Candidate(
                    code="600000",
                    date="2026-01-06",
                    strategy="b1",
                    close=10.5,
                    turnover_n=1000.0,
                    buy_review_score=4.5,
                )
            ],
            "2026-01-07": [],
        },
        "next_open_prices": {
            "2026-01-07": {"600000": 10.8},
            "2026-01-08": {"600000": 10.2},
        },
        "sell_decisions": {
            "2026-01-07": {"600000": "sell"},
        },
        "stock_to_index": {"600000": "HS300"},
        "benchmark_returns": pd.DataFrame(
            {"HS300": [0.01, -0.02]},
            index=["2026-01-07", "2026-01-08"],
        ),
    }

    result = run_backtest({"max_positions": 10}, data_bundle)

    assert [trade.side for trade in result.trades] == ["buy", "sell"]
    assert result.daily_snapshots[-1].position_count == 0


def test_engine_blocks_new_positions_when_risk_off():
    data_bundle = {
        "daily_candidates": {
            "2026-01-06": [
                Candidate(
                    code="600000",
                    date="2026-01-06",
                    strategy="b1",
                    close=10.5,
                    turnover_n=1000.0,
                    buy_review_score=4.5,
                )
            ]
        },
        "next_open_prices": {
            "2026-01-07": {"600000": 10.8},
        },
        "risk_signals": {
            "2026-01-06": {"manual_risk_off": True},
        },
        "stock_to_index": {"600000": "HS300"},
        "benchmark_returns": pd.DataFrame({"HS300": [0.01]}, index=["2026-01-07"]),
    }

    result = run_backtest({"max_positions": 10}, data_bundle)

    assert result.trades == []
    assert result.daily_snapshots[0].position_count == 0


def test_load_local_backtest_bundle_uses_candidates_raw_and_review(tmp_path):
    candidates_dir = tmp_path / "data" / "candidates"
    raw_dir = tmp_path / "data" / "raw"
    review_dir = tmp_path / "data" / "review" / "2026-01-06"
    review_sell_dir = tmp_path / "data" / "review_sell" / "2026-01-06"
    benchmark_dir = tmp_path / "data" / "reference" / "benchmarks"
    risk_proxy_dir = tmp_path / "data" / "reference" / "risk_proxies"
    config_dir = tmp_path / "config"
    reference_data_dir = tmp_path / "data" / "reference"

    candidates_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)
    review_dir.mkdir(parents=True)
    review_sell_dir.mkdir(parents=True)
    benchmark_dir.mkdir(parents=True)
    risk_proxy_dir.mkdir(parents=True)
    config_dir.mkdir(parents=True)

    (candidates_dir / "candidates_2026-01-06.json").write_text(
        """{
  "run_date": "2026-01-06",
  "pick_date": "2026-01-06",
  "candidates": [
    {
      "code": "600000",
      "date": "2026-01-06",
      "strategy": "b1",
      "close": 10.5,
      "turnover_n": 1000.0
    }
  ],
  "meta": {}
}""",
        encoding="utf-8",
    )
    (raw_dir / "600000.csv").write_text(
        """date,open,close,high,low,volume
2026-01-06,10.2,10.5,10.6,10.1,1000
2026-01-07,10.8,11.0,11.1,10.7,1100
""",
        encoding="utf-8",
    )
    (review_dir / "600000.json").write_text(
        """{
  "total_score": 4.6,
  "verdict": "PASS",
  "signal_type": "trend_start",
  "comment": "趋势健康。"
}""",
        encoding="utf-8",
    )
    (review_sell_dir / "600000.json").write_text(
        """{
  "decision": "sell",
  "reasoning": "趋势破坏。",
  "risk_flags": ["trend_break"],
  "confidence": 0.9
}""",
        encoding="utf-8",
    )
    (benchmark_dir / "ALLA.csv").write_text(
        """date,close
2026-01-06,100
2026-01-07,110
""",
        encoding="utf-8",
    )
    (risk_proxy_dir / "US_EQ.csv").write_text(
        """date,close
2026-01-05,100
2026-01-06,95
""",
        encoding="utf-8",
    )
    (reference_data_dir / "index_membership.json").write_text(
        """{
  "600000": ["CSI1000", "HS300"]
}""",
        encoding="utf-8",
    )
    (config_dir / "reference_data.yaml").write_text(
        """benchmark_priority:
  - HS300
  - CSI500
  - CSI1000
  - CSI2000
  - ALLA
risk_thresholds:
  a_share_break_lte: -0.02
  macro_move_abs: 0.03
""",
        encoding="utf-8",
    )

    bundle = load_local_backtest_bundle(
        tmp_path,
        start="2026-01-06",
        end="2026-01-07",
        mode="quant_plus_ai",
    )

    candidate = bundle["daily_candidates"]["2026-01-06"][0]
    assert candidate.buy_review_score == 4.6
    assert bundle["next_open_prices"]["2026-01-07"]["600000"] == 10.8
    assert bundle["stock_to_index"]["600000"] == "HS300"
    assert bundle["sell_decisions"]["2026-01-06"]["600000"] == "sell"
    assert bundle["risk_signals"]["2026-01-06"]["macro_risk"] is True
    assert bundle["benchmark_returns"].loc["2026-01-07", "ALLA"] == pytest.approx(0.1)


def test_engine_tracks_cash_after_trade_costs():
    data_bundle = {
        "daily_candidates": {
            "2026-01-06": [
                Candidate(
                    code="600000",
                    date="2026-01-06",
                    strategy="b1",
                    close=10.5,
                    turnover_n=1000.0,
                    buy_review_score=4.5,
                )
            ],
            "2026-01-07": [],
        },
        "next_open_prices": {
            "2026-01-07": {"600000": 10.0},
            "2026-01-08": {"600000": 10.0},
        },
        "sell_decisions": {
            "2026-01-07": {"600000": "sell"},
        },
        "stock_to_index": {"600000": "HS300"},
        "benchmark_returns": pd.DataFrame(
            {"HS300": [0.01, 0.0]},
            index=["2026-01-07", "2026-01-08"],
        ),
    }

    result = run_backtest(
        {
            "max_positions": 10,
            "initial_cash": 100000.0,
            "costs": {"commission_bps": 3, "stamp_duty_bps": 10, "slippage_bps": 2},
        },
        data_bundle,
    )

    assert result.daily_snapshots[0].cash == pytest.approx(98999.5)
    assert result.daily_snapshots[0].equity == pytest.approx(99999.5)
    assert result.daily_snapshots[1].cash == pytest.approx(99998.0)
    assert result.daily_snapshots[1].equity == pytest.approx(99998.0)
