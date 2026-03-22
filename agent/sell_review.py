import argparse
from pathlib import Path

try:
    from agent.gemini_review import GeminiJsonReviewer, _ROOT, load_config
    from agent.review_types import parse_sell_review
except ImportError:  # 兼容直接运行 python agent/sell_review.py
    from gemini_review import GeminiJsonReviewer, _ROOT, load_config
    from review_types import parse_sell_review


class SellReviewer(GeminiJsonReviewer):
    review_type = "sell"
    prompt_path = Path(__file__).resolve().parent / "prompts" / "sell_prompt.md"

    def build_user_text(self, code: str) -> str:
        return (
            f"股票代码：{code}\n\n"
            "以下是该持仓股票的 **日线图**，请根据系统提示判断继续持有还是卖出，"
            "并严格输出 JSON。"
        )

    @staticmethod
    def normalize_result(payload: dict, *, code: str) -> dict:
        parsed = parse_sell_review(payload)
        return {
            "code": code,
            "decision": parsed.decision,
            "reasoning": parsed.reasoning,
            "risk_flags": parsed.risk_flags,
            "confidence": parsed.confidence,
        }

    def generate_suggestion(self, pick_date: str, all_results: list[dict], min_score: float) -> dict:
        _ = min_score
        hold_list = [result["code"] for result in all_results if result.get("decision") == "hold"]
        sell_list = [result["code"] for result in all_results if result.get("decision") == "sell"]
        return {
            "date": pick_date,
            "total_reviewed": len(all_results),
            "hold_list": hold_list,
            "sell_list": sell_list,
        }


def load_sell_config(
    config_path: Path | None = None,
    *,
    candidates_path: Path | None = None,
) -> dict:
    cfg_path = config_path or (_ROOT / "config" / "gemini_sell_review.yaml")
    config = load_config(
        cfg_path,
        prompt_path=str(SellReviewer.prompt_path.relative_to(_ROOT)),
        output_dir="data/review_sell",
    )
    if candidates_path is not None:
        config["candidates"] = candidates_path
    return config


def main() -> None:
    parser = argparse.ArgumentParser(description="Gemini 卖出图表复评")
    parser.add_argument(
        "--config",
        default=str(_ROOT / "config" / "gemini_sell_review.yaml"),
        help="配置文件路径（默认 config/gemini_sell_review.yaml）",
    )
    parser.add_argument(
        "--input",
        default=None,
        help="输入文件路径，可覆盖 candidates 配置",
    )
    args = parser.parse_args()

    reviewer = SellReviewer(
        load_sell_config(
            Path(args.config),
            candidates_path=Path(args.input) if args.input else None,
        )
    )
    reviewer.run()


if __name__ == "__main__":
    main()
