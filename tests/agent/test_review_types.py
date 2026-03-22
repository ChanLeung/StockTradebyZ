from agent.review_types import parse_buy_review


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
