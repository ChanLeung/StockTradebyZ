from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml

from backtest.engine import run_backtest
from backtest.reporting import build_signal_sheet, summarize_backtest
from pipeline.schemas import Candidate


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


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    config = load_backtest_config(args.config)
    output_root = Path(args.output_dir or config.get("output_dir", "data/backtest"))
    data_bundle = build_demo_bundle(args.start, args.end, args.mode)
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
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    signal_path.write_text(
        json.dumps(signal_sheet, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"[回测] 模式: {args.mode}")
    print(f"[回测] 区间: {args.start} -> {args.end}")
    print(f"[回测] 摘要: {summary_path}")
    print(f"[回测] 信号单: {signal_path}")


if __name__ == "__main__":
    main()
