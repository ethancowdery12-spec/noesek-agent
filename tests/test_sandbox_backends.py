"""Sandbox backend contract tests. No live daemons or accounts: docker-py is
tested against a fake SDK client, e2b against a fake sandbox factory."""
import shutil

import pytest

from noesek.tools.sandbox_backends import (DockerCliBackend, DockerPyBackend,
                                           E2BBackend, SandboxBackendError,
                                           get_backend)


@pytest.mark.skipif(shutil.which("docker") is None, reason="no docker binary - get_backend falls back to local-subprocess")
async def test_default_backend_is_docker_cli():
    assert get_backend().name == "docker-cli"


def test_unknown_backend_rejected():
    with pytest.raises(SandboxBackendError):
        get_backend("firecracker")


async def test_docker_cli_missing_binary_is_clean_error():
    out = await DockerCliBackend().run_python("print(1)", image="python:3.12-alpine", timeout_seconds=5)
    assert out["backend"] == "docker-cli"
    assert "exit_code" in out or "error" in out


class FakeContainer:
    def wait(self, timeout=None):
        return {"StatusCode": 0}

    def logs(self, stdout=True, stderr=True):
        return b"fake-output\n"

    def remove(self, force=False):
        self.removed = True


class FakeDockerClient:
    def __init__(self):
        self.calls = []

    class containers:
        @staticmethod
        def run(image, cmd, **kwargs):
            FakeDockerClient.last_kwargs = kwargs
            return FakeContainer()


async def test_docker_py_applies_isolation_flags():
    backend = DockerPyBackend(client=FakeDockerClient())
    out = await backend.run_python("print('hi')", image="python:3.12-alpine", timeout_seconds=5)
    assert out["exit_code"] == 0 and out["stdout"] == "fake-output\n"
    kw = FakeDockerClient.last_kwargs
    assert kw["network_disabled"] is True and kw["read_only"] is True
    assert kw["mem_limit"] == "256m" and kw["pids_limit"] == 64


class FakeCommandResult:
    exit_code = 0
    stdout = "e2b-ok\n"
    stderr = ""


class FakeE2BSandbox:
    def __init__(self):
        self.killed = False
        self.files = self
        self.commands = self

    def write(self, path, data):
        self.written = (path, data)

    def run(self, cmd, timeout=None):
        self.cmd = cmd
        return FakeCommandResult()

    def kill(self):
        self.killed = True


async def test_e2b_backend_writes_runs_and_kills():
    holder = {}
    def factory():
        holder["sb"] = FakeE2BSandbox()
        return holder["sb"]
    backend = E2BBackend(sandbox_factory=factory)
    out = await backend.run_python("print('hi')", image="ignored", timeout_seconds=10)
    assert out["exit_code"] == 0 and out["stdout"] == "e2b-ok\n"
    assert holder["sb"].written[0] == "/home/user/main.py"
    assert holder["sb"].killed is True  # microVM always torn down


async def test_e2b_backend_error_is_contained():
    def factory():
        raise RuntimeError("no api key")
    out = await E2BBackend(sandbox_factory=factory).run_python("x=1", image="i", timeout_seconds=5)
    assert "e2b backend unavailable" in out["error"]
