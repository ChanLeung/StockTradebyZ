from pathlib import Path


class BuyReviewer:
    review_type = "buy"
    prompt_path = Path(__file__).resolve().parent / "prompts" / "buy_prompt.md"
