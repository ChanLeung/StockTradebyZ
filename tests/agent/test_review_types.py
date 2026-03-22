from agent.buy_review import BuyReviewer
from agent.review_types import parse_buy_review, parse_sell_review
from agent.sell_review import SellReviewer


def test_parse_buy_review_keeps_total_score_and_verdict():
    parsed = parse_buy_review(
        {
            "total_score": 4.2,
            "verdict": "PASS",
            "signal_type": "trend_start",
            "comment": "趋势健康，量价配合较好。",
        }
    )

    assert parsed.total_score == 4.2
    assert parsed.verdict == "PASS"


def test_parse_sell_review_requires_hold_or_sell():
    parsed = parse_sell_review(
        {
            "decision": "sell",
            "reasoning": "趋势破坏，量价转弱。",
            "risk_flags": ["trend_break"],
            "confidence": 0.8,
        }
    )

    assert parsed.decision == "sell"
    assert parsed.risk_flags == ["trend_break"]


def test_buy_and_sell_reviewers_use_expected_review_type():
    assert BuyReviewer.review_type == "buy"
    assert SellReviewer.review_type == "sell"
