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


class StepRecorder:
    def __init__(self):
        self.calls = []

    def __call__(self, step_name: str, cmd: list[str]) -> None:
        self.calls.append((step_name, cmd))


def _write_candidates_latest(root: Path, pick_date: str = "2026-04-24") -> None:
    candidates_dir = root / "data" / "candidates"
    candidates_dir.mkdir(parents=True, exist_ok=True)
    (candidates_dir / "candidates_latest.json").write_text(
        json.dumps({"pick_date": pick_date, "candidates": []}),
        encoding="utf-8",
    )
    (candidates_dir / f"candidates_{pick_date}.json").write_text(
        json.dumps({"pick_date": pick_date, "candidates": []}),
        encoding="utf-8",
    )


def _write_suggestion(root: Path, pick_date: str = "2026-04-24") -> None:
    review_dir = root / "data" / "review" / pick_date
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / "suggestion.json").write_text(
        json.dumps({"date": pick_date, "recommendations": []}),
        encoding="utf-8",
    )


def test_run_daily_loop_without_holdings_skips_sell_review(tmp_path, capsys):
    _write_candidates_latest(tmp_path)
    _write_suggestion(tmp_path)
    recorder = StepRecorder()
    parser = run_all.build_parser()
    args = parser.parse_args(["--skip-fetch"])

    run_all.run_daily_loop(
        args,
        root=tmp_path,
        python="python",
        run_step=recorder,
        print_recommendations=lambda: None,
        print_signal_summary=lambda path: None,
    )

    commands = [" ".join(cmd) for _, cmd in recorder.calls]
    assert "python -m pipeline.fetch_kline" not in commands
    assert any("python -m pipeline.cli preselect" == command for command in commands)
    assert any("python -m agent.buy_review" == command for command in commands)
    assert not any("agent.sell_review" in command for command in commands)
    assert any("python -m backtest.cli --mode quant_plus_ai --start 2026-04-24 --end 2026-04-24" == command for command in commands)
    captured = capsys.readouterr()
    assert "未找到持仓快照" in captured.out


def test_run_daily_loop_with_holdings_runs_sell_review(tmp_path):
    _write_candidates_latest(tmp_path)
    _write_suggestion(tmp_path)
    holdings_path = _write_holdings(tmp_path / "holdings_snapshot.json")
    recorder = StepRecorder()
    parser = run_all.build_parser()
    args = parser.parse_args(["--skip-fetch", "--holdings", str(holdings_path)])

    run_all.run_daily_loop(
        args,
        root=tmp_path,
        python="python",
        run_step=recorder,
        print_recommendations=lambda: None,
        print_signal_summary=lambda path: None,
    )

    commands = [" ".join(cmd) for _, cmd in recorder.calls]
    assert any(f"python -m agent.sell_review --input {holdings_path}" == command for command in commands)


def test_run_daily_loop_skip_sell_review_never_runs_sell_review(tmp_path):
    _write_candidates_latest(tmp_path)
    _write_suggestion(tmp_path)
    holdings_path = _write_holdings(tmp_path / "holdings_snapshot.json")
    recorder = StepRecorder()
    parser = run_all.build_parser()
    args = parser.parse_args(["--skip-fetch", "--holdings", str(holdings_path), "--skip-sell-review"])

    run_all.run_daily_loop(
        args,
        root=tmp_path,
        python="python",
        run_step=recorder,
        print_recommendations=lambda: None,
        print_signal_summary=lambda path: None,
    )

    commands = [" ".join(cmd) for _, cmd in recorder.calls]
    assert not any("agent.sell_review" in command for command in commands)


def test_run_daily_loop_start_from_6_skips_recommendations_and_runs_later_steps(tmp_path):
    _write_candidates_latest(tmp_path)
    _write_suggestion(tmp_path)
    holdings_path = _write_holdings(tmp_path / "holdings_snapshot.json")
    recorder = StepRecorder()
    parser = run_all.build_parser()
    args = parser.parse_args(["--start-from", "6", "--holdings", str(holdings_path)])
    recommendation_calls = []

    run_all.run_daily_loop(
        args,
        root=tmp_path,
        python="python",
        run_step=recorder,
        print_recommendations=lambda: recommendation_calls.append("called"),
        print_signal_summary=lambda path: None,
    )

    commands = [" ".join(cmd) for _, cmd in recorder.calls]
    assert recommendation_calls == []
    assert not any("pipeline.fetch_kline" in command for command in commands)
    assert not any("pipeline.cli preselect" in command for command in commands)
    assert not any("export_kline_charts" in command for command in commands)
    assert not any("agent.buy_review" in command for command in commands)
    assert any(f"python -m agent.sell_review --input {holdings_path}" == command for command in commands)
    assert any("python -m backtest.cli --mode quant_plus_ai --start 2026-04-24 --end 2026-04-24" == command for command in commands)


def test_run_daily_loop_start_from_7_only_runs_backtest_signal(tmp_path):
    _write_candidates_latest(tmp_path)
    _write_suggestion(tmp_path)
    holdings_path = _write_holdings(tmp_path / "holdings_snapshot.json")
    recorder = StepRecorder()
    parser = run_all.build_parser()
    args = parser.parse_args(["--start-from", "7", "--holdings", str(holdings_path)])
    recommendation_calls = []

    run_all.run_daily_loop(
        args,
        root=tmp_path,
        python="python",
        run_step=recorder,
        print_recommendations=lambda: recommendation_calls.append("called"),
        print_signal_summary=lambda path: None,
    )

    commands = [" ".join(cmd) for _, cmd in recorder.calls]
    assert recommendation_calls == []
    assert not any("pipeline.fetch_kline" in command for command in commands)
    assert not any("pipeline.cli preselect" in command for command in commands)
    assert not any("export_kline_charts" in command for command in commands)
    assert not any("agent.buy_review" in command for command in commands)
    assert not any("agent.sell_review" in command for command in commands)
    assert commands == [
        "python -m backtest.cli --mode quant_plus_ai --start 2026-04-24 --end 2026-04-24"
    ]


def test_run_daily_loop_start_from_6_skip_signal_does_not_require_candidates(tmp_path):
    holdings_path = _write_holdings(tmp_path / "holdings_snapshot.json")
    recorder = StepRecorder()
    parser = run_all.build_parser()
    args = parser.parse_args(
        ["--start-from", "6", "--skip-backtest-signal", "--holdings", str(holdings_path)]
    )

    run_all.run_daily_loop(
        args,
        root=tmp_path,
        python="python",
        run_step=recorder,
        print_recommendations=lambda: None,
        print_signal_summary=lambda path: None,
    )

    commands = [" ".join(cmd) for _, cmd in recorder.calls]
    assert commands == [f"python -m agent.sell_review --input {holdings_path}"]


def test_run_daily_loop_step_names_use_seven_step_numbering(tmp_path):
    _write_candidates_latest(tmp_path)
    _write_suggestion(tmp_path)
    recorder = StepRecorder()
    parser = run_all.build_parser()
    args = parser.parse_args([])

    run_all.run_daily_loop(
        args,
        root=tmp_path,
        python="python",
        run_step=recorder,
        print_recommendations=lambda: None,
        print_signal_summary=lambda path: None,
    )

    step_names = [step_name for step_name, _ in recorder.calls]
    assert step_names[:4] == [
        "1/7  拉取 K 线数据（fetch_kline）",
        "2/7  量化初选（cli preselect）",
        "3/7  导出 K 线图（export_kline_charts）",
        "4/7  双模型图表分析（buy_review）",
    ]


def test_ensure_daily_signal_inputs_requires_dated_candidates(tmp_path):
    _write_suggestion(tmp_path)

    with pytest.raises(SystemExit):
        run_all.ensure_daily_signal_inputs(tmp_path, "2026-04-24")


def test_ensure_daily_signal_inputs_requires_suggestion(tmp_path):
    _write_candidates_latest(tmp_path)
    suggestion_path = tmp_path / "data" / "review" / "2026-04-24" / "suggestion.json"
    if suggestion_path.exists():
        suggestion_path.unlink()

    with pytest.raises(SystemExit):
        run_all.ensure_daily_signal_inputs(tmp_path, "2026-04-24")


def test_build_signal_brief_path_uses_quant_plus_ai_daily_output(tmp_path):
    path = run_all.build_signal_brief_path(tmp_path, "2026-04-24")

    assert path == (
        tmp_path
        / "data"
        / "backtest"
        / "quant_plus_ai"
        / "2026-04-24_2026-04-24"
        / "signal_sheet_brief.md"
    )


def test_print_signal_brief_summary_prints_path_and_key_sections(tmp_path, capsys):
    brief_path = tmp_path / "signal_sheet_brief.md"
    brief_path.write_text(
        "# 盘前执行卡片\n\n"
        "- 信号日期：2026-04-24\n"
        "- 执行日期：2026-04-27\n"
        "- 风险模式：normal\n"
        "- 当前/目标仓位：2 -> 3\n\n"
        "## Top 5 重点动作\n"
        "- 买入 600000\n\n"
        "## 新开仓（1）\n"
        "- 600000\n",
        encoding="utf-8",
    )

    run_all.print_signal_brief_summary(brief_path)

    output = capsys.readouterr().out
    assert "次日执行卡片" in output
    assert str(brief_path) in output
    assert "信号日期：2026-04-24" in output
    assert "买入 600000" in output


def test_print_signal_brief_summary_accepts_variable_top_actions_limit(tmp_path, capsys):
    brief_path = tmp_path / "signal_sheet_brief.md"
    brief_path.write_text(
        "# 盘前执行卡片\n\n"
        "- 信号日期：2026-04-24\n"
        "- 执行日期：2026-04-27\n"
        "- 风险模式：normal\n"
        "- 当前/目标仓位：2 -> 3\n\n"
        "## Top 3 重点动作\n"
        "- 卖出 600000\n\n"
        "## 新开仓（1）\n"
        "- 000001\n",
        encoding="utf-8",
    )

    run_all.print_signal_brief_summary(brief_path)

    output = capsys.readouterr().out
    assert "Top 3 重点动作" in output
    assert "卖出 600000" in output


def test_run_daily_loop_allow_empty_holdings_mentions_empty_position(tmp_path, capsys):
    _write_candidates_latest(tmp_path)
    _write_suggestion(tmp_path)
    recorder = StepRecorder()
    parser = run_all.build_parser()
    args = parser.parse_args(["--skip-fetch", "--allow-empty-holdings"])

    run_all.run_daily_loop(
        args,
        root=tmp_path,
        python="python",
        run_step=recorder,
        print_recommendations=lambda: None,
        print_signal_summary=lambda path: None,
    )

    output = capsys.readouterr().out
    assert "按空仓处理" in output
