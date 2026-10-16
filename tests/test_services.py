import plistlib
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from less import services


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setattr(services, "STATE_FILE", tmp_path / "data/state.json")
    monkeypatch.setattr(services, "AGENTS_DIR", tmp_path / "agents")
    monkeypatch.setattr(services, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(services.shutil, "which", lambda _: "/usr/local/bin/node")
    monkeypatch.setattr(services, "get_agent", lambda: SimpleNamespace(provider="codex"))
    monkeypatch.setattr(services, "port_available", lambda _: True)
    monkeypatch.setattr(services, "pid_exists", lambda _: False)
    states = {name: {"loaded": False, "state": "stopped", "pid": None}
              for name in services.COMPONENTS}
    calls = []
    monkeypatch.setattr(services, "service_state", lambda name: dict(states[name]))
    monkeypatch.setattr(services, "healthy", lambda name, port: states[name]["loaded"])
    monkeypatch.setattr(services, "scheduler_is_running", lambda: states["scheduler"]["loaded"])

    def launchctl(*args, **kwargs):
        calls.append(args)
        if args[0] == "bootstrap":
            config = plistlib.loads(open(args[2], "rb").read())
            name = config["Label"].rsplit(".", 1)[-1]
            states[name] = {"loaded": True, "state": "running", "pid": 100}
        elif args[0] == "bootout":
            name = args[1].rsplit(".", 1)[-1]
            states[name] = {"loaded": False, "state": "stopped", "pid": None}
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(services, "launchctl", launchctl)
    return SimpleNamespace(states=states, calls=calls, launchctl=launchctl)


def test_start_stop_start_controls_all_services_and_is_idempotent(manager):
    services.start()
    assert all(state["loaded"] for state in manager.states.values())
    count = len(manager.calls)
    services.start()
    assert len(manager.calls) == count
    services.stop()
    assert not any(state["loaded"] for state in manager.states.values())
    disabled = {args[1].rsplit(".", 1)[-1] for args in manager.calls if args[0] == "disable"}
    assert disabled == set(services.COMPONENTS)
    services.stop()
    services.start()
    assert all(state["loaded"] for state in manager.states.values())


def test_unmanaged_port_conflict_leaves_running_scheduler_untouched(manager, monkeypatch):
    manager.states["scheduler"] = {"loaded": True, "state": "running", "pid": 123}
    monkeypatch.setattr(services, "port_available", lambda port: port != 8000)
    with pytest.raises(RuntimeError, match="unmanaged"):
        services.start()
    assert manager.states["scheduler"]["loaded"]
    assert manager.calls == []


def test_start_failure_rolls_back_only_new_components(manager, monkeypatch):
    manager.states["scheduler"] = {"loaded": True, "state": "running", "pid": 123}
    path = services.AGENTS_DIR / "local.less.scheduler.plist"
    services.write_file(path, plistlib.dumps(services.agent_config("scheduler", "codex")))

    def fail_frontend(*args, **kwargs):
        if args[0] == "bootstrap" and "frontend" in args[2]:
            raise subprocess.CalledProcessError(5, args)
        return manager.launchctl(*args, **kwargs)

    monkeypatch.setattr(services, "launchctl", fail_frontend)
    with pytest.raises(subprocess.CalledProcessError):
        services.start()
    assert manager.states["scheduler"]["loaded"]
    assert not manager.states["api"]["loaded"]
    assert not manager.states["frontend"]["loaded"]
    assert not any(args[0] == "bootout" and args[1].endswith("scheduler")
                   for args in manager.calls)


def test_readiness_failure_disables_new_jobs(manager, monkeypatch):
    monkeypatch.setattr(services, "healthy", lambda *_: False)
    clock = iter((0, 21))
    monkeypatch.setattr(services.time, "monotonic", lambda: next(clock))
    with pytest.raises(RuntimeError, match="did not become ready"):
        services.start()
    assert not any(state["loaded"] for state in manager.states.values())


def test_automatic_port_selection_and_explicit_conflict(manager, monkeypatch):
    monkeypatch.setattr(services, "port_available", lambda port: port in (5174, 8000))
    services.start()
    assert services.saved_settings()["frontend_port"] == 5174
    config = plistlib.loads((services.AGENTS_DIR / "local.less.frontend.plist").read_bytes())
    assert config["ProgramArguments"][config["ProgramArguments"].index("--port") + 1] == "5174"
    with pytest.raises(RuntimeError, match="occupied"):
        services.choose_port(5173, explicit=True)


def test_missing_node_does_not_enable_partial_services(manager, monkeypatch):
    monkeypatch.setattr(services.shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError, match="Node.js"):
        services.start()
    assert manager.calls == []


def test_service_configs_keep_credentials_out_of_all_jobs(manager, monkeypatch):
    monkeypatch.setenv("LESS_SMTP_PASSWORD", "sensitive-sentinel")
    monkeypatch.setenv("CODEX_THREAD_ID", "sensitive-sentinel")
    for name in services.COMPONENTS:
        config = services.agent_config(name, "codex", 5174)
        assert config["KeepAlive"] and config["RunAtLoad"]
        assert config["EnvironmentVariables"]["LESS_AGENT_PROVIDER"] == "codex"
        assert "sensitive-sentinel" not in plistlib.dumps(config).decode()


def test_service_state_does_not_confuse_nested_coalition_state(monkeypatch):
    monkeypatch.setattr(services, "launchctl", lambda *_a, **_kw: SimpleNamespace(
        returncode=0,
        stdout="\tstate = running\n\tpid = 123\n\tresource coalition = {\n\t\tstate = active\n\t}",
    ))
    state = services.service_state("api")
    assert state["state"] == "running"
    assert state["pid"] == 123


def test_frontend_health_accepts_current_less_title(monkeypatch):
    monkeypatch.setattr(services, "service_state", lambda _: {"state": "running", "pid": 123})
    response = Mock(status=200)
    response.read.return_value = "<title>Less · Read less. Know more.</title>".encode()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(services, "urlopen", lambda *_a, **_kw: response)
    assert services.healthy("frontend", 5174)
    response.read.return_value = b"<title>Another project</title>"
    assert not services.healthy("frontend", 5174)


def test_dev_stops_all_services_on_interrupt(monkeypatch):
    start, stop = Mock(), Mock()
    monkeypatch.setattr(services, "start", start)
    monkeypatch.setattr(services, "stop", stop)
    monkeypatch.setattr(services.signal, "signal", lambda *_: None)
    event = Mock()
    event.wait.side_effect = KeyboardInterrupt
    monkeypatch.setattr(services.threading, "Event", lambda: event)
    with pytest.raises(KeyboardInterrupt):
        services.dev()
    start.assert_called_once()
    stop.assert_called_once()


def test_dev_start_failure_does_not_stop_preexisting_services(monkeypatch):
    monkeypatch.setattr(services.signal, "signal", lambda *_: None)
    monkeypatch.setattr(services, "start", Mock(side_effect=RuntimeError("port busy")))
    stop = Mock()
    monkeypatch.setattr(services, "stop", stop)
    with pytest.raises(RuntimeError, match="port busy"):
        services.dev()
    stop.assert_not_called()
