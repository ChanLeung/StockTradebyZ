from dataclasses import dataclass


@dataclass
class BuyReviewResult:
    total_score: float
    verdict: str
    signal_type: str
    comment: str


@dataclass
class SellReviewResult:
    decision: str
    reasoning: str
    risk_flags: list[str]
    confidence: float


def map_buy_score_to_verdict(score: float) -> str:
    if score >= 4.0:
        return "PASS"
    if score >= 3.2:
        return "WATCH"
    return "FAIL"


def parse_buy_review(payload: dict) -> BuyReviewResult:
    return BuyReviewResult(
        total_score=float(payload["total_score"]),
        verdict=str(payload["verdict"]),
        signal_type=str(payload.get("signal_type", "")),
        comment=str(payload.get("comment", "")),
    )


def parse_sell_review(payload: dict) -> SellReviewResult:
    return SellReviewResult(
        decision=str(payload["decision"]),
        reasoning=str(payload.get("reasoning", "")),
        risk_flags=list(payload.get("risk_flags", [])),
        confidence=float(payload.get("confidence", 0.0)),
    )


def aggregate_buy_model_results(code: str, model_results: dict[str, dict], weights: dict[str, float]) -> dict:
    if not model_results:
        raise ValueError("缺少可聚合的买入复评结果")

    normalized_weights = {
        provider: float(weights.get(provider, 0.0))
        for provider in model_results
    }
    total_weight = sum(normalized_weights.values())
    if total_weight <= 0:
        raise ValueError("买入复评权重之和必须大于 0")

    normalized_weights = {
        provider: weight / total_weight
        for provider, weight in normalized_weights.items()
    }
    parsed_results = {
        provider: parse_buy_review(payload)
        for provider, payload in model_results.items()
    }
    weighted_score = round(
        sum(parsed_results[provider].total_score * normalized_weights[provider] for provider in parsed_results),
        4,
    )

    top_provider = max(
        parsed_results,
        key=lambda provider: parsed_results[provider].total_score,
    )
    signal_types = {
        parsed.signal_type
        for parsed in parsed_results.values()
        if parsed.signal_type
    }
    if len(signal_types) == 1:
        final_signal_type = next(iter(signal_types))
    else:
        final_signal_type = parsed_results[top_provider].signal_type or "mixed"

    return {
        "code": code,
        "total_score": weighted_score,
        "verdict": map_buy_score_to_verdict(weighted_score),
        "signal_type": final_signal_type,
        "comment": (
            f"综合评分 {weighted_score:.2f}。"
            + " ".join(
                f"{provider.capitalize()}：{parsed_results[provider].comment}"
                for provider in parsed_results
                if parsed_results[provider].comment
            )
        ).strip(),
        "model_reviews": {
            provider: dict(payload)
            for provider, payload in model_results.items()
        },
        "ensemble": {
            "strategy": "weighted_average",
            "weights": normalized_weights,
            "score_breakdown": {
                provider: parsed.total_score
                for provider, parsed in parsed_results.items()
            },
        },
    }
