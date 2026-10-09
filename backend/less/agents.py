"""Select the launching agent once and normalize its structured task output."""

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from jsonschema import ValidationError, validate

from less.config import settings

Provider = Literal["codex", "antigravity"]
TIMEOUT = 3600
PERMISSION_DENIAL = re.compile(
    r"soft[- ]denied|permission[_ ]denied|requires? (?:permission|approval)|"
    r"(?:permission|approval|policy)[^\n]*(?:denied|blocked|required|not granted)|"
    r"(?:tool|action)[^\n]*(?:denied|not allowed)",
    re.IGNORECASE,
)


def _provider_for_process(command: str) -> Provider | None:
    name = Path(command).name.lower()
    if name == "agy" or name == "antigravity" or "/Antigravity.app/" in command:
        return "antigravity"
    if name == "codex" or "/Codex.app/" in command:
        return "codex"
    return None


def _ancestor_provider() -> Provider | None:
    """Inspect only our ancestors; another open application is not a launch signal."""
    pid = os.getppid()
    seen = set()
    for _ in range(24):
        if pid <= 1 or pid in seen:
            break
        seen.add(pid)
        try:
            result = subprocess.run(
                ["ps", "-p", str(pid), "-o", "ppid=,comm="],
                capture_output=True, text=True, timeout=1, check=False,
            )
            parent, command = result.stdout.strip().split(None, 1)
            pid = int(parent)
        except (OSError, subprocess.TimeoutExpired, ValueError):
            break
        provider = _provider_for_process(command)
        if provider:
            return provider
    return None


def resolve_provider() -> Provider:
    configured = settings().agent_provider
    if configured != "auto":
        return configured
    provider = _ancestor_provider()
    if provider:
        return provider
    if os.environ.get("CODEX_THREAD_ID") or (
        os.environ.get("CODEX_INTERNAL_ORIGINATOR_OVERRIDE") == "Codex Desktop"
    ):
        return "codex"
    raise RuntimeError(
        "Cannot identify the launching agent. Set LESS_AGENT_PROVIDER=codex or "
        "LESS_AGENT_PROVIDER=antigravity before starting Less."
    )


def agent_environment(provider: Provider) -> dict[str, str]:
    # Authentication may use HOME; SMTP and all LESS_ settings stay in the host.
    names = ["HOME", "PATH", "TMPDIR", "LANG", "LC_ALL", "USER"]
    if provider == "codex":
        names.append("CODEX_HOME")
    return {name: os.environ[name] for name in names if name in os.environ}


@dataclass(frozen=True)
class AgentRunner:
    provider: Provider
    executable: str

    @property
    def label(self) -> str:
        return "Codex" if self.provider == "codex" else "Antigravity"

    def run(self, workspace: Path, output: Path, schema: Path, prompt: str,
            search: bool = False) -> dict:
        if self.provider == "codex":
            command = [self.executable]
            if search:
                command.append("--search")
            command.extend([
                "--ask-for-approval", "never", "exec", "--ignore-user-config",
                "--sandbox", "read-only", "--ephemeral", "--skip-git-repo-check",
                "--cd", str(workspace), "--output-schema", str(schema),
                "--output-last-message", str(output), prompt,
            ])
        else:
            if not search:
                prompt += " 不得使用网页搜索或访问网页；只比较提供的文件。"
            command = [
                self.executable, "-p", prompt, "--output-format", "json",
                "--json-schema", str(schema), "--print-timeout", "1h", "--sandbox",
            ]
        try:
            result = subprocess.run(
                command, cwd=workspace, capture_output=True, text=True, timeout=TIMEOUT,
                env=agent_environment(self.provider), stdin=subprocess.DEVNULL, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(f"{self.label} content task could not complete: {exc}") from exc
        if result.returncode != 0:
            raise RuntimeError(
                f"{self.label} content task failed (exit {result.returncode}): "
                f"{result.stderr.strip()[-1600:]}"
            )
        if PERMISSION_DENIAL.search(result.stderr):
            raise RuntimeError(
                f"{self.label} content task encountered a permission denial: "
                f"{result.stderr.strip()[-1600:]}"
            )
        try:
            if self.provider == "codex":
                payload = json.loads(output.read_text(encoding="utf-8"))
            else:
                envelope = json.loads(result.stdout)
                if not isinstance(envelope, dict) or envelope.get("status") != "SUCCESS":
                    detail = envelope.get("error", "unsuccessful status") if isinstance(
                        envelope, dict
                    ) else "invalid envelope"
                    raise RuntimeError(f"Antigravity content task failed: {str(detail)[:1600]}")
                payload = envelope.get("structured_output")
            validate(payload, json.loads(schema.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            raise RuntimeError(f"{self.label} did not return valid structured output") from exc
        # The host writes the batch so both adapters present the same comparison inputs.
        if self.provider == "antigravity":
            output.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return payload


@lru_cache
def get_agent() -> AgentRunner:
    provider = resolve_provider()
    command = "codex" if provider == "codex" else "agy"
    executable = shutil.which(command)
    if not executable:
        raise RuntimeError(f"{provider} requires '{command}' on PATH; no other agent will be used.")
    return AgentRunner(provider, executable)


def initialize_agent() -> AgentRunner:
    agent = get_agent()
    print(f"Less content agent: {agent.label} ({agent.executable})", file=sys.stderr, flush=True)
    return agent


def run_content_task(workspace: Path, output: Path, schema: Path, prompt: str,
                     search: bool = False) -> dict:
    return get_agent().run(workspace, output, schema, prompt, search)
