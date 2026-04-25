import json
from pathlib import Path

import pytest

import run_all


def test_run_all_parser_exposes_trading_loop_options():
    parser = run_all.build_parser()

    args = parser.parse_args(
        [
            "--skip-fetch",
            "--start-from",
            "3",
            "--holdings",
            "data/backtest/x/holdings_snapshot.json",
            "--skip-sell-review",
            "--skip-backtest-signal",
            "--allow-empty-holdings",
        ]
    )

    assert args.skip_fetch is True
    assert args.start_from == 3
    assert args.holdings == "data/backtest/x/holdings_snapshot.json"
    assert args.skip_sell_review is True
    assert args.skip_backtest_signal is True
    assert args.allow_empty_holdings is True


def test_load_latest_pick_date_reads_candidates_latest(tmp_path):
    candidates_dir = tmp_path / "data" / "candidates"
    candidates_dir.mkdir(parents=True)
    (candidates_dir / "candidates_latest.json").write_text(
        json.dumps({"pick_date": "2026-04-24", "candidates": []}),
        encoding="utf-8",
    )

    assert run_all.load_latest_pick_date(tmp_path) == "2026-04-24"


def test_load_latest_pick_date_fails_when_missing_pick_date(tmp_path):
    candidates_dir = tmp_path / "data" / "candidates"
    candidates_dir.mkdir(parents=True)
    (candidates_dir / "candidates_latest.json").write_text(
        json.dumps({"candidates": []}),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit):
        run_all.load_latest_pick_date(tmp_path)


def test_validate_holdings_snapshot_accepts_snapshot_file(tmp_path):
    holdings_path = tmp_path / "holdings_snapshot.json"
    holdings_path.write_text(
        json.dumps(
            {
                "as_of_date": "2026-04-24",
                "state": {
                    "cash": 1000000.0,
                    "positions": [{"code": "600000"}],
                },
            }
        ),
        encoding="utf-8",
    )

    assert run_all.validate_holdings_snapshot(holdings_path) is True


def test_validate_holdings_snapshot_rejects_invalid_file(tmp_path):
    holdings_path = tmp_path / "holdings_snapshot.json"
    holdings_path.write_text(json.dumps({"bad": "shape"}), encoding="utf-8")

    assert run_all.validate_holdings_snapshot(holdings_path) is False
