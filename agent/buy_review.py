import argparse
from pathlib import Path

try:
    from agent.gemini_review import GeminiReviewer, _ROOT, load_config
except ImportError:  # 兼容直接运行 python agent/buy_review.py
    from gemini_review import GeminiReviewer, _ROOT, load_config


class BuyReviewer(GeminiReviewer):
    review_type = "buy"
    prompt_path = Path(__file__).resolve().parent / "prompts" / "buy_prompt.md"


def load_buy_config(config_path: Path | None = None) -> dict:
    return load_config(
        config_path,
        prompt_path=str(BuyReviewer.prompt_path.relative_to(_ROOT)),
        output_dir="data/review",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Gemini 买入图表复评")
    parser.add_argument(
        "--config",
        default=str(_ROOT / "config" / "gemini_review.yaml"),
        help="配置文件路径（默认 config/gemini_review.yaml）",
    )
    args = parser.parse_args()

    reviewer = BuyReviewer(load_buy_config(Path(args.config)))
    reviewer.run()


if __name__ == "__main__":
    main()
