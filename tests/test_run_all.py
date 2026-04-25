import json
import os
import sys
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


def test_load_latest_pick_date_fails_when_candidates_latest_missing(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc_info:
        run_all.load_latest_pick_date(tmp_path)

    assert exc_info.value.code == 1
    assert "找不到 candidates_latest.json" in capsys.readouterr().out


def test_load_latest_pick_date_fails_when_missing_pick_date(tmp_path, capsys):
    candidates_dir = tmp_path / "data" / "candidates"
    candidates_dir.mkdir(parents=True)
    (candidates_dir / "candidates_latest.json").write_text(
        json.dumps({"candidates": []}),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit) as exc_info:
        run_all.load_latest_pick_date(tmp_path)

    assert exc_info.value.code == 1
    assert "未设置 pick_date" in capsys.readouterr().out


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


def test_validate_holdings_snapshot_rejects_missing_file(tmp_path):
    assert run_all.validate_holdings_snapshot(tmp_path / "holdings_snapshot.json") is False


def test_validate_holdings_snapshot_rejects_json_decode_error(tmp_path):
    holdings_path = tmp_path / "holdings_snapshot.json"
    holdings_path.write_text("{bad json", encoding="utf-8")

    assert run_all.validate_holdings_snapshot(holdings_path) is False


def _write_holdings(path: Path, *, as_of_date: str = "2026-04-24") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "as_of_date": as_of_date,
                "state": {"cash": 1000000.0, "positions": [{"code": "600000"}]},
            }
        ),
        encoding="utf-8",
    )
    return path


def test_resolve_holdings_snapshot_uses_explicit_path(tmp_path):
    holdings_path = _write_holdings(tmp_path / "custom" / "holdings_snapshot.json")

    resolved = run_all.resolve_holdings_snapshot(tmp_path, explicit_path=str(holdings_path))

    assert resolved == holdings_path


def test_resolve_holdings_snapshot_uses_relative_explicit_path(tmp_path):
    holdings_path = _write_holdings(tmp_path / "relative" / "holdings_snapshot.json")

    resolved = run_all.resolve_holdings_snapshot(
        tmp_path,
        explicit_path="relative/holdings_snapshot.json",
    )

    assert resolved == holdings_path


def test_resolve_holdings_snapshot_fails_for_missing_explicit_path(tmp_path):
    missing_path = tmp_path / "missing.json"

    with pytest.raises(SystemExit):
        run_all.resolve_holdings_snapshot(tmp_path, explicit_path=str(missing_path))


def test_resolve_holdings_snapshot_finds_latest_backtest_snapshot(tmp_path):
    old_path = _write_holdings(
        tmp_path / "data" / "backtest" / "quant_plus_ai" / "old" / "holdings_snapshot.json",
        as_of_date="2026-04-23",
    )
    new_path = _write_holdings(
        tmp_path / "data" / "backtest" / "quant_plus_ai" / "new" / "holdings_snapshot.json",
        as_of_date="2026-04-24",
    )
    os.utime(old_path, (1000, 1000))
    os.utime(new_path, (2000, 2000))

    resolved = run_all.resolve_holdings_snapshot(tmp_path)

    assert resolved == new_path


def test_resolve_holdings_snapshot_breaks_mtime_ties_by_path(tmp_path, monkeypatch):
    low_path = _write_holdings(
        tmp_path / "data" / "backtest" / "quant_plus_ai" / "aaa" / "holdings_snapshot.json"
    )
    high_path = _write_holdings(
        tmp_path / "data" / "backtest" / "quant_plus_ai" / "zzz" / "holdings_snapshot.json"
    )
    os.utime(low_path, (1000, 1000))
    os.utime(high_path, (1000, 1000))

    monkeypatch.setattr(Path, "glob", lambda self, pattern: iter([low_path, high_path]))

    resolved = run_all.resolve_holdings_snapshot(tmp_path)

    assert resolved == high_path


def test_resolve_holdings_snapshot_returns_none_when_not_found(tmp_path):
    assert run_all.resolve_holdings_snapshot(tmp_path) is None


def test_main_routes_backtest_before_daily_parser(monkeypatch):
    calls = []

    def fake_run(step_name, cmd):
        calls.append((step_name, cmd))

    monkeypatch.setattr(run_all, "load_project_env", lambda: None)
    monkeypatch.setattr(run_all, "_run", fake_run)
    monkeypatch.setattr(sys, "argv", ["run_all.py", "backtest", "--start", "2026-01-01"])

    run_all.main()

    assert calls == [
        (
            "回测（backtest.cli）",
            [run_all.PYTHON, "-m", "backtest.cli", "--start", "2026-01-01"],
        )
    ]
