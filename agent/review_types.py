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


@dataclass
class SellSignalReviewResult:
    total_score: float
    verdict: str
    signal_type: str
    comment: str


PROVIDER_LABELS = {
    "gemini": "Gemini",
    "openai": "OpenAI",
}


def map_buy_score_to_verdict(score: float) -> str:
    if score >= 4.0:
        return "PASS"
    if score >= 3.2:
        return "WATCH"
    return "FAIL"


def map_sell_score_to_verdict(score: float) -> str:
    return map_buy_score_to_verdict(score)


def map_sell_verdict_to_decision(verdict: str) -> str:
    return "sell" if str(verdict).upper() == "PASS" else "hold"


def derive_sell_confidence(total_score: float, decision: str) -> float:
    if decision == "sell":
        raw_confidence = float(total_score) / 5.0
    else:
        raw_confidence = (5.0 - float(total_score)) / 5.0
    return round(max(0.0, min(raw_confidence, 1.0)), 4)


def parse_buy_review(payload: dict) -> BuyReviewResult:
    return BuyReviewResult(
        total_score=float(payload["total_score"]),
        verdict=str(payload["verdict"]),
        signal_type=str(payload.get("signal_type", "")),
        comment=str(payload.get("comment", "")),
    )


def parse_sell_signal_review(payload: dict) -> SellSignalReviewResult:
    return SellSignalReviewResult(
        total_score=float(payload["total_score"]),
        verdict=str(payload["verdict"]),
        signal_type=str(payload.get("signal_type", "")),
        comment=str(payload.get("comment", "")),
    )


def derive_sell_risk_flags(
    *,
    signal_type: str,
    verdict: str,
    model_results: dict[str, dict] | None = None,
) -> list[str]:
    flags: list[str] = []
    normalized_verdict = str(verdict).upper()

    if normalized_verdict in {"PASS", "WATCH"} and signal_type:
        flags.append(str(signal_type))

    if model_results:
        signal_types = {
            parse_sell_signal_review(payload).signal_type
            for payload in model_results.values()
            if payload.get("signal_type")
        }
        if len(signal_types) > 1:
            flags.append("model_disagreement")

    return flags


def parse_sell_review(payload: dict) -> SellReviewResult:
    if "decision" not in payload:
        scored = parse_sell_signal_review(payload)
        decision = map_sell_verdict_to_decision(scored.verdict)
        return SellReviewResult(
            decision=decision,
            reasoning=str(payload.get("reasoning") or scored.comment),
            risk_flags=list(
                payload.get("risk_flags")
                or derive_sell_risk_flags(
                    signal_type=scored.signal_type,
                    verdict=scored.verdict,
                )
            ),
            confidence=float(
                payload.get("confidence", derive_sell_confidence(scored.total_score, decision))
            ),
        )

    return SellReviewResult(
        decision=str(payload["decision"]),
        reasoning=str(payload.get("reasoning", "")),
        risk_flags=list(payload.get("risk_flags", [])),
        confidence=float(payload.get("confidence", 0.0)),
    )


def _normalize_weights(model_results: dict[str, dict], weights: dict[str, float]) -> dict[str, float]:
    normalized_weights = {
        provider: float(weights.get(provider, 0.0))
        for provider in model_results
    }
    total_weight = sum(normalized_weights.values())
    if total_weight <= 0:
        raise ValueError("模型权重之和必须大于 0")
    return {
        provider: weight / total_weight
        for provider, weight in normalized_weights.items()
    }


def _resolve_weighted_signal_type(parsed_results: dict[str, BuyReviewResult | SellSignalReviewResult]) -> str:
    signal_types = {
        parsed.signal_type
        for parsed in parsed_results.values()
        if parsed.signal_type
    }
    if len(signal_types) == 1:
        return next(iter(signal_types))
    top_provider = max(
        parsed_results,
        key=lambda provider: parsed_results[provider].total_score,
    )
    return parsed_results[top_provider].signal_type or "mixed"


def _build_weighted_comment(
    weighted_score: float,
    parsed_results: dict[str, BuyReviewResult | SellSignalReviewResult],
) -> str:
    parts = [f"综合评分 {weighted_score:.2f}。"]
    for provider, parsed in parsed_results.items():
        if parsed.comment:
            parts.append(f"{PROVIDER_LABELS.get(provider, provider.capitalize())}：{parsed.comment}")
    if len({parsed.signal_type for parsed in parsed_results.values() if parsed.signal_type}) > 1:
        parts.append("两模型对信号类型存在分歧。")
    return " ".join(part.strip() for part in parts if part.strip()).strip()


def aggregate_buy_model_results(code: str, model_results: dict[str, dict], weights: dict[str, float]) -> dict:
    if not model_results:
        raise ValueError("缺少可聚合的买入复评结果")

    normalized_weights = _normalize_weights(model_results, weights)
    parsed_results = {
        provider: parse_buy_review(payload)
        for provider, payload in model_results.items()
    }
    weighted_score = round(
        sum(parsed_results[provider].total_score * normalized_weights[provider] for provider in parsed_results),
        4,
    )

    return {
        "code": code,
        "total_score": weighted_score,
        "verdict": map_buy_score_to_verdict(weighted_score),
        "signal_type": _resolve_weighted_signal_type(parsed_results),
        "comment": _build_weighted_comment(weighted_score, parsed_results),
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


def aggregate_sell_model_results(code: str, model_results: dict[str, dict], weights: dict[str, float]) -> dict:
    if not model_results:
        raise ValueError("缺少可聚合的卖出复评结果")

    normalized_weights = _normalize_weights(model_results, weights)
    parsed_results = {
        provider: parse_sell_signal_review(payload)
        for provider, payload in model_results.items()
    }
    weighted_score = round(
        sum(parsed_results[provider].total_score * normalized_weights[provider] for provider in parsed_results),
        4,
    )
    verdict = map_sell_score_to_verdict(weighted_score)
    signal_type = _resolve_weighted_signal_type(parsed_results)
    decision = map_sell_verdict_to_decision(verdict)
    comment = _build_weighted_comment(weighted_score, parsed_results)

    return {
        "code": code,
        "total_score": weighted_score,
        "verdict": verdict,
        "signal_type": signal_type,
        "comment": comment,
        "decision": decision,
        "reasoning": comment,
        "risk_flags": derive_sell_risk_flags(
            signal_type=signal_type,
            verdict=verdict,
            model_results=model_results,
        ),
        "confidence": derive_sell_confidence(weighted_score, decision),
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
