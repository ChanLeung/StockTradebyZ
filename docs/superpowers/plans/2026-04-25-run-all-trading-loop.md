# run_all.py Trading Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade `python run_all.py` from a buy-only recommendation script into the daily trading-loop entrypoint that can run buy review, optional sell review, and one-day signal-sheet generation.

**Architecture:** Keep `run_all.py` as a thin orchestrator that shells out to existing modules instead of duplicating trading logic. Add small helper functions for argument parsing, latest `pick_date` loading, holdings snapshot resolution, guard checks, and signal-card summary printing so the behavior can be unit-tested without running external services. Preserve `python run_all.py backtest ...` as a direct pass-through to `backtest.cli`.

**Tech Stack:** Python 3.12, argparse, pathlib, json, subprocess, pytest, existing `agent.*`, `pipeline.*`, `dashboard.*`, and `backtest.cli` modules.

---

## File Structure

- Modify: `run_all.py`
  - Owns command-line parsing and subprocess orchestration.
  - Adds testable helpers for daily trading-loop flow.
  - Does not parse AI model internals or implement trading decisions.
- Create: `tests/test_run_all.py`
  - Unit tests command construction, holdings resolution, signal input guards, and backtest subcommand preservation.
  - Uses monkeypatch/fake runners rather than invoking network/model/data-heavy steps.
- Modify: `README.md`
  - Documents that `python run_all.py` is now the daily trading-loop entrypoint.
  - Keeps `python run_all.py backtest ...` as the historical research entrypoint.

## Implementation Rules

- Use Chinese comments and user-facing messages.
- Keep changes surgical; avoid refactoring unrelated modules.
- Do not change `backtest.cli` in this plan.
- Do not add broker execution.
- Do not silently rely on demo fallback in daily mode; guard required local files before calling `backtest.cli`.
- Preserve existing `--skip-fetch` and `--start-from` behavior for the first four steps.

---

### Task 1: Add Testable Parser and Utility Helpers

**Files:**
- Modify: `run_all.py`
- Create: `tests/test_run_all.py`

- [ ] **Step 1: Write failing tests for the new parser and helpers**

Create `tests/test_run_all.py` with these tests:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/test_run_all.py -q
```

Expected: FAIL because `build_parser`, `load_latest_pick_date`, and `validate_holdings_snapshot` do not exist yet.

- [ ] **Step 3: Add the minimal parser and helper implementation**

In `run_all.py`, add imports and helper functions near the top:

```python
from collections.abc import Callable


StepRunner = Callable[[str, list[str]], None]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AgentTrader 日常交易闭环自动运行脚本")
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="跳过步骤 1（行情下载），直接从初选开始",
    )
    parser.add_argument(
        "--start-from",
        type=int,
        default=1,
        metavar="N",
        help="从第 N 步开始执行（1~7），跳过前面的步骤",
    )
    parser.add_argument(
        "--holdings",
        default=None,
        help="当前持仓快照路径，用于卖出复评",
    )
    parser.add_argument(
        "--skip-sell-review",
        action="store_true",
        help="跳过持仓卖出复评，只生成买入建议",
    )
    parser.add_argument(
        "--skip-backtest-signal",
        action="store_true",
        help="跳过次日执行信号单生成",
    )
    parser.add_argument(
        "--allow-empty-holdings",
        action="store_true",
        help="没有持仓快照时继续执行，按空仓处理",
    )
    return parser


def load_latest_pick_date(root: Path = ROOT) -> str:
    candidates_file = root / "data" / "candidates" / "candidates_latest.json"
    if not candidates_file.exists():
        print(f"[ERROR] 找不到 candidates_latest.json：{candidates_file}")
        raise SystemExit(1)

    with candidates_file.open(encoding="utf-8") as f:
        pick_date = str(json.load(f).get("pick_date", "")).strip()

    if not pick_date:
        print("[ERROR] candidates_latest.json 中未设置 pick_date。")
        raise SystemExit(1)
    return pick_date


def validate_holdings_snapshot(path: Path) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False

    if not isinstance(payload, dict):
        return False
    if not payload.get("as_of_date"):
        return False
    state = payload.get("state")
    if not isinstance(state, dict):
        return False
    positions = state.get("positions")
    if not isinstance(positions, list):
        return False
    return all(isinstance(item, dict) and item.get("code") for item in positions)
```

- [ ] **Step 4: Replace inline parser creation with `build_parser()`**

In `main()`, replace the existing `argparse.ArgumentParser(...)` block with:

```python
    parser = build_parser()
    args = parser.parse_args()
```

Keep the existing backtest subcommand guard before parser creation.

- [ ] **Step 5: Run tests to verify Task 1 passes**

Run:

```bash
python -m pytest tests/test_run_all.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 1**

```bash
git add run_all.py tests/test_run_all.py
git commit -m "功能: 增加run_all闭环参数和基础校验"
```

---

### Task 2: Resolve Current Holdings Snapshot

**Files:**
- Modify: `run_all.py`
- Modify: `tests/test_run_all.py`

- [ ] **Step 1: Add failing tests for holdings snapshot resolution**

Append these tests to `tests/test_run_all.py`:

```python
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
    old_path.touch()
    new_path.touch()

    resolved = run_all.resolve_holdings_snapshot(tmp_path)

    assert resolved == new_path


def test_resolve_holdings_snapshot_returns_none_when_not_found(tmp_path):
    assert run_all.resolve_holdings_snapshot(tmp_path) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/test_run_all.py -q
```

Expected: FAIL because `resolve_holdings_snapshot` does not exist yet.

- [ ] **Step 3: Implement holdings snapshot resolution**

Add this function to `run_all.py` after `validate_holdings_snapshot`:

```python
def resolve_holdings_snapshot(root: Path = ROOT, explicit_path: str | None = None) -> Path | None:
    if explicit_path:
        holdings_path = Path(explicit_path)
        if not holdings_path.is_absolute():
            holdings_path = root / holdings_path
        if not holdings_path.exists():
            print(f"[ERROR] 指定的持仓快照不存在：{holdings_path}")
            raise SystemExit(1)
        if not validate_holdings_snapshot(holdings_path):
            print(f"[ERROR] 指定的持仓快照格式不正确：{holdings_path}")
            raise SystemExit(1)
        return holdings_path

    candidates = [
        path
        for path in (root / "data" / "backtest").glob("**/holdings_snapshot.json")
        if validate_holdings_snapshot(path)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)
```

- [ ] **Step 4: Run tests to verify Task 2 passes**

Run:

```bash
python -m pytest tests/test_run_all.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

```bash
git add run_all.py tests/test_run_all.py
git commit -m "功能: 自动定位run_all持仓快照"
```

---

### Task 3: Add Daily Trading Loop Orchestration

**Files:**
- Modify: `run_all.py`
- Modify: `tests/test_run_all.py`

- [ ] **Step 1: Add failing tests for daily loop command sequence**

Append these tests to `tests/test_run_all.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/test_run_all.py -q
```

Expected: FAIL because `run_daily_loop` does not exist yet.

- [ ] **Step 3: Implement `run_daily_loop`**

Add this function to `run_all.py` above `main()`:

```python
def run_daily_loop(
    args: argparse.Namespace,
    *,
    root: Path = ROOT,
    python: str = PYTHON,
    run_step: StepRunner = _run,
    print_recommendations: Callable[[], None] = _print_recommendations,
    print_signal_summary: Callable[[Path], None] | None = None,
) -> None:
    start = args.start_from
    if args.skip_fetch and start == 1:
        start = 2

    if start <= 1:
        run_step("1/7  拉取 K 线数据（fetch_kline）", [python, "-m", "pipeline.fetch_kline"])

    if start <= 2:
        run_step("2/7  量化初选（cli preselect）", [python, "-m", "pipeline.cli", "preselect"])

    if start <= 3:
        run_step(
            "3/7  导出 K 线图（export_kline_charts）",
            [python, str(root / "dashboard" / "export_kline_charts.py")],
        )

    if start <= 4:
        run_step("4/7  双模型买入复评（buy_review）", [python, "-m", "agent.buy_review"])

    print(f"\n{'='*60}")
    print("[步骤] 5/7  推荐购买的股票")
    print_recommendations()

    pick_date = load_latest_pick_date(root)
    holdings_path = resolve_holdings_snapshot(root, args.holdings)

    if args.skip_sell_review:
        print("[INFO] 已按参数跳过卖出复评。")
    elif holdings_path is None:
        print("[WARN] 未找到持仓快照，本次跳过卖出复评，仅生成买入建议和空仓信号单。")
    else:
        run_step(
            "6/7  持仓卖出复评（sell_review）",
            [python, "-m", "agent.sell_review", "--input", str(holdings_path)],
        )

    if args.skip_backtest_signal:
        print("[INFO] 已按参数跳过次日执行信号单生成。")
        return

    signal_brief_path = build_signal_brief_path(root, pick_date)
    ensure_daily_signal_inputs(root, pick_date)
    run_step(
        "7/7  生成次日执行信号单（backtest.cli）",
        [
            python,
            "-m",
            "backtest.cli",
            "--mode",
            "quant_plus_ai",
            "--start",
            pick_date,
            "--end",
            pick_date,
        ],
    )
    if print_signal_summary is None:
        print_signal_summary = print_signal_brief_summary
    print_signal_summary(signal_brief_path)
```

- [ ] **Step 4: Update `main()` to call `run_daily_loop`**

Replace the existing daily-mode body in `main()` after `args = parser.parse_args()` with:

```python
    run_daily_loop(args)
```

Keep this backtest subcommand block unchanged:

```python
    if len(sys.argv) > 1 and sys.argv[1] == "backtest":
        _run(
            "回测（backtest.cli）",
            [PYTHON, "-m", "backtest.cli", *sys.argv[2:]],
        )
        return
```

- [ ] **Step 5: Run tests to observe missing signal helper failures**

Run:

```bash
python -m pytest tests/test_run_all.py -q
```

Expected: FAIL because `build_signal_brief_path`, `ensure_daily_signal_inputs`, or `print_signal_brief_summary` are not implemented yet. Continue with Task 4.

---

### Task 4: Guard Daily Signal Generation and Print Brief Summary

**Files:**
- Modify: `run_all.py`
- Modify: `tests/test_run_all.py`

- [ ] **Step 1: Add failing tests for signal guards and summary printing**

Append these tests to `tests/test_run_all.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify failures**

Run:

```bash
python -m pytest tests/test_run_all.py -q
```

Expected: FAIL because the helper functions are missing.

- [ ] **Step 3: Implement signal guard helpers**

Add these functions to `run_all.py`:

```python
def ensure_daily_signal_inputs(root: Path, pick_date: str) -> None:
    candidates_file = root / "data" / "candidates" / f"candidates_{pick_date}.json"
    suggestion_file = root / "data" / "review" / pick_date / "suggestion.json"

    if not candidates_file.exists():
        print(f"[ERROR] 找不到真实候选文件，拒绝使用 demo 回测：{candidates_file}")
        raise SystemExit(1)
    if not suggestion_file.exists():
        print(f"[ERROR] 找不到买入复评汇总，无法生成真实信号单：{suggestion_file}")
        raise SystemExit(1)


def build_signal_brief_path(root: Path, pick_date: str) -> Path:
    return (
        root
        / "data"
        / "backtest"
        / "quant_plus_ai"
        / f"{pick_date}_{pick_date}"
        / "signal_sheet_brief.md"
    )
```

- [ ] **Step 4: Implement signal-card summary printing**

Add this function to `run_all.py`:

```python
def print_signal_brief_summary(brief_path: Path) -> None:
    print(f"\n{'='*60}")
    print("[结果] 次日执行卡片")
    print(f"路径：{brief_path}")

    if not brief_path.exists():
        print("[WARN] 执行卡片尚未生成，请检查 backtest.cli 输出。")
        return

    lines = brief_path.read_text(encoding="utf-8").splitlines()
    interesting_prefixes = (
        "- 信号日期：",
        "- 执行日期：",
        "- 风险模式：",
        "- 当前/目标仓位：",
    )
    printed = 0
    in_top_actions = False
    for line in lines:
        if line.startswith(interesting_prefixes):
            print(line)
            printed += 1
            continue
        if line.startswith("## Top 5 重点动作"):
            print(line)
            in_top_actions = True
            printed += 1
            continue
        if in_top_actions:
            if line.startswith("## ") and not line.startswith("## Top 5 重点动作"):
                break
            if line.strip():
                print(line)
                printed += 1
        if printed >= 12:
            break
```

- [ ] **Step 5: Run run_all tests**

Run:

```bash
python -m pytest tests/test_run_all.py -q
```

Expected: PASS.

- [ ] **Step 6: Run related backtest tests**

Run:

```bash
python -m pytest tests/backtest/test_engine.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Tasks 3 and 4**

```bash
git add run_all.py tests/test_run_all.py
git commit -m "功能: run_all接入卖出复评和执行信号单"
```

---

### Task 5: Update README and Verify the Full Suite

**Files:**
- Modify: `README.md`
- Test: existing tests

- [ ] **Step 1: Update README daily entrypoint description**

In `README.md`, update the `3.4 运行一键脚本` section so it says:

```markdown
### 3.4 运行日常交易闭环

在项目根目录执行：

~~~bash
python run_all.py
~~~

默认流程会依次执行：

1. 拉取最新 K 线数据
2. 量化初选
3. 导出候选 K 线图
4. 买入双模型复评
5. 打印买入推荐
6. 自动定位当前持仓快照并执行卖出复评
7. 生成次日执行信号单和盘前执行卡片

常用参数：

~~~bash
python run_all.py --skip-fetch
python run_all.py --start-from 3
python run_all.py --holdings data/backtest/quant_plus_ai/2026-04-24_2026-04-24/holdings_snapshot.json
python run_all.py --skip-sell-review
python run_all.py --skip-backtest-signal
~~~

如果没有找到持仓快照，脚本会按空仓处理并跳过卖出复评，不会阻断买入推荐。
~~~
```

Remove any duplicated older wording that says `run_all.py` only has four steps.

- [ ] **Step 2: Update README backtest section if needed**

Ensure the backtest examples still include:

```markdown
python run_all.py backtest --start 2026-03-01 --end 2026-03-10
python run_all.py backtest --mode quant_only --start 2026-01-01 --end 2026-01-31
```

Also keep this explanation:

```markdown
`quant_plus_ai` 是默认工作模式，也是推荐的日常研究模式；`quant_only` 仅建议用于内部调试。
```

- [ ] **Step 3: Run targeted tests**

Run:

```bash
python -m pytest tests/test_run_all.py tests/backtest/test_engine.py -q
```

Expected: PASS.

- [ ] **Step 4: Run the full suite**

Run:

```bash
python -m pytest -q
```

Expected: PASS. Current baseline before this plan is `109 passed`.

- [ ] **Step 5: Run help smoke test**

Run:

```bash
python run_all.py --help
```

Expected: output includes:

```text
--holdings
--skip-sell-review
--skip-backtest-signal
--allow-empty-holdings
```

- [ ] **Step 6: Commit documentation and final verification**

```bash
git add README.md
git commit -m "文档: 更新run_all交易闭环说明"
```

- [ ] **Step 7: Final status check**

Run:

```bash
git status --short --branch
git log --oneline -5
```

Expected:

```text
## feature/live-trading-research-closure...origin/feature/live-trading-research-closure [ahead N]
```

No uncommitted tracked changes.

---

## Plan Self-Review

Spec coverage:

- Daily default entrypoint: covered by Tasks 3 and 5.
- Backtest subcommand preservation: covered by Task 3 because the existing guard remains unchanged, and Task 5 keeps README examples.
- New CLI options: covered by Task 1.
- Holdings snapshot resolution: covered by Task 2.
- Sell review orchestration: covered by Task 3.
- One-day signal-sheet generation: covered by Tasks 3 and 4.
- Demo fallback protection: covered by Task 4 through `ensure_daily_signal_inputs`.
- Signal-card summary printing: covered by Task 4.
- Tests and docs: covered by Tasks 1 through 5.

Placeholder scan:

- The plan contains no unresolved placeholder markers or unspecified edge-case language.
- Each code-changing step includes concrete snippets or exact command examples.

Type consistency:

- `build_parser()` returns `argparse.ArgumentParser`.
- `load_latest_pick_date(root: Path = ROOT) -> str`.
- `validate_holdings_snapshot(path: Path) -> bool`.
- `resolve_holdings_snapshot(root: Path = ROOT, explicit_path: str | None = None) -> Path | None`.
- `run_daily_loop(...) -> None`.
- `ensure_daily_signal_inputs(root: Path, pick_date: str) -> None`.
- `build_signal_brief_path(root: Path, pick_date: str) -> Path`.
- `print_signal_brief_summary(brief_path: Path) -> None`.
