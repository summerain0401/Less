import importlib.util
import json
import subprocess
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from less import agents
from less.config import ROOT, Settings
from pydantic import ValidationError


@pytest.fixture(autouse=True)
def clear_agent(monkeypatch):
    agents.get_agent.cache_clear()
    monkeypatch.setattr(agents, "settings", lambda: SimpleNamespace(agent_provider="auto"))
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.delenv("CODEX_INTERNAL_ORIGINATOR_OVERRIDE", raising=False)
    yield
    agents.get_agent.cache_clear()


@pytest.mark.parametrize("provider", ["codex", "antigravity"])
def test_explicit_provider_overrides_launch_environment(monkeypatch, provider):
    monkeypatch.setattr(agents, "settings", lambda: SimpleNamespace(agent_provider=provider))
    monkeypatch.setattr(agents, "_ancestor_provider", lambda: pytest.fail("must not inspect"))
    assert agents.resolve_provider() == provider


@pytest.mark.parametrize("command,expected", [
    ("/Applications/Codex.app/Contents/MacOS/Codex", "codex"),
    ("/Users/me/.local/bin/codex", "codex"),
    ("/Applications/Antigravity.app/Contents/MacOS/Antigravity", "antigravity"),
    ("/Users/me/.local/bin/agy", "antigravity"),
    ("/Applications/Visual Studio Code.app/Contents/MacOS/Electron", None),
    ("/projects/antigravity-project/python", None),
])
def test_process_identity(command, expected):
    assert agents._provider_for_process(command) == expected


def test_nearest_launch_ancestor_wins_over_inherited_codex_marker(monkeypatch):
    monkeypatch.setenv("CODEX_THREAD_ID", "inherited")
    monkeypatch.setattr(agents.os, "getppid", lambda: 100)
    calls = []

    def inspect(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(stdout={
            "100": "200 /bin/zsh", "200": "300 /Applications/Antigravity.app/Contents/MacOS/Antigravity",
        }[command[2]])

    monkeypatch.setattr(agents.subprocess, "run", inspect)
    assert agents.resolve_provider() == "antigravity"
    assert len(calls) == 2


@pytest.mark.parametrize("failure", [PermissionError("restricted"),
    subprocess.TimeoutExpired("ps", 1)])
def test_restricted_detection_uses_verified_codex_marker(monkeypatch, failure):
    monkeypatch.setattr(agents.subprocess, "run", lambda *_a, **_k: (_ for _ in ()).throw(failure))
    monkeypatch.setenv("CODEX_THREAD_ID", "current")
    assert agents.resolve_provider() == "codex"


def test_unknown_environment_never_selects_from_installed_tools(monkeypatch):
    monkeypatch.setattr(agents, "_ancestor_provider", lambda: None)
    monkeypatch.setattr(agents.shutil, "which", lambda _command: "/installed/tool")
    with pytest.raises(RuntimeError, match="LESS_AGENT_PROVIDER"):
        agents.get_agent()


def test_invalid_config_is_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, agent_provider="gemini")


@pytest.mark.parametrize("provider,command", [("codex", "codex"), ("antigravity", "agy")])
def test_selected_executable_missing_does_not_fallback(monkeypatch, provider, command):
    monkeypatch.setattr(agents, "resolve_provider", lambda: provider)
    monkeypatch.setattr(agents.shutil, "which", lambda candidate: None if candidate == command else "/other")
    with pytest.raises(RuntimeError, match="no other agent"):
        agents.get_agent()


@pytest.mark.parametrize("provider", ["codex", "antigravity"])
def test_child_environment_does_not_inherit_secrets_or_runtime_markers(monkeypatch, provider):
    for name in ("LESS_SMTP_PASSWORD", "SMTP_PASSWORD", "LESS_AGENT_PROVIDER", "CODEX_THREAD_ID"):
        monkeypatch.setenv(name, "private")
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("CODEX_HOME", "/codex-home")
    child = agents.agent_environment(provider)
    assert child["PATH"] == "/usr/bin"
    assert set(child) <= {"HOME", "PATH", "TMPDIR", "LANG", "LC_ALL", "USER", "CODEX_HOME"}
    assert ("CODEX_HOME" in child) == (provider == "codex")


@pytest.fixture
def task_files(tmp_path):
    schema = tmp_path / "schema.json"
    schema.write_text(json.dumps({
        "type": "object", "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"], "additionalProperties": False,
    }))
    return tmp_path, tmp_path / "output.json", schema


@pytest.mark.parametrize("provider", ["codex", "antigravity"])
def test_generation_and_comparison_share_frozen_runner(monkeypatch, task_files, provider):
    workspace, output, schema = task_files
    monkeypatch.setattr(agents, "resolve_provider", lambda: provider)
    monkeypatch.setattr(agents.shutil, "which", lambda name: f"/bin/{name}")
    chosen = agents.get_agent()
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        assert kwargs["cwd"] == workspace
        assert kwargs["timeout"] == 3600
        assert kwargs["stdin"] == subprocess.DEVNULL
        if provider == "codex":
            output.write_text('{"ok": true}')
        return SimpleNamespace(returncode=0, stderr="", stdout=json.dumps({
            "status": "SUCCESS", "structured_output": {"ok": True},
        }))

    monkeypatch.setattr(agents.subprocess, "run", run)
    assert agents.run_content_task(workspace, output, schema, "discover", search=True) == {"ok": True}
    monkeypatch.setattr(agents, "resolve_provider", lambda: "antigravity" if provider == "codex" else "codex")
    assert agents.get_agent() is chosen
    assert agents.run_content_task(workspace, output, schema, "compare") == {"ok": True}
    assert calls[0][0] == calls[1][0] == chosen.executable
    assert json.loads(output.read_text()) == {"ok": True}
    if provider == "codex":
        assert "--search" in calls[0] and "--search" not in calls[1]
        assert calls[0][calls[0].index("--sandbox") + 1] == "read-only"
    else:
        assert calls[0][calls[0].index("--json-schema") + 1] == str(schema)
        assert "--sandbox" in calls[0]
        assert "dangerously" not in " ".join(calls[0])


@pytest.mark.parametrize("provider", ["codex", "antigravity"])
@pytest.mark.parametrize("failure", [FileNotFoundError("missing"),
    subprocess.TimeoutExpired("agent", 3600)])
def test_task_start_or_timeout_failure(monkeypatch, task_files, provider, failure):
    monkeypatch.setattr(agents.subprocess, "run", lambda *_a, **_k: (_ for _ in ()).throw(failure))
    with pytest.raises(RuntimeError, match="could not complete"):
        agents.AgentRunner(provider, "/bin/agent").run(*task_files, "task")


@pytest.mark.parametrize("provider", ["codex", "antigravity"])
def test_authentication_failure(monkeypatch, task_files, provider):
    monkeypatch.setattr(agents.subprocess, "run", lambda *_a, **_k: SimpleNamespace(
        returncode=1, stderr="authentication required", stdout="",
    ))
    with pytest.raises(RuntimeError, match="authentication required"):
        agents.AgentRunner(provider, "/bin/agent").run(*task_files, "task")


@pytest.mark.parametrize("stderr", [
    "Tool read_url was soft-denied; add a permissions.allow rule",
    "permission denied: read_url", "action requires approval", "tool not allowed: search_web",
])
def test_soft_permission_denial_rejects_success(monkeypatch, task_files, stderr):
    monkeypatch.setattr(agents.subprocess, "run", lambda *_a, **_k: SimpleNamespace(
        returncode=0, stderr=stderr,
        stdout='{"status":"SUCCESS","structured_output":{"ok":true}}',
    ))
    with pytest.raises(RuntimeError, match="permission denial"):
        agents.AgentRunner("antigravity", "/bin/agy").run(*task_files, "task")


@pytest.mark.parametrize("payload", ["invalid json", "[]", "{\"ok\":\"yes\"}",
    "{}", "{\"ok\":true,\"extra\":1}"])
@pytest.mark.parametrize("provider", ["codex", "antigravity"])
def test_invalid_structured_output(monkeypatch, task_files, payload, provider):
    _, output, _ = task_files
    output.write_text(payload)
    try:
        value = json.loads(payload)
        stdout = json.dumps({"status": "SUCCESS", "structured_output": value})
    except json.JSONDecodeError:
        stdout = payload
    monkeypatch.setattr(agents.subprocess, "run", lambda *_a, **_k: SimpleNamespace(
        returncode=0, stderr="", stdout=stdout,
    ))
    with pytest.raises(RuntimeError, match="valid structured output"):
        agents.AgentRunner(provider, "/bin/agent").run(*task_files, "task")


def test_unsuccessful_envelope_even_with_zero_exit(monkeypatch, task_files):
    monkeypatch.setattr(agents.subprocess, "run", lambda *_a, **_k: SimpleNamespace(
        returncode=0, stderr="", stdout='{"status":"ERROR","error":"login required"}',
    ))
    with pytest.raises(RuntimeError, match="login required"):
        agents.AgentRunner("antigravity", "/bin/agy").run(*task_files, "task")


def test_dev_passes_selected_provider_to_all_children(monkeypatch):
    spec = importlib.util.spec_from_file_location("less_dev", ROOT / "scripts/dev.py")
    dev = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dev)
    monkeypatch.setattr(dev, "initialize_agent", lambda: SimpleNamespace(provider="antigravity"))
    monkeypatch.setattr(dev.socket, "socket", MagicMock())
    monkeypatch.setattr(dev.signal, "signal", lambda *_: None)
    environments = []

    def start(_command, **kwargs):
        environments.append(kwargs["env"])
        return SimpleNamespace(poll=lambda: 0, wait=lambda **_: None)

    monkeypatch.setattr(dev.subprocess, "Popen", start)
    with pytest.raises(SystemExit, match="exited unexpectedly"):
        dev.main()
    assert len(environments) == 3
    assert all(env["LESS_AGENT_PROVIDER"] == "antigravity" for env in environments)
