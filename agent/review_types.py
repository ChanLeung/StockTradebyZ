from dataclasses import dataclass


@dataclass
class BuyReviewResult:
    total_score: float
    verdict: str
    signal_type: str
    comment: str


def parse_buy_review(payload: dict) -> BuyReviewResult:
    return BuyReviewResult(
        total_score=float(payload["total_score"]),
        verdict=str(payload["verdict"]),
        signal_type=str(payload.get("signal_type", "")),
        comment=str(payload.get("comment", "")),
    )
