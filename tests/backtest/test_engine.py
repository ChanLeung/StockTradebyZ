import json

import pandas as pd
import pytest

import backtest.cli as backtest_cli
from backtest.cli import build_backtest_bundle, build_parser, load_backtest_config, load_local_backtest_bundle, main as cli_main
from backtest.engine import run_backtest
from backtest.reporting import build_signal_sheet
from pipeline.schemas import Candidate
from trading.holdings_io import load_holdings_snapshot, save_holdings_snapshot
from trading.schemas import PortfolioState, Position


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


def test_backtest_cli_defaults_to_quant_plus_ai_mode():
    parser = build_parser()

    args = parser.parse_args([])

    assert args.mode == "quant_plus_ai"


def test_backtest_cli_help_marks_quant_only_as_debug_mode():
    parser = build_parser()

    help_text = parser.format_help()

    assert "quant_only" in help_text
    assert "仅内部调试" in help_text


def test_backtest_cli_parses_initial_holdings_path():
    parser = build_parser()

    args = parser.parse_args(["--initial-holdings", "data/backtest/holdings_snapshot.json"])

    assert args.initial_holdings == "data/backtest/holdings_snapshot.json"


def test_engine_uses_initial_state_for_signal_holdings_and_sell_decisions():
    data_bundle = {
        "initial_state": PortfolioState(
            cash=5000.0,
            positions=[
                Position(
                    code="600000",
                    entry_date="2026-01-02",
                    entry_price=10.0,
                    weight=1.0,
                    quantity=100,
                )
            ],
        ),
        "daily_candidates": {"2026-01-06": []},
        "next_open_prices": {"2026-01-07": {"600000": 11.0}},
        "signal_close_prices": {"2026-01-06": {"600000": 10.5}},
        "sell_decisions": {"2026-01-06": {"600000": "sell"}},
        "stock_to_index": {"600000": "HS300"},
        "benchmark_returns": pd.DataFrame({"HS300": [0.0]}, index=["2026-01-07"]),
    }

    result = run_backtest(
        {
            "max_positions": 10,
            "costs": {"commission_bps": 0, "stamp_duty_bps": 0, "slippage_bps": 0},
        },
        data_bundle,
    )
    signal_sheet = build_signal_sheet(result)

    assert result.initial_cash == pytest.approx(6000.0)
    assert signal_sheet["current_holdings"][0]["code"] == "600000"
    assert signal_sheet["sell_orders"][0]["code"] == "600000"
    assert [trade.side for trade in result.trades] == ["sell"]
    assert result.final_state.positions == []


def test_backtest_cli_initial_holdings_populates_signal_sheet(tmp_path, monkeypatch):
    output_dir = tmp_path / "out"
    holdings_path = tmp_path / "holdings_snapshot.json"
    save_holdings_snapshot(
        holdings_path,
        as_of_date="2026-01-06",
        state=PortfolioState(
            cash=5000.0,
            positions=[
                Position(
                    code="600000",
                    entry_date="2026-01-02",
                    entry_price=10.0,
                    weight=1.0,
                    quantity=100,
                )
            ],
        ),
    )

    def fake_build_backtest_bundle(*args, **kwargs):
        return {
            "daily_candidates": {"2026-01-06": []},
            "next_open_prices": {"2026-01-07": {"600000": 11.0}},
            "signal_close_prices": {"2026-01-06": {"600000": 10.5}},
            "stock_to_index": {"600000": "HS300"},
            "benchmark_returns": pd.DataFrame({"HS300": [0.0]}, index=["2026-01-07"]),
        }

    monkeypatch.setattr(backtest_cli, "build_backtest_bundle", fake_build_backtest_bundle)

    cli_main(
        [
            "--mode",
            "quant_only",
            "--start",
            "2026-01-06",
            "--end",
            "2026-01-06",
            "--output-dir",
            str(output_dir),
            "--initial-holdings",
            str(holdings_path),
        ]
    )

    signal_path = output_dir / "quant_only" / "2026-01-06_2026-01-06" / "signal_sheet.json"
    signal_sheet = json.loads(signal_path.read_text(encoding="utf-8"))
    assert signal_sheet["current_holdings"][0]["code"] == "600000"


def test_build_backtest_bundle_keeps_demo_fallback_without_initial_state(tmp_path):
    bundle = build_backtest_bundle(
        tmp_path,
        start="2026-01-01",
        end="2026-01-05",
        mode="quant_only",
    )

    assert bundle["daily_candidates"]
    assert bundle["next_open_prices"]


def test_build_backtest_bundle_with_initial_state_does_not_fallback_to_demo(tmp_path):
    initial_state = PortfolioState(
        cash=5000.0,
        positions=[
            Position(
                code="600000",
                entry_date="2026-01-02",
                entry_price=10.0,
                weight=1.0,
                quantity=100,
            )
        ],
    )

    with pytest.raises(FileNotFoundError, match="本地|candidates"):
        build_backtest_bundle(
            tmp_path,
            start="2026-01-01",
            end="2026-01-05",
            mode="quant_only",
            initial_state=initial_state,
        )


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
    assert "signal_date,trade_date,risk_mode,code,action,category,instruction,priority_score" in content


def test_backtest_cli_writes_signal_sheet_review_markdown(tmp_path):
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

    review_path = output_dir / "quant_only" / "2026-01-01_2026-01-05" / "signal_sheet_review.md"
    assert review_path.exists()

    content = review_path.read_text(encoding="utf-8")
    assert "# 次日执行复核摘要" in content
    assert "## 风险摘要" in content
    assert "## 仓位摘要" in content


def test_backtest_cli_writes_signal_sheet_brief_markdown(tmp_path):
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

    brief_path = output_dir / "quant_only" / "2026-01-01_2026-01-05" / "signal_sheet_brief.md"
    assert brief_path.exists()

    content = brief_path.read_text(encoding="utf-8")
    assert "# 盘前执行卡片" in content
    assert "## 一句话摘要" in content
    assert "## 卖出优先" in content
    assert "## 持仓观察" in content
    assert "## 新开仓" in content
    assert "## Top 5 重点动作" in content


def test_load_backtest_config_reads_brief_execution_labels(tmp_path):
    config_path = tmp_path / "backtest.yaml"
    config_path.write_text(
        """brief:
  execution_labels:
    sell_review: 立刻执行
    hold_watch: 盘中观察
    new_buy: 尾盘再看
""",
        encoding="utf-8",
    )

    config = load_backtest_config(config_path)

    assert config["brief"]["execution_labels"]["sell_review"] == "立刻执行"
    assert config["brief"]["execution_labels"]["hold_watch"] == "盘中观察"
    assert config["brief"]["execution_labels"]["new_buy"] == "尾盘再看"


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


def test_load_local_backtest_bundle_accepts_scored_sell_review_payload(tmp_path):
    candidates_dir = tmp_path / "data" / "candidates"
    raw_dir = tmp_path / "data" / "raw"
    review_dir = tmp_path / "data" / "review" / "2026-01-06"
    review_sell_dir = tmp_path / "data" / "review_sell" / "2026-01-06"
    config_dir = tmp_path / "config"

    candidates_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)
    review_dir.mkdir(parents=True)
    review_sell_dir.mkdir(parents=True)
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
  "total_score": 4.2,
  "verdict": "PASS",
  "signal_type": "top_out",
  "comment": "高位放量滞涨，兑现风险上升。"
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
""",
        encoding="utf-8",
    )

    bundle = load_local_backtest_bundle(
        tmp_path,
        start="2026-01-06",
        end="2026-01-07",
        mode="quant_plus_ai",
    )

    assert bundle["sell_decisions"]["2026-01-06"]["600000"] == "sell"
    assert bundle["sell_reviews"]["2026-01-06"]["600000"]["reasoning"] == "高位放量滞涨，兑现风险上升。"
    assert bundle["sell_reviews"]["2026-01-06"]["600000"]["risk_flags"] == ["top_out"]


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


def test_load_local_backtest_bundle_loads_sell_reviews_for_tracked_non_candidate_codes(tmp_path):
    candidates_dir = tmp_path / "data" / "candidates"
    raw_dir = tmp_path / "data" / "raw"
    review_dir_day1 = tmp_path / "data" / "review" / "2026-01-06"
    review_dir_day2 = tmp_path / "data" / "review" / "2026-01-07"
    review_sell_dir_day2 = tmp_path / "data" / "review_sell" / "2026-01-07"
    config_dir = tmp_path / "config"

    candidates_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)
    review_dir_day1.mkdir(parents=True)
    review_dir_day2.mkdir(parents=True)
    review_sell_dir_day2.mkdir(parents=True)
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
2026-01-08,10.6,10.4,10.7,10.3,900
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
    (review_dir_day1 / "600000.json").write_text(
        """{"total_score": 4.6, "verdict": "PASS", "signal_type": "trend_start", "comment": "趋势健康。"}""",
        encoding="utf-8",
    )
    (review_dir_day2 / "000001.json").write_text(
        """{"total_score": 4.2, "verdict": "PASS", "signal_type": "trend_start", "comment": "趋势健康。"}""",
        encoding="utf-8",
    )
    (review_sell_dir_day2 / "600000.json").write_text(
        """{"decision": "sell", "reasoning": "老持仓趋势破坏。", "risk_flags": ["trend_break"], "confidence": 0.9}""",
        encoding="utf-8",
    )
    (review_sell_dir_day2 / "999999.json").write_text(
        """{"decision": "sell", "reasoning": "无关股票。", "risk_flags": ["noise"], "confidence": 0.1}""",
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
        mode="quant_plus_ai",
    )

    assert bundle["sell_decisions"]["2026-01-07"]["600000"] == "sell"
    assert bundle["sell_reviews"]["2026-01-07"]["600000"]["reasoning"] == "老持仓趋势破坏。"
    assert "999999" not in bundle["sell_decisions"]["2026-01-07"]


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

    assert result.daily_snapshots[0].cash == pytest.approx(90995.49946)
    assert result.daily_snapshots[0].equity == pytest.approx(99995.49946)
    assert result.daily_snapshots[1].cash == pytest.approx(99982.0018)
    assert result.daily_snapshots[1].equity == pytest.approx(99982.0018)


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


def test_engine_allocates_buy_quantity_from_total_equity_one_tenth():
    data_bundle = {
        "daily_candidates": {
            "2026-01-06": [
                Candidate(
                    code="600000",
                    date="2026-01-06",
                    strategy="b1",
                    close=10.8,
                    turnover_n=1000.0,
                    buy_review_score=4.5,
                )
            ]
        },
        "next_open_prices": {
            "2026-01-07": {"600000": 11.0},
        },
        "stock_to_index": {"600000": "HS300"},
        "benchmark_returns": pd.DataFrame({"HS300": [0.0]}, index=["2026-01-07"]),
    }

    result = run_backtest(
        {
            "max_positions": 10,
            "initial_cash": 100000.0,
            "costs": {"commission_bps": 0, "stamp_duty_bps": 0, "slippage_bps": 0},
        },
        data_bundle,
    )

    assert len(result.trades) == 1
    assert result.trades[0].side == "buy"
    assert result.trades[0].quantity == 900
    assert result.final_state.positions[0].quantity == 900
    assert result.daily_snapshots[0].cash == pytest.approx(90100.0)


def test_engine_sells_full_position_quantity_after_sized_buy():
    data_bundle = {
        "daily_candidates": {
            "2026-01-06": [
                Candidate(
                    code="600000",
                    date="2026-01-06",
                    strategy="b1",
                    close=10.0,
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
            {"HS300": [0.0, 0.0]},
            index=["2026-01-07", "2026-01-08"],
        ),
    }

    result = run_backtest(
        {
            "max_positions": 10,
            "initial_cash": 100000.0,
            "costs": {"commission_bps": 0, "stamp_duty_bps": 0, "slippage_bps": 0},
        },
        data_bundle,
    )

    assert [trade.side for trade in result.trades] == ["buy", "sell"]
    assert [trade.quantity for trade in result.trades] == [1000, 1000]
    assert result.final_state.positions == []


def test_engine_does_not_buy_back_code_sold_on_same_signal_day():
    data_bundle = {
        "daily_candidates": {
            "2026-01-06": [
                Candidate(
                    code="600000",
                    date="2026-01-06",
                    strategy="b1",
                    close=10.0,
                    turnover_n=1000.0,
                    buy_review_score=4.5,
                )
            ],
            "2026-01-07": [
                Candidate(
                    code="600000",
                    date="2026-01-07",
                    strategy="b1",
                    close=10.2,
                    turnover_n=1000.0,
                    buy_review_score=4.8,
                )
            ],
        },
        "next_open_prices": {
            "2026-01-07": {"600000": 10.0},
            "2026-01-08": {"600000": 10.2},
        },
        "sell_decisions": {
            "2026-01-07": {"600000": "sell"},
        },
        "stock_to_index": {"600000": "HS300"},
        "benchmark_returns": pd.DataFrame(
            {"HS300": [0.0, 0.0]},
            index=["2026-01-07", "2026-01-08"],
        ),
    }

    result = run_backtest(
        {
            "max_positions": 10,
            "initial_cash": 100000.0,
            "costs": {"commission_bps": 0, "stamp_duty_bps": 0, "slippage_bps": 0},
        },
        data_bundle,
    )

    assert [trade.side for trade in result.trades] == ["buy", "sell"]
    assert result.final_state.positions == []


def test_engine_keeps_cash_when_pass_candidates_are_fewer_than_available_slots():
    data_bundle = {
        "daily_candidates": {
            "2026-01-06": [
                Candidate(
                    code="600000",
                    date="2026-01-06",
                    strategy="b1",
                    close=10.0,
                    turnover_n=1000.0,
                    buy_review_score=4.5,
                ),
                Candidate(
                    code="000001",
                    date="2026-01-06",
                    strategy="b1",
                    close=20.0,
                    turnover_n=900.0,
                    buy_review_score=4.4,
                ),
            ]
        },
        "next_open_prices": {
            "2026-01-07": {
                "600000": 10.0,
                "000001": 20.0,
            },
        },
        "stock_to_index": {
            "600000": "HS300",
            "000001": "CSI2000",
        },
        "benchmark_returns": pd.DataFrame({"HS300": [0.0], "CSI2000": [0.0]}, index=["2026-01-07"]),
    }

    result = run_backtest(
        {
            "max_positions": 10,
            "initial_cash": 100000.0,
            "costs": {"commission_bps": 0, "stamp_duty_bps": 0, "slippage_bps": 0},
        },
        data_bundle,
    )

    assert len(result.final_state.positions) == 2
    assert result.daily_snapshots[0].cash > 0


def test_engine_applies_same_index_limit_to_new_buys():
    candidates = [
        Candidate(
            code=f"60000{idx}",
            date="2026-01-06",
            strategy="b1",
            close=10.0 + idx,
            turnover_n=1000.0,
            buy_review_score=4.9 - idx * 0.1,
        )
        for idx in range(5)
    ]
    data_bundle = {
        "daily_candidates": {"2026-01-06": candidates},
        "next_open_prices": {
            "2026-01-07": {candidate.code: candidate.close for candidate in candidates},
        },
        "stock_to_index": {candidate.code: "CSI2000" for candidate in candidates},
        "benchmark_returns": pd.DataFrame({"CSI2000": [0.0]}, index=["2026-01-07"]),
    }

    result = run_backtest(
        {
            "max_positions": 10,
            "initial_cash": 100000.0,
            "portfolio": {"max_same_index": 4},
            "costs": {"commission_bps": 0, "stamp_duty_bps": 0, "slippage_bps": 0},
        },
        data_bundle,
    )

    assert len(result.final_state.positions) == 4
    assert result.last_buy_rejections["index_limit"] == ["600004"]
    assert "指数约束拒绝 1 只" in result.last_cash_reserved_reason


def test_engine_applies_same_industry_limit_to_new_buys():
    candidates = [
        Candidate(code="600000", date="2026-01-06", strategy="b1", close=10.0, turnover_n=1000.0, buy_review_score=4.9),
        Candidate(code="600001", date="2026-01-06", strategy="b1", close=11.0, turnover_n=1000.0, buy_review_score=4.8),
        Candidate(code="600002", date="2026-01-06", strategy="b1", close=12.0, turnover_n=1000.0, buy_review_score=4.7),
    ]
    data_bundle = {
        "daily_candidates": {"2026-01-06": candidates},
        "next_open_prices": {
            "2026-01-07": {candidate.code: candidate.close for candidate in candidates},
        },
        "stock_to_index": {
            "600000": "CSI2000",
            "600001": "HS300",
            "600002": "CSI500",
        },
        "stock_to_industry": {
            "600000": "有色金属",
            "600001": "有色金属",
            "600002": "有色金属",
        },
        "benchmark_returns": pd.DataFrame(
            {"CSI2000": [0.0], "HS300": [0.0], "CSI500": [0.0]},
            index=["2026-01-07"],
        ),
    }

    result = run_backtest(
        {
            "max_positions": 10,
            "initial_cash": 100000.0,
            "portfolio": {"max_same_industry": 2},
            "costs": {"commission_bps": 0, "stamp_duty_bps": 0, "slippage_bps": 0},
        },
        data_bundle,
    )

    assert len(result.final_state.positions) == 2
    assert result.last_buy_rejections["industry_limit"] == ["600002"]
    assert "行业约束拒绝 1 只" in result.last_cash_reserved_reason


def test_engine_replaces_watch_position_with_new_pass_candidate():
    data_bundle = {
        "daily_candidates": {
            "2026-01-06": [
                Candidate(code="600000", date="2026-01-06", strategy="b1", close=10.0, turnover_n=1000.0, buy_review_score=4.5),
            ],
            "2026-01-07": [
                Candidate(code="000001", date="2026-01-07", strategy="b1", close=9.5, turnover_n=900.0, buy_review_score=4.8),
            ],
        },
        "next_open_prices": {
            "2026-01-07": {"600000": 10.0},
            "2026-01-08": {"600000": 9.8, "000001": 9.5},
        },
        "sell_reviews": {
            "2026-01-07": {
                "600000": {
                    "decision": "hold",
                    "verdict": "WATCH",
                    "total_score": 3.6,
                    "reasoning": "趋势转弱。",
                    "risk_flags": ["weakening"],
                    "confidence": 0.28,
                }
            }
        },
        "stock_to_index": {"600000": "HS300", "000001": "CSI2000"},
        "benchmark_returns": pd.DataFrame(
            {"HS300": [0.0, 0.0], "CSI2000": [0.0, 0.0]},
            index=["2026-01-07", "2026-01-08"],
        ),
    }

    result = run_backtest(
        {
            "max_positions": 1,
            "initial_cash": 100000.0,
            "portfolio": {"max_daily_replacements": 1},
            "costs": {"commission_bps": 0, "stamp_duty_bps": 0, "slippage_bps": 0},
        },
        data_bundle,
    )

    assert [trade.side for trade in result.trades] == ["buy", "sell", "buy"]
    assert [position.code for position in result.final_state.positions] == ["000001"]
    assert result.last_replaceable_watch_list == [
        {
            "code": "600000",
            "holding_days": 0,
            "sell_score": 3.6,
            "reasoning": "趋势转弱。",
            "risk_flags": ["weakening"],
            "status": "replaced",
            "replacement_code": "000001",
            "replacement_score": 4.8,
        }
    ]


def test_engine_does_not_replace_fail_position_with_new_candidate():
    data_bundle = {
        "daily_candidates": {
            "2026-01-06": [
                Candidate(code="600000", date="2026-01-06", strategy="b1", close=10.0, turnover_n=1000.0, buy_review_score=4.5),
            ],
            "2026-01-07": [
                Candidate(code="000001", date="2026-01-07", strategy="b1", close=9.5, turnover_n=900.0, buy_review_score=4.8),
            ],
        },
        "next_open_prices": {
            "2026-01-07": {"600000": 10.0},
            "2026-01-08": {"600000": 9.8, "000001": 9.5},
        },
        "sell_reviews": {
            "2026-01-07": {
                "600000": {
                    "decision": "hold",
                    "verdict": "FAIL",
                    "total_score": 2.8,
                    "reasoning": "趋势仍健康。",
                    "risk_flags": [],
                    "confidence": 0.44,
                }
            }
        },
        "stock_to_index": {"600000": "HS300", "000001": "CSI2000"},
        "benchmark_returns": pd.DataFrame(
            {"HS300": [0.0, 0.0], "CSI2000": [0.0, 0.0]},
            index=["2026-01-07", "2026-01-08"],
        ),
    }

    result = run_backtest(
        {
            "max_positions": 1,
            "initial_cash": 100000.0,
            "portfolio": {"max_daily_replacements": 1},
            "costs": {"commission_bps": 0, "stamp_duty_bps": 0, "slippage_bps": 0},
        },
        data_bundle,
    )

    assert [trade.side for trade in result.trades] == ["buy"]
    assert [position.code for position in result.final_state.positions] == ["600000"]
