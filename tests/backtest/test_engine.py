import pandas as pd

from backtest.cli import build_parser
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
