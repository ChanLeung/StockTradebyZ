from agent.review_cache import build_cache_key


def test_build_cache_key_for_same_parts_is_stable():
    key1 = build_cache_key("600000", "2026-01-06", "buy", "prompt-v1")
    key2 = build_cache_key("600000", "2026-01-06", "buy", "prompt-v1")

    assert key1 == key2
