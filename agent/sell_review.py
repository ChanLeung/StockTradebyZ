import argparse
from copy import deepcopy
from pathlib import Path

try:
    from agent.base_reviewer import BaseReviewer
    from agent.gemini_provider import GeminiJsonReviewer
    from agent.openai_review import OpenAISellReviewer
    from agent.review_config import SELL_REVIEW_CONFIG_PATH, _ROOT, load_review_config
    from agent.review_types import (
        aggregate_sell_model_results,
        derive_sell_confidence,
        derive_sell_risk_flags,
        map_sell_verdict_to_decision,
        parse_sell_signal_review,
    )
except ImportError:  # 兼容直接运行 python agent/sell_review.py
    from base_reviewer import BaseReviewer
    from gemini_provider import GeminiJsonReviewer
    from openai_review import OpenAISellReviewer
    from review_config import SELL_REVIEW_CONFIG_PATH, _ROOT, load_review_config
    from review_types import (
        aggregate_sell_model_results,
        derive_sell_confidence,
        derive_sell_risk_flags,
        map_sell_verdict_to_decision,
        parse_sell_signal_review,
    )


DEFAULT_SELL_PROVIDERS = {
    "gemini": {
        "model": "gemini-3.1-flash-lite-preview",
        "weight": 0.5,
    },
    "openai": {
        "model": "gpt-5.4",
        "weight": 0.5,
    },
}


def _merge_sell_providers(
    raw_providers: dict | None, fallback_gemini_model: str | None = None
) -> dict[str, dict]:
    providers = deepcopy(DEFAULT_SELL_PROVIDERS)
    if fallback_gemini_model:
        providers["gemini"]["model"] = str(fallback_gemini_model)
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


def _normalize_sell_payload(payload: dict, *, code: str) -> dict:
    parsed = parse_sell_signal_review(payload)
    decision = map_sell_verdict_to_decision(parsed.verdict)
    result = dict(payload)
    result.update(
        {
            "code": code,
            "total_score": parsed.total_score,
            "verdict": parsed.verdict,
            "signal_type": parsed.signal_type,
            "comment": parsed.comment,
            "decision": decision,
            "reasoning": str(payload.get("reasoning") or parsed.comment),
            "risk_flags": list(
                payload.get("risk_flags")
                or derive_sell_risk_flags(
                    signal_type=parsed.signal_type,
                    verdict=parsed.verdict,
                )
            ),
            "confidence": float(
                payload.get(
                    "confidence", derive_sell_confidence(parsed.total_score, decision)
                )
            ),
        }
    )
    return result


class GeminiSellReviewer(GeminiJsonReviewer):
    review_type = "sell"
    prompt_path = Path(__file__).resolve().parent / "prompts" / "sell_prompt.md"

    def build_user_text(self, code: str) -> str:
        return (
            f"股票代码：{code}\n\n"
            "以下是该持仓股票的 **日线图**，请根据系统提示判断当前是否出现短期卖点，"
            "并严格输出 JSON。"
        )

    @staticmethod
    def normalize_result(payload: dict, *, code: str) -> dict:
        return _normalize_sell_payload(payload, code=code)


class SellReviewer(BaseReviewer):
    review_type = "sell"
    prompt_path = Path(__file__).resolve().parent / "prompts" / "sell_prompt.md"

    def __init__(self, config):
        super().__init__(config)
        self.providers = config["providers"]
        self.weights = {
            provider_name: float(provider_cfg.get("weight", 0.0))
            for provider_name, provider_cfg in self.providers.items()
        }
        self.gemini_reviewer = GeminiSellReviewer(self._build_provider_config("gemini"))
        self.openai_reviewer = OpenAISellReviewer(self._build_provider_config("openai"))

    def _build_provider_config(self, provider_name: str) -> dict:
        config = dict(self.config)
        provider_cfg = self.providers[provider_name]
        config["model"] = provider_cfg["model"]
        return config

    @staticmethod
    def normalize_result(payload: dict, *, code: str) -> dict:
        return _normalize_sell_payload(payload, code=code)

    @staticmethod
    def aggregate_reviews(
        code: str, model_results: dict[str, dict], weights: dict[str, float]
    ) -> dict:
        return aggregate_sell_model_results(
            code=code,
            model_results=model_results,
            weights=weights,
        )

    def review_stock(self, code: str, day_chart: Path, prompt: str) -> dict:
        gemini_result = self.gemini_reviewer.review_stock(
            code=code, day_chart=day_chart, prompt=prompt
        )
        openai_result = self.openai_reviewer.review_stock(
            code=code, day_chart=day_chart, prompt=prompt
        )
        return self.aggregate_reviews(
            code=code,
            model_results={
                "gemini": gemini_result,
                "openai": openai_result,
            },
            weights=self.weights,
        )

    def generate_suggestion(
        self, pick_date: str, all_results: list[dict], min_score: float
    ) -> dict:
        _ = min_score
        ordered_results = sorted(
            all_results, key=lambda result: result.get("total_score", 0.0), reverse=True
        )
        hold_list = [
            result["code"]
            for result in ordered_results
            if result.get("decision") == "hold"
        ]
        sell_list = [
            result["code"]
            for result in ordered_results
            if result.get("decision") == "sell"
        ]
        watch_list = [
            result["code"]
            for result in ordered_results
            if result.get("verdict") == "WATCH"
        ]
        return {
            "date": pick_date,
            "total_reviewed": len(ordered_results),
            "hold_list": hold_list,
            "sell_list": sell_list,
            "watch_list": watch_list,
            "reviews": [
                {
                    "code": result["code"],
                    "decision": result.get("decision"),
                    "verdict": result.get("verdict"),
                    "total_score": result.get("total_score"),
                    "signal_type": result.get("signal_type"),
                    "comment": result.get("comment"),
                    **(
                        {
                            "gemini_score": result.get("model_reviews", {})
                            .get("gemini", {})
                            .get("total_score"),
                            "openai_score": result.get("model_reviews", {})
                            .get("openai", {})
                            .get("total_score"),
                        }
                        if "model_reviews" in result
                        else {}
                    ),
                }
                for result in ordered_results
            ],
        }


def load_sell_config(
    config_path: Path | None = None,
    *,
    candidates_path: Path | None = None,
) -> dict:
    config = load_review_config(
        config_path or SELL_REVIEW_CONFIG_PATH,
        prompt_path=str(SellReviewer.prompt_path.relative_to(_ROOT)),
        output_dir="data/review_sell",
    )
    config["providers"] = _merge_sell_providers(
        config.get("providers"),
        fallback_gemini_model=config.get("model"),
    )
    config["model"] = _build_ensemble_model_label(config["providers"])
    if candidates_path is not None:
        config["candidates"] = candidates_path
    return config


def main() -> None:
    parser = argparse.ArgumentParser(description="双模型卖出图表复评")
    parser.add_argument(
        "--config",
        default=str(SELL_REVIEW_CONFIG_PATH),
        help="配置文件路径（默认 config/sell_review.yaml）",
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
