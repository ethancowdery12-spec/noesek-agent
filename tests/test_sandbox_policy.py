"""SandboxPolicy (M1) invariants: the flags a run executes under, without
needing a Docker daemon - argv and kwargs are pure and tested directly."""
import os

import pytest

from noesek.tools.sandbox_backends import (
    CONTAINER_ENV, CONTAINER_USER, DockerCliBackend, DockerPyBackend,
    E2BBackend, LocalSubprocessBackend, SandboxBackendError, SandboxPolicy,
    _container_kwargs, _docker_argv)


def test_default_policy_reproduces_old_posture():
    p = SandboxPolicy()
    assert p.read_paths == () and p.egress == () and p.scratch is False


def test_policy_is_frozen():
    with pytest.raises(Exception):
        SandboxPolicy().egress = ("x.example.com",)


def test_bad_egress_domain_rejected():
    with pytest.raises(ValueError):
        SandboxPolicy(egress=("not a domain!!",))


def test_relative_read_path_rejected():
    with pytest.raises(ValueError):
        SandboxPolicy(read_paths=("relative/dir",))


def test_good_policy_accepted():
    p = SandboxPolicy(egress=("api.github.com", "pypi.org"), read_paths=("/srv/data",), scratch=True)
    assert "pypi.org" in p.egress


def test_docker_argv_hardening_flags():
    argv = _docker_argv(SandboxPolicy(), image="python:3.12-alpine",
                        payload=["python", "/work/main.py"], mem="256m", tmpfs_size="32m",
                        mounts=(("/host/main.py", "/work/main.py"),))
    s = " ".join(argv)
    assert "--network=none" in s and "--read-only" in s
    assert "--cap-drop=ALL" in s
    assert "no-new-privileges" in s
    assert argv[argv.index("--user") + 1] == CONTAINER_USER
    assert "/host/main.py:/work/main.py:ro" in argv  # every mount read-only


def test_docker_argv_env_allowlist_only(monkeypatch):
    monkeypatch.setenv("NOESEK_LLM_API_KEY", "sk-sentinel-secret")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "aws-sentinel")
    argv = _docker_argv(SandboxPolicy(), image="img", payload=["true"], mem="256m", tmpfs_size="32m")
    env_flags = [argv[i + 1] for i, a in enumerate(argv) if a == "-e"]
    assert env_flags == list(CONTAINER_ENV)
    assert not any("sentinel" in tok for tok in argv)
    leaked = [k for k, v in os.environ.items()
              if len(v) >= 8 and any(v in tok for tok in argv)]
    assert leaked == []


def test_scratch_is_the_only_extra_writable_path():
    p = SandboxPolicy(scratch=True)
    argv = _docker_argv(p, image="img", payload=["true"], mem="256m", tmpfs_size="32m")
    tmpfs_vals = [argv[i + 1] for i, a in enumerate(argv) if a == "--tmpfs"]
    assert "/scratch:rw,noexec,nosuid,size=64m,mode=1777" in tmpfs_vals
    # /tmp and /scratch tmpfs are the only writable paths; the root FS stays ro
    assert "--read-only" in argv
    assert "--read-only" in argv


def test_container_kwargs_mirror_argv():
    kw = _container_kwargs(SandboxPolicy(scratch=True), mem="256m", tmpfs_size="32m")
    assert kw["cap_drop"] == ["ALL"]
    assert kw["security_opt"] == ["no-new-privileges"]
    assert kw["user"] == CONTAINER_USER
    assert kw["network_disabled"] is True and kw["read_only"] is True
    assert set(kw["environment"]) == {"PYTHONDONTWRITEBYTECODE"}
    assert "/scratch" in kw["tmpfs"]


@pytest.mark.parametrize("backend", [
    DockerCliBackend(), DockerPyBackend(client=None), E2BBackend(sandbox_factory=lambda: None),
    LocalSubprocessBackend(),
])
async def test_egress_allowlist_refused_everywhere(backend):
    with pytest.raises(SandboxBackendError, match="M2"):
        await backend.run_python("print(1)", image="img", timeout_seconds=5,
                                 policy=SandboxPolicy(egress=("pypi.org",)))


async def test_local_subprocess_run_command_also_checks_policy():
    with pytest.raises(SandboxBackendError, match="M2"):
        await LocalSubprocessBackend().run_command("ls", image="img", timeout_seconds=5,
                                                   policy=SandboxPolicy(egress=("pypi.org",)))
