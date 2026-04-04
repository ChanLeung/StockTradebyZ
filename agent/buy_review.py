import argparse
from copy import deepcopy
from pathlib import Path

try:
    from agent.base_reviewer import BaseReviewer
    from agent.gemini_provider import GeminiBuyReviewer
    from agent.openai_review import OpenAIBuyReviewer
    from agent.review_config import BUY_REVIEW_CONFIG_PATH, _ROOT, load_review_config
    from agent.review_types import aggregate_buy_model_results, parse_buy_review
except ImportError:  # 兼容直接运行 python agent/buy_review.py
    from base_reviewer import BaseReviewer
    from gemini_provider import GeminiBuyReviewer
    from openai_review import OpenAIBuyReviewer
    from review_config import BUY_REVIEW_CONFIG_PATH, _ROOT, load_review_config
    from review_types import aggregate_buy_model_results, parse_buy_review


DEFAULT_BUY_PROVIDERS = {
    "gemini": {
        "model": "gemini-3.1-flash-lite-preview",
        "weight": 0.5,
    },
    "openai": {
        "model": "gpt-5.4",
        "weight": 0.5,
    },
}


def _merge_buy_providers(raw_providers: dict | None) -> dict[str, dict]:
    providers = deepcopy(DEFAULT_BUY_PROVIDERS)
    for name, overrides in (raw_providers or {}).items():
        if name not in providers:
            providers[name] = {}
        providers[name].update(overrides or {})
    return providers


def _build_ensemble_model_label(providers: dict[str, dict]) -> str:
    return "ensemble:" + "|".join(
        f"{name}={provider.get('model', '')}@{float(provider.get('weight', 0.0)):.4f}"
        for name, provider in providers.items()
    )


class BuyReviewer(BaseReviewer):
    review_type = "buy"
    prompt_path = Path(__file__).resolve().parent / "prompts" / "buy_prompt.md"

    def __init__(self, config):
        super().__init__(config)
        self.providers = config["providers"]
        self.weights = {
            provider_name: float(provider_cfg.get("weight", 0.0))
            for provider_name, provider_cfg in self.providers.items()
        }
        self.gemini_reviewer = GeminiBuyReviewer(self._build_provider_config("gemini"))
        self.openai_reviewer = OpenAIBuyReviewer(self._build_provider_config("openai"))

    def _build_provider_config(self, provider_name: str) -> dict:
        config = dict(self.config)
        provider_cfg = self.providers[provider_name]
        config["model"] = provider_cfg["model"]
        return config

    @staticmethod
    def normalize_result(payload: dict, *, code: str) -> dict:
        parsed = parse_buy_review(payload)
        result = dict(payload)
        result.update(
            {
                "code": code,
                "total_score": parsed.total_score,
                "verdict": parsed.verdict,
                "signal_type": parsed.signal_type,
                "comment": parsed.comment,
            }
        )
        return result

    @staticmethod
    def aggregate_reviews(code: str, model_results: dict[str, dict], weights: dict[str, float]) -> dict:
        return aggregate_buy_model_results(
            code=code,
            model_results=model_results,
            weights=weights,
        )

    def review_stock(self, code: str, day_chart: Path, prompt: str) -> dict:
        gemini_result = self.gemini_reviewer.review_stock(code=code, day_chart=day_chart, prompt=prompt)
        openai_result = self.openai_reviewer.review_stock(code=code, day_chart=day_chart, prompt=prompt)
        return self.aggregate_reviews(
            code=code,
            model_results={
                "gemini": gemini_result,
                "openai": openai_result,
            },
            weights=self.weights,
        )


def load_buy_config(
    config_path: Path | None = None,
    *,
    candidates_path: Path | None = None,
) -> dict:
    config = load_review_config(
        config_path or BUY_REVIEW_CONFIG_PATH,
        prompt_path=str(BuyReviewer.prompt_path.relative_to(_ROOT)),
        output_dir="data/review",
    )
    config["providers"] = _merge_buy_providers(config.get("providers"))
    config["model"] = _build_ensemble_model_label(config["providers"])
    if candidates_path is not None:
        config["candidates"] = candidates_path
    return config


def main() -> None:
    parser = argparse.ArgumentParser(description="双模型买入图表复评")
    parser.add_argument(
        "--config",
        default=str(BUY_REVIEW_CONFIG_PATH),
        help="配置文件路径（默认 config/buy_review.yaml）",
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
