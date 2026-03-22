import json

from agent.base_reviewer import BaseReviewer


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
