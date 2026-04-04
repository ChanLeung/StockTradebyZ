from __future__ import annotations

import os
import sys
from pathlib import Path

from google import genai
from google.genai import types

try:
    from project_env import load_project_env
except ImportError:  # 兼容直接运行 python agent/*.py
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from project_env import load_project_env

try:
    from agent.base_reviewer import BaseReviewer
    from agent.review_types import parse_buy_review
except ImportError:  # 兼容直接运行 python agent/*.py
    from base_reviewer import BaseReviewer
    from review_types import parse_buy_review


class GeminiJsonReviewer(BaseReviewer):
    review_type = "generic"
    prompt_path = Path(__file__).resolve().parent / "prompts" / "buy_prompt.md"

    def __init__(self, config):
        super().__init__(config)
        load_project_env()

        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            print(
                "[ERROR] 未找到环境变量 GEMINI_API_KEY，请先设置后重试。",
                file=sys.stderr,
            )
            sys.exit(1)

        self.client = genai.Client(api_key=api_key)

    @staticmethod
    def image_to_part(path: Path) -> types.Part:
        suffix = path.suffix.lower()
        mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
        mime_type = mime_map.get(suffix, "image/jpeg")
        return types.Part.from_bytes(data=path.read_bytes(), mime_type=mime_type)

    def build_user_text(self, code: str) -> str:
        return (
            f"股票代码：{code}\n\n"
            "以下是该股票的 **日线图**，请按照系统提示中的框架进行分析，"
            "并严格按照要求输出 JSON。"
        )

    @staticmethod
    def normalize_result(payload: dict, *, code: str) -> dict:
        result = dict(payload)
        result["code"] = code
        return result

    def review_stock(self, code: str, day_chart: Path, prompt: str) -> dict:
        parts: list[types.Part] = [
            types.Part.from_text(text="【日线图】"),
            self.image_to_part(day_chart),
            types.Part.from_text(text=self.build_user_text(code)),
        ]

        response = self.client.models.generate_content(
            model=self.config.get("model", "gemini-3.1-flash-lite-preview"),
            contents=[types.Content(role="user", parts=parts)],
            config=types.GenerateContentConfig(
                system_instruction=prompt,
                temperature=0.2,
            ),
        )

        response_text = response.text
        if response_text is None:
            raise RuntimeError(f"Gemini 返回空响应，无法解析 JSON（code={code}）")

        result = self.extract_json(response_text)
        return self.normalize_result(result, code=code)


class GeminiBuyReviewer(GeminiJsonReviewer):
    review_type = "buy"
    prompt_path = Path(__file__).resolve().parent / "prompts" / "buy_prompt.md"

    @staticmethod
    def normalize_result(payload: dict, *, code: str) -> dict:
        parsed = parse_buy_review(payload)
        result = dict(payload)
        result.update(
            {
                "code": code,
                "total_score": parsed.total_score,
                "verdict": parsed.verdict,
                "signal_type": parsed.signal_type,
                "comment": parsed.comment,
            }
        )
        return result


GeminiReviewer = GeminiBuyReviewer
