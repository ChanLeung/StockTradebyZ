import json

from agent.base_reviewer import BaseReviewer


class DummyReviewer(BaseReviewer):
    review_type = "sell"

    def __init__(self, config):
        super().__init__(config)
        self.calls = 0

    def review_stock(self, code: str, day_chart, prompt: str) -> dict:
        _ = day_chart, prompt
        self.calls += 1
        return {
            "code": code,
            "decision": "hold",
        }

    def generate_suggestion(self, pick_date: str, all_results: list[dict], min_score: float) -> dict:
        _ = min_score
        return {
            "date": pick_date,
            "total_reviewed": len(all_results),
            "recommendations": [],
        }


def test_load_review_universe_supports_candidate_run_payload(tmp_path):
    payload_path = tmp_path / "candidates.json"
    payload_path.write_text(
        json.dumps(
            {
                "pick_date": "2026-03-17",
                "candidates": [
                    {"code": "600000"},
                    {"code": "000001"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    universe = BaseReviewer.load_review_universe(payload_path)

    assert universe["pick_date"] == "2026-03-17"
    assert [item["code"] for item in universe["candidates"]] == ["600000", "000001"]


def test_load_review_universe_supports_holdings_snapshot_payload(tmp_path):
    payload_path = tmp_path / "holdings_snapshot.json"
    payload_path.write_text(
        json.dumps(
            {
                "as_of_date": "2026-03-18",
                "state": {
                    "cash": 95000.0,
                    "positions": [
                        {"code": "600000", "entry_date": "2026-03-17", "entry_price": 10.8, "weight": 0.5},
                        {"code": "000001", "entry_date": "2026-03-17", "entry_price": 9.6, "weight": 0.5},
                    ],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    universe = BaseReviewer.load_review_universe(payload_path)

    assert universe["pick_date"] == "2026-03-18"
    assert [item["code"] for item in universe["candidates"]] == ["600000", "000001"]


def test_reviewer_reuses_existing_result_only_when_cache_key_matches(tmp_path):
    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text("卖出复评提示词 v1", encoding="utf-8")
    candidates_path = tmp_path / "candidates.json"
    candidates_path.write_text(
        json.dumps({"pick_date": "2026-03-18", "candidates": [{"code": "600000"}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    kline_dir = tmp_path / "kline" / "2026-03-18"
    kline_dir.mkdir(parents=True)
    (kline_dir / "600000_day.png").write_text("fake", encoding="utf-8")
    output_dir = tmp_path / "review_sell"
    out_dir = output_dir / "2026-03-18"
    out_dir.mkdir(parents=True)
    existing_path = out_dir / "600000.json"
    existing_path.write_text(
        json.dumps(
            {
                "code": "600000",
                "decision": "hold",
                "_meta": {
                    "cache_key": "old-key",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    reviewer = DummyReviewer(
        {
            "candidates": candidates_path,
            "kline_dir": tmp_path / "kline",
            "output_dir": output_dir,
            "prompt_path": prompt_path,
            "skip_existing": True,
            "request_delay": 0,
            "model": "gemini-test",
        }
    )

    reviewer.run()

    assert reviewer.calls == 1


def test_reviewer_skips_when_existing_result_cache_key_matches(tmp_path):
    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text("卖出复评提示词 v1", encoding="utf-8")
    candidates_path = tmp_path / "candidates.json"
    candidates_path.write_text(
        json.dumps({"pick_date": "2026-03-18", "candidates": [{"code": "600000"}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    kline_dir = tmp_path / "kline" / "2026-03-18"
    kline_dir.mkdir(parents=True)
    (kline_dir / "600000_day.png").write_text("fake", encoding="utf-8")
    output_dir = tmp_path / "review_sell"
    out_dir = output_dir / "2026-03-18"
    out_dir.mkdir(parents=True)

    reviewer = DummyReviewer(
        {
            "candidates": candidates_path,
            "kline_dir": tmp_path / "kline",
            "output_dir": output_dir,
            "prompt_path": prompt_path,
            "skip_existing": True,
            "request_delay": 0,
            "model": "gemini-test",
        }
    )
    cache_key = reviewer.build_review_cache_key("2026-03-18", "600000")
    (out_dir / "600000.json").write_text(
        json.dumps(
            {
                "code": "600000",
                "decision": "hold",
                "_meta": {
                    "cache_key": cache_key,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    reviewer.run()

    assert reviewer.calls == 0
