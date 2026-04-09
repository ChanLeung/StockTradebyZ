import base64
import json
import os
import sys
from pathlib import Path

import requests
from openai import OpenAI

try:
    from project_env import load_project_env
except ImportError:  # 兼容直接运行 python agent/*.py
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from project_env import load_project_env

try:
    from agent.base_reviewer import BaseReviewer
    from agent.review_types import parse_buy_review, parse_sell_signal_review
except ImportError:  # 兼容直接运行
    from base_reviewer import BaseReviewer
    from review_types import parse_buy_review, parse_sell_signal_review


class OpenAIJsonReviewer(BaseReviewer):
    review_type = "generic"
    prompt_path = Path(__file__).resolve().parent / "prompts" / "buy_prompt.md"

    def __init__(self, config):
        super().__init__(config)
        load_project_env()

        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        base_url = os.environ.get("OPENAI_BASE_URL", "").strip() or str(config.get("base_url", "")).strip()
        if not api_key:
            print(
                "[ERROR] 未找到环境变量 OPENAI_API_KEY，请先设置后重试。",
                file=sys.stderr,
            )
            sys.exit(1)

        self.api_key = api_key
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
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

    def build_request_payload(self, *, code: str, day_chart: Path, prompt: str) -> dict:
        return {
            "model": self.config.get("model", "gpt-5.4"),
            "instructions": prompt,
            "input": [
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
            "temperature": 0.2,
        }
    
    def stream_response_text(self, request_payload: dict, *, code: str) -> str:
        response = requests.post(
            f"{self.base_url}/responses",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={**request_payload, "stream": True},
            stream=True,
            timeout=int(self.config.get("stream_timeout", 300)),
        )
        response.raise_for_status()

        parts: list[str] = []
        for line in response.iter_lines(decode_unicode=False):
            if not line or not line.startswith(b"data: "):
                continue
            data = line[6:]
            if data == b"[DONE]":
                break
            try:
                event = json.loads(data.decode("utf-8"))
            except json.JSONDecodeError:
                continue
            if event.get("type") == "response.output_text.delta":
                parts.append(event.get("delta", ""))

        response_text = "".join(parts).strip()
        if not response_text:
            raise RuntimeError(f"OpenAI 流式回退后仍未返回正文，无法解析 JSON（code={code}）")
        return response_text

    @staticmethod
    def normalize_result(payload: dict, *, code: str) -> dict:
        result = dict(payload)
        result["code"] = code
        return result

    def review_stock(self, code: str, day_chart: Path, prompt: str) -> dict:
        request_payload = self.build_request_payload(code=code, day_chart=day_chart, prompt=prompt)
        response = self.client.responses.create(**request_payload)

        response_text = response.output_text
        if not str(response_text or "").strip():
            response_text = self.stream_response_text(request_payload, code=code)

        result = self.extract_json(response_text)
        return self.normalize_result(result, code=code)


class OpenAIBuyReviewer(OpenAIJsonReviewer):
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


class OpenAISellReviewer(OpenAIJsonReviewer):
    review_type = "sell"
    prompt_path = Path(__file__).resolve().parent / "prompts" / "sell_prompt.md"

    @staticmethod
    def normalize_result(payload: dict, *, code: str) -> dict:
        parsed = parse_sell_signal_review(payload)
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
