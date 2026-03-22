from pathlib import Path


class SellReviewer:
    review_type = "sell"
    prompt_path = Path(__file__).resolve().parent / "prompts" / "sell_prompt.md"
