"""
gemini_review.py
~~~~~~~~~~~~~~~~
历史兼容入口。

当前项目的真实买入复评入口已经迁移到：

    python -m agent.buy_review

本文件保留的目的：

- 兼容旧命令 `python agent/gemini_review.py`
- 兼容旧导入路径
"""

from __future__ import annotations

try:
    from agent.buy_review import main as _buy_review_main
    from agent.gemini_provider import GeminiBuyReviewer, GeminiJsonReviewer, GeminiReviewer
    from agent.review_config import BUY_REVIEW_CONFIG_PATH as _DEFAULT_CONFIG_PATH
    from agent.review_config import _ROOT, load_review_config as _load_review_config
except ImportError:  # 兼容直接运行 python agent/gemini_review.py
    from buy_review import main as _buy_review_main
    from gemini_provider import GeminiBuyReviewer, GeminiJsonReviewer, GeminiReviewer
    from review_config import BUY_REVIEW_CONFIG_PATH as _DEFAULT_CONFIG_PATH
    from review_config import _ROOT, load_review_config as _load_review_config


def load_config(config_path=None, *, prompt_path=None, output_dir=None):
    return _load_review_config(
        config_path or _DEFAULT_CONFIG_PATH,
        prompt_path=prompt_path,
        output_dir=output_dir,
    )


def main() -> None:
    _buy_review_main()


if __name__ == "__main__":
    main()
