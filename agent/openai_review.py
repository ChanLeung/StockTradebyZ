import base64
import os
import sys
from pathlib import Path

from openai import OpenAI

try:
    from agent.base_reviewer import BaseReviewer
    from agent.review_types import parse_buy_review
except ImportError:  # 兼容直接运行
    from base_reviewer import BaseReviewer
    from review_types import parse_buy_review


class OpenAIBuyReviewer(BaseReviewer):
    review_type = "buy"
    prompt_path = Path(__file__).resolve().parent / "prompts" / "buy_prompt.md"

    def __init__(self, config):
        super().__init__(config)

        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        base_url = os.environ.get("OPENAI_BASE_URL", "").strip() or str(config.get("base_url", "")).strip()
        if not api_key:
            print(
                "[ERROR] 未找到环境变量 OPENAI_API_KEY，请先设置后重试。",
                file=sys.stderr,
            )
            sys.exit(1)

        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        self.client = OpenAI(**client_kwargs)

    @staticmethod
    def image_to_data_url(path: Path) -> str:
        suffix = path.suffix.lower()
        mime_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
        }
        mime_type = mime_map.get(suffix, "image/jpeg")
        payload = base64.b64encode(path.read_bytes()).decode("utf-8")
        return f"data:{mime_type};base64,{payload}"

    def build_user_text(self, code: str) -> str:
        return (
            f"股票代码：{code}\n\n"
            "以下是该股票的 **日线图**，请按照系统提示中的框架进行分析，"
            "并严格按照要求输出 JSON。"
        )

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

    def review_stock(self, code: str, day_chart: Path, prompt: str) -> dict:
        response = self.client.responses.create(
            model=self.config.get("model", "gpt-5.4"),
            instructions=prompt,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "【日线图】"},
                        {
                            "type": "input_image",
                            "image_url": self.image_to_data_url(day_chart),
                        },
                        {
                            "type": "input_text",
                            "text": self.build_user_text(code),
                        },
                    ],
                }
            ],
            temperature=0.2,
        )

        response_text = response.output_text
        if response_text is None:
            raise RuntimeError(f"OpenAI 返回空响应，无法解析 JSON（code={code}）")

        result = self.extract_json(response_text)
        return self.normalize_result(result, code=code)
