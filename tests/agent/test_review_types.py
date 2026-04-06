from pathlib import Path

from agent.buy_review import BuyReviewer, load_buy_config
from agent.gemini_review import load_config
from agent.openai_review import OpenAIBuyReviewer, OpenAISellReviewer
from agent.review_types import (
    aggregate_buy_model_results,
    aggregate_sell_model_results,
    map_buy_score_to_verdict,
    map_sell_verdict_to_decision,
    parse_buy_review,
    parse_sell_review,
    parse_sell_signal_review,
)
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


def test_parse_sell_review_accepts_scored_payload_and_maps_to_legacy_contract():
    parsed = parse_sell_review(
        {
            "total_score": 4.2,
            "verdict": "PASS",
            "signal_type": "top_out",
            "comment": "高位放量滞涨，兑现风险上升。",
        }
    )

    assert parsed.decision == "sell"
    assert parsed.reasoning == "高位放量滞涨，兑现风险上升。"
    assert parsed.risk_flags == ["top_out"]
    assert parsed.confidence == 0.84


def test_sell_pass_maps_to_sell():
    assert map_sell_verdict_to_decision("PASS") == "sell"


def test_sell_watch_maps_to_hold():
    assert map_sell_verdict_to_decision("WATCH") == "hold"


def test_sell_fail_maps_to_hold():
    assert map_sell_verdict_to_decision("FAIL") == "hold"


def test_buy_and_sell_reviewers_use_expected_review_type():
    assert BuyReviewer.review_type == "buy"
    assert SellReviewer.review_type == "sell"


def test_buy_and_sell_reviewers_use_dedicated_prompt_files():
    assert BuyReviewer.prompt_path.name == "buy_prompt.md"
    assert SellReviewer.prompt_path.name == "sell_prompt.md"


def test_legacy_gemini_config_defaults_to_buy_prompt():
    config = load_config(Path("config/gemini_review.yaml"))

    assert config["prompt_path"].name == "buy_prompt.md"


def test_buy_reviewer_keeps_full_model_payload_fields_under_model_reviews_only():
    result = BuyReviewer.aggregate_reviews(
        code="600000",
        model_results={
            "gemini": {
                "trend_reasoning": "趋势结构良好。",
                "position_reasoning": "位置尚可。",
                "volume_reasoning": "量价健康。",
                "abnormal_move_reasoning": "前期异动明显。",
                "signal_reasoning": "具备波段潜力。",
                "scores": {
                    "trend_structure": 4,
                    "price_position": 4,
                    "volume_behavior": 4,
                    "previous_abnormal_move": 5,
                },
                "total_score": 4.3,
                "verdict": "PASS",
                "signal_type": "trend_start",
                "comment": "趋势健康。",
            },
            "openai": {
                "trend_reasoning": "趋势延续。",
                "position_reasoning": "位置适中。",
                "volume_reasoning": "量能平稳。",
                "abnormal_move_reasoning": "异动清晰。",
                "signal_reasoning": "仍有上涨空间。",
                "scores": {
                    "trend_structure": 4,
                    "price_position": 4,
                    "volume_behavior": 4,
                    "previous_abnormal_move": 4,
                },
                "total_score": 4.3,
                "verdict": "PASS",
                "signal_type": "trend_start",
                "comment": "结构稳定。",
            },
        },
        weights={"gemini": 0.5, "openai": 0.5},
    )

    assert result["code"] == "600000"
    assert result["total_score"] == 4.3
    assert result["verdict"] == "PASS"
    assert "trend_reasoning" not in result
    assert "position_reasoning" not in result
    assert "volume_reasoning" not in result
    assert "abnormal_move_reasoning" not in result
    assert "signal_reasoning" not in result
    assert "scores" not in result
    assert result["model_reviews"]["gemini"]["trend_reasoning"] == "趋势结构良好。"
    assert result["model_reviews"]["gemini"]["position_reasoning"] == "位置尚可。"
    assert result["model_reviews"]["gemini"]["volume_reasoning"] == "量价健康。"
    assert result["model_reviews"]["gemini"]["abnormal_move_reasoning"] == "前期异动明显。"
    assert result["model_reviews"]["gemini"]["signal_reasoning"] == "具备波段潜力。"
    assert result["model_reviews"]["gemini"]["scores"]["previous_abnormal_move"] == 5
    assert result["model_reviews"]["openai"]["comment"] == "结构稳定。"
    assert result["ensemble"]["weights"]["gemini"] == 0.5


def test_buy_reviewer_aggregates_equal_weight_scores_into_weighted_verdict():
    result = BuyReviewer.aggregate_reviews(
        code="600000",
        model_results={
            "gemini": {
                "total_score": 4.0,
                "verdict": "PASS",
                "signal_type": "trend_start",
                "comment": "Gemini 认为趋势仍强。",
            },
            "openai": {
                "total_score": 3.6,
                "verdict": "WATCH",
                "signal_type": "trend_start",
                "comment": "OpenAI 认为位置略高。",
            },
        },
        weights={"gemini": 0.5, "openai": 0.5},
    )

    assert result["total_score"] == 3.8
    assert result["verdict"] == "WATCH"
    assert result["signal_type"] == "trend_start"
    assert result["model_reviews"]["gemini"]["total_score"] == 4.0
    assert result["model_reviews"]["openai"]["total_score"] == 3.6
    assert result["ensemble"]["strategy"] == "weighted_average"


def test_buy_reviewer_defaults_to_dual_model_provider_config():
    config = load_buy_config()

    assert config["providers"]["gemini"]["model"] == "gemini-3.1-flash-lite-preview"
    assert config["providers"]["gemini"]["weight"] == 0.5
    assert config["providers"]["openai"]["model"] == "gpt-5.4"
    assert config["providers"]["openai"]["weight"] == 0.5
    assert config["model"].startswith("ensemble:")


def test_openai_buy_reviewer_supports_base_url_from_env(monkeypatch, tmp_path):
    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text("提示词", encoding="utf-8")
    captured: dict = {}

    class DummyClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("agent.openai_review.OpenAI", DummyClient)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.com/v1")

    OpenAIBuyReviewer(
        {
            "candidates": tmp_path / "candidates.json",
            "kline_dir": tmp_path / "kline",
            "output_dir": tmp_path / "review",
            "prompt_path": prompt_path,
            "model": "gpt-5.4",
        }
    )

    assert captured["api_key"] == "sk-test-key"
    assert captured["base_url"] == "https://example.com/v1"


def test_openai_sell_reviewer_supports_base_url_from_env(monkeypatch, tmp_path):
    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text("提示词", encoding="utf-8")
    captured: dict = {}

    class DummyClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("agent.openai_review.OpenAI", DummyClient)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.com/v1")

    OpenAISellReviewer(
        {
            "candidates": tmp_path / "candidates.json",
            "kline_dir": tmp_path / "kline",
            "output_dir": tmp_path / "review_sell",
            "prompt_path": prompt_path,
            "model": "gpt-5.4",
        }
    )

    assert captured["api_key"] == "sk-test-key"
    assert captured["base_url"] == "https://example.com/v1"


def test_buy_score_to_verdict_uses_project_thresholds():
    assert map_buy_score_to_verdict(4.0) == "PASS"
    assert map_buy_score_to_verdict(3.2) == "WATCH"
    assert map_buy_score_to_verdict(3.19) == "FAIL"


def test_aggregate_buy_model_results_uses_higher_score_signal_type_when_models_disagree():
    result = aggregate_buy_model_results(
        code="600000",
        model_results={
            "gemini": {
                "total_score": 4.4,
                "verdict": "PASS",
                "signal_type": "trend_start",
                "comment": "Gemini 偏强。",
            },
            "openai": {
                "total_score": 4.1,
                "verdict": "PASS",
                "signal_type": "reversal_setup",
                "comment": "OpenAI 偏反转。",
            },
        },
        weights={"gemini": 0.5, "openai": 0.5},
    )

    assert result["signal_type"] == "trend_start"


def test_buy_reviewer_aggregate_returns_top_level_buy_payload():
    result = BuyReviewer.aggregate_reviews(
        code="600000",
        model_results={
            "gemini": {
                "total_score": 4.2,
                "verdict": "PASS",
                "signal_type": "trend_start",
                "comment": "趋势健康。",
            },
            "openai": {
                "total_score": 4.2,
                "verdict": "PASS",
                "signal_type": "trend_start",
                "comment": "走势稳健。",
            },
        },
        weights={"gemini": 0.5, "openai": 0.5},
    )

    assert result["code"] == "600000"
    assert result["total_score"] == 4.2
    assert result["verdict"] == "PASS"


def test_buy_reviewer_aggregate_prefers_weighted_result_over_single_provider_verdict():
    result = BuyReviewer.aggregate_reviews(
        code="600000",
        model_results={
            "gemini": {
                "total_score": 4.1,
                "verdict": "PASS",
                "signal_type": "trend_start",
                "comment": "略强。",
            },
            "openai": {
                "total_score": 3.1,
                "verdict": "FAIL",
                "signal_type": "mixed",
                "comment": "略弱。",
            },
        },
        weights={"gemini": 0.5, "openai": 0.5},
    )

    assert result["total_score"] == 3.6
    assert result["verdict"] == "WATCH"


def test_sell_reviewer_normalizes_sell_payload():
    result = SellReviewer.normalize_result(
        {
            "total_score": 4.3,
            "verdict": "PASS",
            "signal_type": "top_out",
            "comment": "高位放量滞涨，兑现风险较强。",
        },
        code="600000",
    )

    assert result["code"] == "600000"
    assert result["total_score"] == 4.3
    assert result["verdict"] == "PASS"
    assert result["signal_type"] == "top_out"
    assert result["decision"] == "sell"
    assert result["risk_flags"] == ["top_out"]
    assert result["reasoning"] == "高位放量滞涨，兑现风险较强。"


def test_parse_sell_signal_review_keeps_scored_fields():
    parsed = parse_sell_signal_review(
        {
            "total_score": 3.7,
            "verdict": "WATCH",
            "signal_type": "weakening",
            "comment": "趋势转弱但未到标准卖点。",
        }
    )

    assert parsed.total_score == 3.7
    assert parsed.verdict == "WATCH"
    assert parsed.signal_type == "weakening"


def test_sell_reviewer_aggregates_equal_weight_scores_into_weighted_sell_payload():
    result = SellReviewer.aggregate_reviews(
        code="600000",
        model_results={
            "gemini": {
                "total_score": 4.2,
                "verdict": "PASS",
                "signal_type": "top_out",
                "comment": "Gemini 认为高位兑现信号明确。",
            },
            "openai": {
                "total_score": 3.4,
                "verdict": "WATCH",
                "signal_type": "weakening",
                "comment": "OpenAI 认为趋势转弱但未完全见顶。",
            },
        },
        weights={"gemini": 0.5, "openai": 0.5},
    )

    assert result["total_score"] == 3.8
    assert result["verdict"] == "WATCH"
    assert result["decision"] == "hold"
    assert result["signal_type"] == "top_out"
    assert result["risk_flags"] == ["top_out", "model_disagreement"]
    assert result["ensemble"]["strategy"] == "weighted_average"


def test_aggregate_sell_model_results_returns_top_level_compatibility_fields():
    result = aggregate_sell_model_results(
        code="600000",
        model_results={
            "gemini": {
                "total_score": 4.4,
                "verdict": "PASS",
                "signal_type": "top_out",
                "comment": "卖点较强。",
            },
            "openai": {
                "total_score": 4.4,
                "verdict": "PASS",
                "signal_type": "top_out",
                "comment": "兑现信号明确。",
            },
        },
        weights={"gemini": 0.5, "openai": 0.5},
    )

    assert result["code"] == "600000"
    assert result["decision"] == "sell"
    assert result["reasoning"]
    assert result["confidence"] == 0.88
    assert result["model_reviews"]["openai"]["comment"] == "兑现信号明确。"


def test_sell_reviewer_generates_hold_and_sell_summary():
    reviewer = object.__new__(SellReviewer)

    suggestion = reviewer.generate_suggestion(
        "2026-03-17",
        [
            {"code": "600000", "decision": "hold", "verdict": "WATCH", "total_score": 3.5, "signal_type": "weakening", "comment": "继续观察。"},
            {"code": "000001", "decision": "sell", "verdict": "PASS", "total_score": 4.3, "signal_type": "top_out", "comment": "卖出。"},
        ],
        0.0,
    )

    assert suggestion["hold_list"] == ["600000"]
    assert suggestion["sell_list"] == ["000001"]
    assert suggestion["watch_list"] == ["600000"]


def test_sell_config_uses_review_sell_output_dir():
    config = load_sell_config()

    assert config["output_dir"].name == "review_sell"
    assert config["providers"]["openai"]["model"] == "gpt-5.4"
    assert config["model"].startswith("ensemble:")


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

    assert "必须严格 JSON" in prompt_text
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
    assert "周线趋势" in prompt_text


def test_sell_prompt_keeps_json_contract_and_scoring_rules():
    prompt_text = SellReviewer.prompt_path.read_text(encoding="utf-8")

    assert "必须严格 JSON" in prompt_text
    assert "total_score" in prompt_text
    assert "verdict" in prompt_text
    assert "signal_type" in prompt_text
    assert "comment" in prompt_text
    assert "趋势结构" in prompt_text
    assert "价格位置结构" in prompt_text
    assert "量价行为" in prompt_text
    assert "前期拉升异动" in prompt_text
    assert "强制推理步骤" in prompt_text
