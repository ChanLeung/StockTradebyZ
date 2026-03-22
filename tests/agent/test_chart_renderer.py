from agent.chart_renderer import render_review_chart


def test_render_chart_uses_cache_key(tmp_path, price_frame):
    path1 = render_review_chart(
        price_frame,
        cache_dir=tmp_path,
        review_type="buy",
        code="600000",
        as_of_date="2026-01-06",
    )
    path2 = render_review_chart(
        price_frame,
        cache_dir=tmp_path,
        review_type="buy",
        code="600000",
        as_of_date="2026-01-06",
    )

    assert path1 == path2
    assert path1.exists()
