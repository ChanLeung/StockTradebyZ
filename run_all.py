"""
run_all.py
~~~~~~~~~~
一键运行完整交易选股流程：

  步骤 1  pipeline/fetch_kline.py   — 拉取最新 K 线数据
  步骤 2  pipeline/cli.py preselect — 量化初选，生成候选列表
  步骤 3  dashboard/export_kline_charts.py — 导出候选股 K 线图
  步骤 4  agent/buy_review.py       — 双模型图表分析评分
  步骤 5  打印推荐购买的股票
  步骤 6  agent/sell_review.py      — 当前持仓卖出复评
  步骤 7  backtest/cli.py           — 生成次日执行信号单

用法：
    python run_all.py
    python run_all.py --skip-fetch     # 跳过行情下载（已有最新数据时）
    python run_all.py --start-from 3   # 从第 3 步开始（跳过前两步）
    python run_all.py backtest --mode quant_only
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from collections.abc import Callable
from datetime import date
from pathlib import Path

from project_env import load_project_env

ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable  # 与当前进程同一个 Python 解释器
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
        choices=range(1, 8),
        default=1,
        metavar="N",
        help="从第 N 步开始执行（1~7），跳过前面的步骤",
    )
    parser.add_argument(
        "--holdings",
        default=None,
        help="当前持仓快照路径，用于卖出复评和信号单初始持仓",
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
        help="兼容参数：没有持仓快照时默认也会继续，按空仓处理",
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
    return max(candidates, key=lambda path: (path.stat().st_mtime, str(path)))


def _load_daily_candidates(root: Path, pick_date: str) -> list[dict]:
    candidates_path = root / "data" / "candidates" / f"candidates_{pick_date}.json"
    try:
        payload = json.loads(candidates_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[ERROR] 当日候选文件读取失败，无法生成执行信号单：{candidates_path} ({exc})")
        raise SystemExit(1) from exc

    candidates = payload.get("candidates", [])
    return [candidate for candidate in candidates if isinstance(candidate, dict)]


def _parse_csv_date(value: object) -> date | None:
    text = str(value or "").strip()
    if len(text) >= 10:
        text = text[:10]
    elif len(text) == 8 and text.isdigit():
        text = f"{text[:4]}-{text[4:6]}-{text[6:]}"
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _raw_has_trade_date_after(raw_path: Path, pick_date: str) -> bool:
    signal_date = _parse_csv_date(pick_date)
    if signal_date is None:
        return False

    try:
        with raw_path.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            if "date" not in (reader.fieldnames or []):
                return False
            return any(
                raw_date is not None and raw_date > signal_date
                for raw_date in (_parse_csv_date(row.get("date")) for row in reader)
            )
    except OSError:
        return False


def _holdings_snapshot_is_empty(path: Path) -> bool:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return not payload["state"]["positions"]


def _load_holdings_position_codes(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    positions = payload.get("state", {}).get("positions", [])
    return [
        str(position.get("code", "")).strip()
        for position in positions
        if isinstance(position, dict) and str(position.get("code", "")).strip()
    ]


def ensure_daily_signal_inputs(
    root: Path,
    pick_date: str,
    additional_codes: list[str] | None = None,
) -> None:
    candidates_path = root / "data" / "candidates" / f"candidates_{pick_date}.json"
    suggestion_path = root / "data" / "review" / pick_date / "suggestion.json"

    if not candidates_path.exists():
        print(f"[ERROR] 找不到当日候选文件，无法生成执行信号单：{candidates_path}")
        raise SystemExit(1)
    if not suggestion_path.exists():
        print(f"[ERROR] 找不到当日买入建议，无法生成执行信号单：{suggestion_path}")
        raise SystemExit(1)

    candidates = _load_daily_candidates(root, pick_date)
    signal_codes = list(
        dict.fromkeys(
            [
                *[
                    str(candidate.get("code", "")).strip()
                    for candidate in candidates
                    if candidate.get("code")
                ],
                *(additional_codes or []),
            ]
        )
    )
    missing_raw_files = [
        root / "data" / "raw" / f"{code}.csv"
        for code in signal_codes
        if not (root / "data" / "raw" / f"{code}.csv").exists()
    ]
    if missing_raw_files:
        missing_list = "、".join(str(path) for path in missing_raw_files)
        print(f"[ERROR] 缺少原始K线数据，无法生成执行信号单：{missing_list}")
        raise SystemExit(1)

    missing_future_data = [
        root / "data" / "raw" / f"{code}.csv"
        for code in signal_codes
        if not _raw_has_trade_date_after(
            root / "data" / "raw" / f"{code}.csv",
            pick_date,
        )
    ]
    if missing_future_data:
        missing_list = "、".join(str(path) for path in missing_future_data)
        print(f"[ERROR] 缺少后续交易日K线数据，无法生成执行信号单：{missing_list}")
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


def print_signal_brief_summary(brief_path: Path) -> None:
    if not brief_path.exists():
        print(f"[WARN] 未找到次日执行卡片摘要：{brief_path}")
        return

    text = brief_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    key_prefixes = (
        "- 信号日期：",
        "- 执行日期：",
        "- 风险模式：",
        "- 当前/目标仓位：",
    )

    print(f"\n{'='*60}")
    print("[步骤] 次日执行卡片")
    print(f"  路径：{brief_path}")
    print(f"{'='*60}")

    for line in lines:
        if line.startswith(key_prefixes):
            print(line.removeprefix("- "))

    in_top_actions = False
    for line in lines:
        if line.startswith("## Top ") and "重点动作" in line:
            print(f"\n{line.removeprefix('## ')}")
            in_top_actions = True
            continue
        if in_top_actions and line.startswith("## "):
            break
        if in_top_actions and line.strip():
            print(line)


def _run(step_name: str, cmd: list[str]) -> None:
    """运行子进程，失败时终止整个流程。"""
    print(f"\n{'='*60}")
    print(f"[步骤] {step_name}")
    print(f"  命令: {' '.join(cmd)}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        print(f"\n[ERROR] 步骤「{step_name}」返回非零退出码 {result.returncode}，流程已中止。")
        sys.exit(result.returncode)


def _print_recommendations() -> None:
    """读取最新 suggestion.json，打印推荐购买的股票。"""
    candidates_file = ROOT / "data" / "candidates" / "candidates_latest.json"
    if not candidates_file.exists():
        print("[ERROR] 找不到 candidates_latest.json，无法定位 suggestion.json。")
        return

    with open(candidates_file, encoding="utf-8") as f:
        pick_date: str = json.load(f).get("pick_date", "")

    if not pick_date:
        print("[ERROR] candidates_latest.json 中未设置 pick_date。")
        return

    suggestion_file = ROOT / "data" / "review" / pick_date / "suggestion.json"
    if not suggestion_file.exists():
        print(f"[ERROR] 找不到评分汇总文件：{suggestion_file}")
        return

    with open(suggestion_file, encoding="utf-8") as f:
        suggestion: dict = json.load(f)

    recommendations: list[dict] = suggestion.get("recommendations", [])
    min_score: float = suggestion.get("min_score_threshold", 0)
    total: int = suggestion.get("total_reviewed", 0)

    print(f"\n{'='*60}")
    print(f"  选股日期：{pick_date}")
    print(f"  评审总数：{total} 只   推荐门槛：score ≥ {min_score}")
    print(f"{'='*60}")

    if not recommendations:
        print("  暂无达标推荐股票。")
        return

    header = f"{'排名':>4}  {'代码':>8}  {'总分':>6}  {'信号':>10}  {'研判':>6}  备注"
    print(header)
    print("-" * len(header))
    for r in recommendations:
        rank        = r.get("rank",        "?")
        code        = r.get("code",        "?")
        score       = r.get("total_score", "?")
        signal_type = r.get("signal_type", "")
        verdict     = r.get("verdict",     "")
        comment     = r.get("comment",     "")
        score_str   = f"{score:.1f}" if isinstance(score, (int, float)) else str(score)
        print(f"{rank:>4}  {code:>8}  {score_str:>6}  {signal_type:>10}  {verdict:>6}  {comment}")

    print(f"\n✅ 推荐购买 {len(recommendations)} 只股票（详见 {suggestion_file}）")


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
    holdings_path: Path | None = None

    if args.skip_fetch and start == 1:
        start = 2

    # ── 步骤 1/7：拉取 K 线数据 ───────────────────────────────────────
    if start <= 1:
        run_step(
            "1/7  拉取 K 线数据（fetch_kline）",
            [python, "-m", "pipeline.fetch_kline"],
        )

    # ── 步骤 2/7：量化初选 ───────────────────────────────────────────
    if start <= 2:
        run_step(
            "2/7  量化初选（cli preselect）",
            [python, "-m", "pipeline.cli", "preselect"],
        )

    # ── 步骤 3/7：导出 K 线图 ────────────────────────────────────────
    if start <= 3:
        run_step(
            "3/7  导出 K 线图（export_kline_charts）",
            [python, str(root / "dashboard" / "export_kline_charts.py")],
        )

    # ── 步骤 4/7：双模型图表分析 ─────────────────────────────────────
    if start <= 4:
        run_step(
            "4/7  双模型图表分析（buy_review）",
            [python, "-m", "agent.buy_review"],
        )

    # ── 步骤 5/7：打印推荐结果 ───────────────────────────────────────
    if start <= 5:
        print(f"\n{'='*60}")
        print("[步骤] 5/7  推荐购买的股票")
        print_recommendations()

    # ── 步骤 6/7：持仓卖出复评 ───────────────────────────────────────
    if start <= 6:
        if args.skip_sell_review:
            print("[步骤] 6/7  已跳过持仓卖出复评。")
        else:
            holdings_path = resolve_holdings_snapshot(root, args.holdings)
            if holdings_path is None:
                if args.allow_empty_holdings:
                    print("[步骤] 6/7  未找到持仓快照，按空仓处理，跳过持仓卖出复评。")
                else:
                    print("[步骤] 6/7  未找到持仓快照，跳过持仓卖出复评。")
            elif _holdings_snapshot_is_empty(holdings_path):
                print("[步骤] 6/7  持仓快照为空仓，跳过持仓卖出复评。")
            else:
                run_step(
                    "6/7  持仓卖出复评（sell_review）",
                    [python, "-m", "agent.sell_review", "--input", str(holdings_path)],
                )

    # ── 步骤 7/7：单日回测生成次日执行信号单 ─────────────────────────
    if start > 7:
        return
    if args.skip_backtest_signal:
        print("[步骤] 7/7  已跳过次日执行信号单生成。")
        return
    if holdings_path is None:
        holdings_path = resolve_holdings_snapshot(root, args.holdings)

    pick_date = load_latest_pick_date(root)
    holding_codes = _load_holdings_position_codes(holdings_path) if holdings_path is not None else []
    ensure_daily_signal_inputs(root, pick_date, holding_codes)
    has_current_holdings = bool(holding_codes)
    if not _load_daily_candidates(root, pick_date) and not has_current_holdings:
        print("[步骤] 7/7  当天没有买入候选，跳过次日执行信号单生成。")
        return

    backtest_cmd = [
        python,
        "-m",
        "backtest.cli",
        "--mode",
        "quant_plus_ai",
        "--start",
        pick_date,
        "--end",
        pick_date,
    ]
    if holdings_path is not None:
        backtest_cmd.extend(["--initial-holdings", str(holdings_path)])

    run_step(
        "7/7  生成次日执行信号单（backtest.cli）",
        backtest_cmd,
    )
    signal_brief_path = build_signal_brief_path(root, pick_date)
    (print_signal_summary or print_signal_brief_summary)(signal_brief_path)


def main() -> None:
    load_project_env()

    if len(sys.argv) > 1 and sys.argv[1] == "backtest":
        _run(
            "回测（backtest.cli）",
            [PYTHON, "-m", "backtest.cli", *sys.argv[2:]],
        )
        return

    parser = build_parser()
    args = parser.parse_args()

    run_daily_loop(args)


if __name__ == "__main__":
    main()
