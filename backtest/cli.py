from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path

import pandas as pd
import yaml

from backtest.engine import run_backtest
from backtest.reporting import build_signal_sheet, summarize_backtest
from pipeline.fetch_reference_data import load_reference_series
from pipeline.reference_io import load_index_membership, load_reference_config, pick_primary_index
from pipeline.schemas import Candidate, CandidateRun
from agent.review_types import parse_sell_review
from trading.holdings_io import save_holdings_snapshot
from trading.risk import build_risk_signals

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="backtest.cli",
        description="研究闭环回测命令行入口",
    )
    parser.add_argument("--config", default="config/backtest.yaml", help="回测配置文件路径")
    parser.add_argument(
        "--mode",
        default="quant_only",
        choices=["quant_only", "quant_plus_ai"],
        help="运行模式：纯量化或量化 + AI",
    )
    parser.add_argument("--start", default="2026-01-01", help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end", default="2026-01-31", help="结束日期 YYYY-MM-DD")
    parser.add_argument("--output-dir", default=None, help="输出目录，默认读取配置")
    return parser


def load_backtest_config(path: str | Path) -> dict:
    config_path = Path(path)
    if not config_path.exists():
        return {}
    with config_path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def build_demo_bundle(start: str, end: str, mode: str) -> dict:
    dates = [date.strftime("%Y-%m-%d") for date in pd.bdate_range(start=start, end=end)]
    if len(dates) < 2:
        raise ValueError("回测至少需要 2 个交易日，才能完成收盘信号到次日开盘成交")

    codes = ["600000", "000001"]
    stock_to_index = {"600000": "HS300", "000001": "CSI2000"}
    benchmark_rows = []
    daily_candidates: dict[str, list[Candidate]] = {}
    next_open_prices: dict[str, dict[str, float]] = {}

    for idx, signal_date in enumerate(dates[:-1]):
        review_bonus = 0.2 if mode == "quant_plus_ai" else 0.0
        daily_candidates[signal_date] = [
            Candidate(
                code=code,
                date=signal_date,
                strategy="b1",
                close=10.0 + idx + code_idx,
                turnover_n=1000.0 + idx * 10 + code_idx,
                buy_review_score=4.5 - code_idx * 0.2 + review_bonus,
            )
            for code_idx, code in enumerate(codes)
        ]
        trade_date = dates[idx + 1]
        next_open_prices[trade_date] = {
            "600000": 10.5 + idx,
            "000001": 9.8 + idx,
        }
        benchmark_rows.append(
            {
                "date": trade_date,
                "HS300": 0.01 if idx % 2 == 0 else -0.005,
                "CSI2000": 0.008 if idx % 2 == 0 else -0.006,
            }
        )

    benchmark_returns = pd.DataFrame(benchmark_rows).set_index("date")
    return {
        "daily_candidates": daily_candidates,
        "next_open_prices": next_open_prices,
        "stock_to_index": stock_to_index,
        "benchmark_returns": benchmark_returns,
    }


def load_local_backtest_bundle(
    project_root: str | Path,
    *,
    start: str,
    end: str,
    mode: str,
    manual_risk_off: bool = False,
) -> dict:
    root = Path(project_root)
    candidates_dir = root / "data" / "candidates"
    raw_dir = root / "data" / "raw"
    review_dir = root / "data" / "review"
    review_sell_dir = root / "data" / "review_sell"
    reference_dir = root / "data" / "reference"

    candidate_files = sorted(candidates_dir.glob("candidates_*.json"))
    candidate_files = [
        path
        for path in candidate_files
        if path.stem != "candidates_latest" and start <= path.stem.replace("candidates_", "") <= end
    ]
    if not candidate_files:
        raise FileNotFoundError("指定区间内没有本地 candidates_YYYY-MM-DD.json 可用于回测")

    raw_cache: dict[str, pd.DataFrame] = {}
    daily_candidates: dict[str, list[Candidate]] = {}
    next_open_prices: dict[str, dict[str, float]] = {}
    stock_to_index: dict[str, str] = {}
    sell_decisions: dict[str, dict[str, str]] = {}
    trade_dates: set[str] = set()
    tracked_codes: set[str] = set()
    reference_config = load_reference_config(root / "config" / "reference_data.yaml")
    benchmark_priority = reference_config.get(
        "benchmark_priority",
        ["HS300", "CSI500", "CSI1000", "CSI2000", "ALLA"],
    )
    membership = load_index_membership(reference_dir / "index_membership.json")

    for candidate_file in candidate_files:
        run = CandidateRun.from_dict(json.loads(candidate_file.read_text(encoding="utf-8")))
        pick_date = run.pick_date
        if not (start <= pick_date <= end):
            continue

        trade_date = _find_next_trade_date(pick_date, run.candidates, raw_dir, raw_cache)
        if trade_date is None:
            continue

        tracked_codes.update(candidate.code for candidate in run.candidates)
        open_map: dict[str, float] = {}
        enriched_candidates: list[Candidate] = []
        date_sell_decisions: dict[str, str] = {}
        for tracked_code in sorted(tracked_codes):
            price_row = _find_price_row(tracked_code, trade_date, raw_dir, raw_cache)
            if price_row is not None:
                open_map[tracked_code] = float(price_row["open"])

        for candidate in run.candidates:
            if candidate.code not in open_map:
                continue

            enriched = _enrich_candidate(candidate, mode=mode, review_dir=review_dir / pick_date)
            enriched_candidates.append(enriched)
            stock_to_index[candidate.code] = pick_primary_index(
                candidate.code,
                membership,
                benchmark_priority,
            )
            sell_decision = _load_sell_decision(candidate.code, review_sell_dir / pick_date)
            if sell_decision is not None:
                date_sell_decisions[candidate.code] = sell_decision

        if not enriched_candidates:
            continue

        daily_candidates[pick_date] = enriched_candidates
        next_open_prices[trade_date] = open_map
        trade_dates.add(trade_date)
        if date_sell_decisions:
            sell_decisions[pick_date] = date_sell_decisions

    if not daily_candidates:
        raise FileNotFoundError("本地候选文件存在，但无法组装出有效的回测输入")

    reference = load_reference_series(reference_dir)
    benchmark_returns = _build_benchmark_returns(reference.get("benchmarks", pd.DataFrame()), trade_dates)
    risk_signals = build_risk_signals(
        sorted(daily_candidates.keys()),
        reference.get("benchmarks", pd.DataFrame()),
        reference.get("risk_proxies", pd.DataFrame()),
        reference_config.get("risk_thresholds", {}),
        manual_risk_off=manual_risk_off,
    )

    return {
        "daily_candidates": daily_candidates,
        "next_open_prices": next_open_prices,
        "stock_to_index": stock_to_index,
        "sell_decisions": sell_decisions,
        "risk_signals": risk_signals,
        "benchmark_returns": benchmark_returns,
    }


def build_backtest_bundle(
    project_root: str | Path,
    *,
    start: str,
    end: str,
    mode: str,
    manual_risk_off: bool = False,
) -> dict:
    try:
        return load_local_backtest_bundle(
            project_root,
            start=start,
            end=end,
            mode=mode,
            manual_risk_off=manual_risk_off,
        )
    except FileNotFoundError:
        return build_demo_bundle(start, end, mode)


def _load_raw_frame(code: str, raw_dir: Path, raw_cache: dict[str, pd.DataFrame]) -> pd.DataFrame:
    if code not in raw_cache:
        frame = pd.read_csv(raw_dir / f"{code}.csv")
        frame["date"] = frame["date"].astype(str)
        raw_cache[code] = frame.sort_values("date").reset_index(drop=True)
    return raw_cache[code]


def _find_next_trade_date(
    signal_date: str,
    candidates: list[Candidate],
    raw_dir: Path,
    raw_cache: dict[str, pd.DataFrame],
) -> str | None:
    next_dates: list[str] = []
    for candidate in candidates:
        frame = _load_raw_frame(candidate.code, raw_dir, raw_cache)
        future_dates = frame.loc[frame["date"] > signal_date, "date"]
        if not future_dates.empty:
            next_dates.append(str(future_dates.iloc[0]))
    return min(next_dates) if next_dates else None


def _find_price_row(
    code: str,
    trade_date: str,
    raw_dir: Path,
    raw_cache: dict[str, pd.DataFrame],
) -> dict | None:
    frame = _load_raw_frame(code, raw_dir, raw_cache)
    matched = frame.loc[frame["date"] == trade_date]
    if matched.empty:
        return None
    return matched.iloc[0].to_dict()


def _enrich_candidate(candidate: Candidate, *, mode: str, review_dir: Path) -> Candidate:
    if mode != "quant_plus_ai":
        return candidate

    review_path = review_dir / f"{candidate.code}.json"
    if not review_path.exists():
        return candidate

    review_data = json.loads(review_path.read_text(encoding="utf-8"))
    return replace(
        candidate,
        buy_review_score=float(review_data.get("total_score", 0.0)),
        buy_review_date=candidate.date,
        buy_prompt_version="buy_prompt.md",
    )


def _load_sell_decision(code: str, review_dir: Path) -> str | None:
    review_path = review_dir / f"{code}.json"
    if not review_path.exists():
        return None
    review = parse_sell_review(json.loads(review_path.read_text(encoding="utf-8")))
    return review.decision


def _build_benchmark_returns(benchmarks: pd.DataFrame, trade_dates: set[str]) -> pd.DataFrame:
    if benchmarks.empty:
        return pd.DataFrame({"ALLA": [0.0 for _ in sorted(trade_dates)]}, index=sorted(trade_dates))

    result = benchmarks.copy()
    if "ALLA" not in result.columns:
        result["ALLA"] = 0.0
    result = result.sort_index().reindex(sorted(trade_dates)).fillna(0.0)
    return result


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    config = load_backtest_config(args.config)
    output_root = PROJECT_ROOT / (args.output_dir or config.get("output_dir", "data/backtest"))
    data_bundle = build_backtest_bundle(
        PROJECT_ROOT,
        start=args.start,
        end=args.end,
        mode=args.mode,
        manual_risk_off=bool(config.get("risk", {}).get("manual_switch", False)),
    )
    result = run_backtest(config or {"max_positions": 10}, data_bundle)

    summary = summarize_backtest(result)
    summary["mode"] = args.mode
    summary["start"] = args.start
    summary["end"] = args.end
    signal_sheet = build_signal_sheet(result)

    output_dir = output_root / args.mode / f"{args.start}_{args.end}"
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = output_dir / "summary.json"
    signal_path = output_dir / "signal_sheet.json"
    snapshots_path = output_dir / "daily_snapshots.json"
    holdings_path = output_dir / "holdings_snapshot.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    signal_path.write_text(
        json.dumps(signal_sheet, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    snapshots_path.write_text(
        json.dumps([snapshot.to_dict() for snapshot in result.daily_snapshots], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    save_holdings_snapshot(
        holdings_path,
        as_of_date=result.daily_snapshots[-1].date if result.daily_snapshots else args.end,
        state=result.final_state,
    )

    print(f"[回测] 模式: {args.mode}")
    print(f"[回测] 区间: {args.start} -> {args.end}")
    print(f"[回测] 摘要: {summary_path}")
    print(f"[回测] 信号单: {signal_path}")
    print(f"[回测] 明细: {snapshots_path}")
    print(f"[回测] 持仓: {holdings_path}")


if __name__ == "__main__":
    main()
