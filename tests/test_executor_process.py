import stat
import sys

import pytest
from less.ai import AIError, CodexCliExecutor
from less.config import Settings


def shim(tmp_path, script):
    path = tmp_path / "fake-codex"
    path.write_text(
        f"#!{sys.executable}\nimport sys, json, pathlib, time\n"
        "if '--version' in sys.argv:\n print('codex-test 1'); sys.exit(0)\n" + script
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


def test_process_output_and_usage(tmp_path):
    binary = shim(
        tmp_path,
        "sys.stdin.read()\npathlib.Path(sys.argv[sys.argv.index('--output-last-message')+1]).write_text('{}')\nprint(json.dumps({'type':'turn.completed','usage':{'input_tokens':10,'output_tokens':2}}))\n",
    )
    result = CodexCliExecutor(Settings(codex_bin=binary)).execute({"paragraphs": []})
    assert result.raw == "{}"
    assert result.metadata["usage"]["input_tokens"] == 10
    assert result.metadata["cost"] is None


@pytest.mark.parametrize(
    "message,code", [("Unauthorized 401", "auth"), ("Usage limit reached", "quota")]
)
def test_auth_and_quota_classification(tmp_path, message, code):
    binary = shim(tmp_path, f"print({message!r}, file=sys.stderr)\nsys.exit(1)\n")
    with pytest.raises(AIError) as error:
        CodexCliExecutor(Settings(codex_bin=binary)).execute({})
    assert error.value.code == code


def test_timeout_terminates_process(tmp_path):
    binary = shim(tmp_path, "time.sleep(60)\n")
    config = Settings(codex_bin=binary).model_copy(update={"codex_timeout": 0.1})
    with pytest.raises(AIError) as error:
        CodexCliExecutor(config).execute({})
    assert error.value.code == "timeout"
