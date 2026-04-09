import json
from types import SimpleNamespace

import agent.openai_review as openai_review
from agent.openai_review import OpenAIBuyReviewer


def test_openai_buy_reviewer_falls_back_to_stream_when_output_text_is_empty(monkeypatch, tmp_path):
    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text("提示词", encoding="utf-8")
    chart_path = tmp_path / "600000_day.jpg"
    chart_path.write_bytes(b"fake-image")

    class DummyResponses:
        def create(self, **kwargs):
            _ = kwargs
            return SimpleNamespace(output_text="")

    class DummyClient:
        def __init__(self, **kwargs):
            _ = kwargs
            self.responses = DummyResponses()

    class DummyStreamResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def iter_lines(self, decode_unicode=False):
            _ = decode_unicode
            events = [
                {"type": "response.output_text.delta", "delta": '{"total_score": 4.2,'},
                {"type": "response.output_text.delta", "delta": ' "verdict": "PASS",'},
                {"type": "response.output_text.delta", "delta": ' "signal_type": "trend_start",'},
                {"type": "response.output_text.delta", "delta": ' "comment": "趋势健康。"}'},
            ]
            for event in events:
                yield f"data: {json.dumps(event, ensure_ascii=False)}".encode("utf-8")
            yield b"data: [DONE]"

    def fake_post(url, *, headers=None, json=None, stream=None, timeout=None):
        assert url == "https://example.com/v1/responses"
        assert headers == {
            "Authorization": "Bearer sk-test-key",
            "Content-Type": "application/json",
        }
        assert json["stream"] is True
        assert stream is True
        assert timeout == 300
        return DummyStreamResponse()

    monkeypatch.setattr(openai_review, "OpenAI", DummyClient)
    monkeypatch.setattr(
        openai_review,
        "requests",
        SimpleNamespace(post=fake_post),
        raising=False,
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.com/v1")

    reviewer = OpenAIBuyReviewer(
        {
            "candidates": tmp_path / "candidates.json",
            "kline_dir": tmp_path,
            "output_dir": tmp_path / "review",
            "prompt_path": prompt_path,
            "model": "gpt-5.4",
        }
    )

    result = reviewer.review_stock("600000", chart_path, "提示词")

    assert result["code"] == "600000"
    assert result["total_score"] == 4.2
    assert result["verdict"] == "PASS"
    assert result["signal_type"] == "trend_start"
