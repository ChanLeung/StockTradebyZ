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
