from pathlib import Path

import pandas as pd
from PIL import Image, ImageDraw

from agent.review_cache import get_cache_path


def _normalize_close_points(df: pd.DataFrame, width: int, height: int, padding: int) -> list[tuple[float, float]]:
    closes = df["close"].astype(float).tolist()
    if not closes:
        return []

    if len(closes) == 1:
        x_positions = [width / 2]
    else:
        step = (width - padding * 2) / (len(closes) - 1)
        x_positions = [padding + idx * step for idx in range(len(closes))]

    min_close = min(closes)
    max_close = max(closes)
    if max_close == min_close:
        y_positions = [height / 2 for _ in closes]
    else:
        usable_height = height - padding * 2
        y_positions = [
            padding + (max_close - close) / (max_close - min_close) * usable_height
            for close in closes
        ]

    return list(zip(x_positions, y_positions))


def render_review_chart(
    df: pd.DataFrame,
    *,
    cache_dir: str | Path,
    review_type: str,
    code: str,
    as_of_date: str,
    width: int = 1200,
    height: int = 700,
) -> Path:
    output_path = get_cache_path(cache_dir, code, as_of_date, review_type, str(width), str(height))
    if output_path.exists():
        return output_path

    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)

    padding = 40
    draw.rectangle((padding, padding, width - padding, height - padding), outline="#d0d7de", width=2)

    points = _normalize_close_points(df, width, height, padding)
    if len(points) >= 2:
        draw.line(points, fill="#2563eb", width=4)
    elif len(points) == 1:
        x, y = points[0]
        draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill="#2563eb")

    image.save(output_path, format="PNG")
    return output_path
