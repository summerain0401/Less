import json
from pathlib import Path

import pytest
from less.ai import CodexCliExecutor, safe_environment, validate_output
from less.collector import canonical_url, paragraphs
from less.config import Settings


def output(quote="The release adds a task queue.", ids=None):
    return json.dumps(
        {
            "summary": "发布新增任务队列。",
            "language": "en",
            "claims": [
                {
                    "text": "发布新增任务队列",
                    "kind": "fact_candidate",
                    "paragraph_ids": ids or ["p0001"],
                    "quote": quote,
                }
            ],
            "entities": [],
            "topics": ["Agents"],
            "uncertainties": ["未验证实际效果"],
        }
    )


def test_quotes_and_locations_must_exist():
    source = paragraphs(
        "The release adds a task queue.\nThe authors have not evaluated productivity."
    )
    assert validate_output(output(), source).claims[0].kind == "fact_candidate"
    with pytest.raises(ValueError, match="quotation"):
        validate_output(output("Productivity doubled."), source)
    with pytest.raises(ValueError, match="paragraph"):
        validate_output(output(ids=["p0099"]), source)


def test_canonical_url_retains_meaningful_version():
    assert (
        canonical_url("https://example.com/release?v=2&utm_source=x#intro")
        == "https://example.com/release?v=2"
    )
    assert canonical_url("https://example.com/release?v=1") != canonical_url(
        "https://example.com/release?v=2"
    )
    with pytest.raises(ValueError):
        canonical_url("file:///etc/passwd")


def test_executor_has_no_business_secrets_or_tools(monkeypatch):
    monkeypatch.setenv("LESS_DATABASE_URL", "secret-db")
    monkeypatch.setenv("OPENAI_API_KEY", "secret-key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret-cloud")
    assert "LESS_DATABASE_URL" not in safe_environment()
    assert "OPENAI_API_KEY" not in safe_environment()
    assert "AWS_SECRET_ACCESS_KEY" not in safe_environment()
    cmd = CodexCliExecutor(Settings()).command(Path("/tmp/task"))
    assert "read-only" in cmd
    assert "--ignore-user-config" in cmd
    assert "shell_tool" in cmd
    assert 'approval_policy="never"' in cmd
