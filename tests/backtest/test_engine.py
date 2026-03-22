import pandas as pd
import pytest

from backtest.cli import build_parser, load_local_backtest_bundle, main as cli_main
from backtest.engine import run_backtest
from pipeline.schemas import Candidate
from trading.holdings_io import load_holdings_snapshot


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


def test_backtest_cli_writes_daily_snapshots_file(tmp_path):
    output_dir = tmp_path / "out"

    cli_main(
        [
            "--mode",
            "quant_only",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-05",
            "--output-dir",
            str(output_dir),
        ]
    )

    snapshot_path = output_dir / "quant_only" / "2026-01-01_2026-01-05" / "daily_snapshots.json"
    assert snapshot_path.exists()


def test_backtest_cli_writes_holdings_snapshot_file(tmp_path):
    output_dir = tmp_path / "out"

    cli_main(
        [
            "--mode",
            "quant_only",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-05",
            "--output-dir",
            str(output_dir),
        ]
    )

    holdings_path = output_dir / "quant_only" / "2026-01-01_2026-01-05" / "holdings_snapshot.json"
    assert holdings_path.exists()

    snapshot = load_holdings_snapshot(holdings_path)
    assert snapshot["as_of_date"] == "2026-01-05"
    assert snapshot["state"].cash >= 0.0


def test_backtest_cli_writes_signal_sheet_csv_file(tmp_path):
    output_dir = tmp_path / "out"

    cli_main(
        [
            "--mode",
            "quant_only",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-05",
            "--output-dir",
            str(output_dir),
        ]
    )

    csv_path = output_dir / "quant_only" / "2026-01-01_2026-01-05" / "signal_sheet_actions.csv"
    assert csv_path.exists()

    content = csv_path.read_text(encoding="utf-8")
    assert "signal_date,trade_date,risk_mode,code,action,instruction" in content


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
    assert bundle["signal_close_prices"]["2026-01-06"]["600000"] == 10.5
    assert bundle["stock_to_index"]["600000"] == "HS300"
    assert bundle["sell_decisions"]["2026-01-06"]["600000"] == "sell"
    assert bundle["sell_reviews"]["2026-01-06"]["600000"]["reasoning"] == "趋势破坏。"
    assert bundle["sell_reviews"]["2026-01-06"]["600000"]["risk_flags"] == ["trend_break"]
    assert bundle["risk_signals"]["2026-01-06"]["macro_risk"] is True
    assert bundle["benchmark_returns"].loc["2026-01-07", "ALLA"] == pytest.approx(0.1)


def test_load_local_backtest_bundle_keeps_open_prices_for_tracked_holdings(tmp_path):
    candidates_dir = tmp_path / "data" / "candidates"
    raw_dir = tmp_path / "data" / "raw"
    config_dir = tmp_path / "config"

    candidates_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)
    config_dir.mkdir(parents=True)

    (candidates_dir / "candidates_2026-01-06.json").write_text(
        """{
  "run_date": "2026-01-06",
  "pick_date": "2026-01-06",
  "candidates": [{"code": "600000", "date": "2026-01-06", "strategy": "b1", "close": 10.5, "turnover_n": 1000.0}],
  "meta": {}
}""",
        encoding="utf-8",
    )
    (candidates_dir / "candidates_2026-01-07.json").write_text(
        """{
  "run_date": "2026-01-07",
  "pick_date": "2026-01-07",
  "candidates": [{"code": "000001", "date": "2026-01-07", "strategy": "b1", "close": 9.5, "turnover_n": 900.0}],
  "meta": {}
}""",
        encoding="utf-8",
    )
    (raw_dir / "600000.csv").write_text(
        """date,open,close,high,low,volume
2026-01-06,10.2,10.5,10.6,10.1,1000
2026-01-07,10.8,11.0,11.1,10.7,1100
2026-01-08,11.1,11.2,11.3,11.0,1000
""",
        encoding="utf-8",
    )
    (raw_dir / "000001.csv").write_text(
        """date,open,close,high,low,volume
2026-01-07,9.2,9.5,9.6,9.1,900
2026-01-08,9.6,9.7,9.8,9.5,950
""",
        encoding="utf-8",
    )
    (config_dir / "reference_data.yaml").write_text(
        """benchmark_priority:
  - HS300
  - CSI500
  - CSI1000
  - CSI2000
  - ALLA
""",
        encoding="utf-8",
    )

    bundle = load_local_backtest_bundle(
        tmp_path,
        start="2026-01-06",
        end="2026-01-07",
        mode="quant_only",
    )

    assert bundle["next_open_prices"]["2026-01-08"]["600000"] == 11.1
    assert bundle["next_open_prices"]["2026-01-08"]["000001"] == 9.6
    assert bundle["signal_close_prices"]["2026-01-07"]["600000"] == 11.0
    assert bundle["signal_close_prices"]["2026-01-07"]["000001"] == 9.5


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


def test_engine_reduces_positions_when_risk_off_exposure_drops():
    data_bundle = {
        "daily_candidates": {
            "2026-01-06": [
                Candidate(code=f"{600000 + idx}", date="2026-01-06", strategy="b1", close=10.0 + idx, turnover_n=1000.0, buy_review_score=5.0 - idx * 0.1)
                for idx in range(4)
            ],
            "2026-01-07": [
                Candidate(code=f"{600000 + idx}", date="2026-01-07", strategy="b1", close=10.0 + idx, turnover_n=1000.0, buy_review_score=5.0 - idx * 0.1)
                for idx in range(4)
            ],
        },
        "next_open_prices": {
            "2026-01-07": {f"{600000 + idx}": 10.0 + idx for idx in range(4)},
            "2026-01-08": {f"{600000 + idx}": 10.2 + idx for idx in range(4)},
        },
        "risk_signals": {
            "2026-01-07": {"manual_risk_off": True},
        },
        "stock_to_index": {f"{600000 + idx}": "HS300" for idx in range(4)},
        "benchmark_returns": pd.DataFrame(
            {"HS300": [0.01, 0.0]},
            index=["2026-01-07", "2026-01-08"],
        ),
    }

    result = run_backtest({"max_positions": 4}, data_bundle)

    assert [trade.side for trade in result.trades].count("buy") == 4
    assert [trade.side for trade in result.trades].count("sell") == 2
    assert result.daily_snapshots[-1].position_count == 2
