import os
from pathlib import Path

from project_env import load_project_env


def test_load_project_env_reads_utf8_sig_file_and_sets_missing_values(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("\ufeffTUSHARE_TOKEN=test-token\nOPENAI_BASE_URL=https://example.com/v1\n", encoding="utf-8")
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    loaded_path = load_project_env(env_path)

    assert loaded_path == Path(env_path)
    assert os.environ["TUSHARE_TOKEN"] == "test-token"
    assert os.environ["OPENAI_BASE_URL"] == "https://example.com/v1"


def test_load_project_env_does_not_override_existing_value_by_default(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("TUSHARE_TOKEN=file-token\n", encoding="utf-8")
    monkeypatch.setenv("TUSHARE_TOKEN", "existing-token")

    load_project_env(env_path)

    assert os.environ["TUSHARE_TOKEN"] == "existing-token"
