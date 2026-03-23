from pathlib import Path

from agent.buy_review import BuyReviewer, load_buy_config
from agent.gemini_review import load_config
from agent.review_types import parse_buy_review, parse_sell_review
from agent.sell_review import SellReviewer, load_sell_config


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


def test_buy_and_sell_reviewers_use_dedicated_prompt_files():
    assert BuyReviewer.prompt_path.name == "buy_prompt.md"
    assert SellReviewer.prompt_path.name == "sell_prompt.md"


def test_legacy_gemini_config_defaults_to_buy_prompt():
    config = load_config(Path("config/gemini_review.yaml"))

    assert config["prompt_path"].name == "buy_prompt.md"


def test_buy_reviewer_normalizes_buy_payload():
    result = BuyReviewer.normalize_result(
        {
            "total_score": 4.2,
            "verdict": "PASS",
            "signal_type": "trend_start",
            "comment": "趋势健康。",
        },
        code="600000",
    )

    assert result["code"] == "600000"
    assert result["total_score"] == 4.2
    assert result["verdict"] == "PASS"


def test_sell_reviewer_normalizes_sell_payload():
    result = SellReviewer.normalize_result(
        {
            "decision": "sell",
            "reasoning": "趋势破坏。",
            "risk_flags": ["trend_break"],
            "confidence": 0.8,
        },
        code="600000",
    )

    assert result["code"] == "600000"
    assert result["decision"] == "sell"
    assert result["risk_flags"] == ["trend_break"]


def test_sell_reviewer_generates_hold_and_sell_summary():
    reviewer = object.__new__(SellReviewer)

    suggestion = reviewer.generate_suggestion(
        "2026-03-17",
        [
            {"code": "600000", "decision": "hold", "confidence": 0.7},
            {"code": "000001", "decision": "sell", "confidence": 0.8},
        ],
        0.0,
    )

    assert suggestion["hold_list"] == ["600000"]
    assert suggestion["sell_list"] == ["000001"]


def test_sell_config_uses_review_sell_output_dir():
    config = load_sell_config()

    assert config["output_dir"].name == "review_sell"


def test_buy_config_uses_review_output_dir():
    config = load_buy_config()

    assert config["output_dir"].name == "review"


def test_sell_config_accepts_input_override(tmp_path):
    input_path = tmp_path / "holdings_snapshot.json"
    input_path.write_text("{}", encoding="utf-8")

    config = load_sell_config(candidates_path=input_path)

    assert config["candidates"] == input_path


def test_buy_config_accepts_input_override(tmp_path):
    input_path = tmp_path / "candidates.json"
    input_path.write_text("{}", encoding="utf-8")

    config = load_buy_config(candidates_path=input_path)

    assert config["candidates"] == input_path


def test_buy_prompt_keeps_json_contract_and_detailed_scoring_rules():
    prompt_text = BuyReviewer.prompt_path.read_text(encoding="utf-8")

    assert "必须输出 JSON" in prompt_text
    assert "total_score" in prompt_text
    assert "verdict" in prompt_text
    assert "signal_type" in prompt_text
    assert "comment" in prompt_text
    assert "趋势结构" in prompt_text
    assert "价格位置" in prompt_text
    assert "量价行为" in prompt_text
    assert "前期建仓异动" in prompt_text
    assert "权重" in prompt_text
    assert "强制推理步骤" in prompt_text
    assert "只能根据图中实际可见的信息" in prompt_text
    assert "周线趋势" not in prompt_text
