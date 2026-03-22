import argparse
from pathlib import Path

try:
    from agent.gemini_review import GeminiReviewer, _ROOT, load_config
except ImportError:  # 兼容直接运行 python agent/buy_review.py
    from gemini_review import GeminiReviewer, _ROOT, load_config


class BuyReviewer(GeminiReviewer):
    review_type = "buy"
    prompt_path = Path(__file__).resolve().parent / "prompts" / "buy_prompt.md"


def load_buy_config(
    config_path: Path | None = None,
    *,
    candidates_path: Path | None = None,
) -> dict:
    config = load_config(
        config_path,
        prompt_path=str(BuyReviewer.prompt_path.relative_to(_ROOT)),
        output_dir="data/review",
    )
    if candidates_path is not None:
        config["candidates"] = candidates_path
    return config


def main() -> None:
    parser = argparse.ArgumentParser(description="Gemini 买入图表复评")
    parser.add_argument(
        "--config",
        default=str(_ROOT / "config" / "gemini_review.yaml"),
        help="配置文件路径（默认 config/gemini_review.yaml）",
    )
    parser.add_argument(
        "--input",
        default=None,
        help="输入文件路径，可覆盖 candidates 配置",
    )
    args = parser.parse_args()

    reviewer = BuyReviewer(
        load_buy_config(
            Path(args.config),
            candidates_path=Path(args.input) if args.input else None,
        )
    )
    reviewer.run()


if __name__ == "__main__":
    main()
