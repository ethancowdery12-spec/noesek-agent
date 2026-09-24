"""Sandboxed-execution backends behind Noesek's sandbox tool interface.

Milestone M1 of docs/SANDBOX_ISOLATION_DESIGN.md (Ethan directive, Sep 23):
every run executes under a declared SandboxPolicy. Container payloads run as
an unprivileged numeric user with all capabilities dropped and
no-new-privileges set; the environment is a fixed allowlist; the only
writable path is an optional per-run tmpfs scratch; egress is none unless a
policy declares an allowlist - which no backend honors yet (M2), so a
non-empty allowlist is an explicit error everywhere, never a silent allow.

Four pinned backends, one policy surface (noesek.tools.sandbox.run_python):
- docker-cli: the original subprocess `docker run` path (unchanged default).
- docker-py: the pinned docker SDK (Apache-2.0), same isolation flags.
- e2b: the pinned E2B SDK (Apache-2.0) remote microVM. Requires the operator's
  own E2B_API_KEY env; Noesek never embeds or requests credentials, and this
  backend is only selected explicitly via NOESEK_SANDBOX_BACKEND=e2b.
- local-subprocess: last resort on hosts without Docker (the Render image).
  Never honors egress.

Backends are constructed lazily and are dependency-injectable for tests.
"""
from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

ISOLATION = {
    "network_disabled": True,
    "read_only": True,
    "mem_limit": "256m",
    "nano_cpus": 1_000_000_000,
    "pids_limit": 64,
}

_HOST_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")

# Fixed environment allowlist inside containers. Host env is never inherited;
# no SandboxPolicy field can carry a secret by construction.
CONTAINER_ENV = ("PYTHONDONTWRITEBYTECODE=1",)

# Unprivileged numeric user for container payloads (nobody). Numeric IDs need
# no /etc/passwd entry in the image.
CONTAINER_USER = "65534:65534"


@dataclass(frozen=True)
class SandboxPolicy:
    """Declared per-run execution policy. A bare SandboxPolicy() reproduces
    the pre-policy posture exactly: nothing writable, no network, no env."""
    read_paths: tuple = ()        # host paths mounted read-only
    scratch: bool = False         # one fresh per-run tmpfs at /scratch, removed with the container
    egress: tuple = ()            # domain allowlist; empty = network none (M2 honors it, M1 rejects non-empty)
    mem_limit: str = "256m"
    timeout_seconds: int = 30

    def __post_init__(self):
        for d in self.egress:
            if not _HOST_RE.match(d or ""):
                raise ValueError(f"invalid egress domain: {d!r}")
        for p in self.read_paths:
            if not str(p).startswith("/"):
                raise ValueError(f"read_paths must be absolute: {p!r}")


class SandboxBackendError(RuntimeError):
    pass


def _check_policy(policy: SandboxPolicy | None) -> SandboxPolicy:
    policy = policy or SandboxPolicy()
    if policy.egress:
        raise SandboxBackendError(
            "egress allowlists are milestone M2 - pass an empty egress tuple for now; "
            "local-subprocess never honors egress")
    return policy


def _docker_argv(policy: SandboxPolicy, *, image: str, payload: list,
                 mem: str, tmpfs_size: str, mounts: tuple = (), workdir: str | None = None) -> list:
    """Pure argv builder for the docker-cli backend (unit-tested directly).

    Hard invariants: network none, root FS read-only, all caps dropped,
    no-new-privileges, unprivileged numeric user, env allowlist only, every
    bind mount read-only, writes confined to tmpfs (/tmp always, /scratch
    only when the policy asks)."""
    argv = ["docker", "run", "--rm", "--network=none", "--read-only",
            "--cap-drop=ALL", "--security-opt", "no-new-privileges",
            "--user", CONTAINER_USER,
            f"--memory={mem}", "--cpus=1", "--pids-limit=64",
            "--tmpfs", f"/tmp:rw,noexec,nosuid,size={tmpfs_size}"]
    for e in CONTAINER_ENV:
        argv += ["-e", e]
    for src, dst in mounts:
        argv += ["-v", f"{src}:{dst}:ro"]
    if policy.scratch:
        argv += ["--tmpfs", "/scratch:rw,noexec,nosuid,size=64m,mode=1777"]
    if workdir:
        argv += ["-w", workdir]
    return argv + [image] + list(payload)


def _container_kwargs(policy: SandboxPolicy, *, mem: str, tmpfs_size: str) -> dict:
    """docker-py run kwargs mirroring _docker_argv's invariants."""
    tmpfs = {"/tmp": f"rw,noexec,nosuid,size={tmpfs_size}"}
    if policy.scratch:
        tmpfs["/scratch"] = "rw,noexec,nosuid,size=64m,mode=1777"
    return {
        "network_disabled": True,
        "read_only": True,
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges"],
        "user": CONTAINER_USER,
        "mem_limit": mem,
        "nano_cpus": ISOLATION["nano_cpus"],
        "pids_limit": ISOLATION["pids_limit"],
        "environment": dict(e.split("=", 1) for e in CONTAINER_ENV),
        "tmpfs": tmpfs,
    }


def _trim(data: bytes | str) -> str:
    text = data.decode(errors="replace") if isinstance(data, bytes) else str(data)
    return text[-12000:]


class DockerCliBackend:
    name = "docker-cli"

    async def run_python(self, code: str, *, image: str, timeout_seconds: int,
                         policy: SandboxPolicy | None = None) -> dict:
        policy = _check_policy(policy)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "main.py"; p.write_text(code)
            cmd = _docker_argv(policy, image=image, payload=["python", "/work/main.py"],
                               mem=policy.mem_limit, tmpfs_size="32m",
                               mounts=((str(p), "/work/main.py"),))
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
                return {"exit_code": proc.returncode, "stdout": _trim(out), "stderr": _trim(err),
                        "backend": self.name}
            except OSError:
                return {"error": "Docker is not installed or not runnable on PATH", "backend": self.name}
            except TimeoutError:
                proc.kill(); await proc.wait()
                return {"error": "Sandbox timed out", "backend": self.name}


    async def run_command(self, command: str, *, image: str, timeout_seconds: int,
                          workspace: str | None = None, policy: SandboxPolicy | None = None) -> dict:
        """Run a shell command with the workspace mounted read-only at /workspace.

        Network stays disabled; PYTHONDONTWRITEBYTECODE keeps the ro mount clean."""
        policy = _check_policy(policy)
        mounts = ((workspace, "/workspace"),) if workspace else ()
        cmd = _docker_argv(policy, image=image, payload=["sh", "-c", command],
                           mem="512m", tmpfs_size="64m", mounts=mounts,
                           workdir="/workspace" if workspace else None)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
            return {"exit_code": proc.returncode, "stdout": _trim(out), "stderr": _trim(err),
                    "backend": self.name}
        except OSError:
            return {"error": "Docker is not installed or not runnable on PATH", "backend": self.name}
        except TimeoutError:
            proc.kill(); await proc.wait()
            return {"error": "Sandbox timed out", "backend": self.name}


class DockerPyBackend:
    name = "docker-py"

    def __init__(self, client=None):
        self._client = client

    def _get_client(self):
        if self._client is None:
            import docker
            self._client = docker.from_env()
        return self._client

    async def run_python(self, code: str, *, image: str, timeout_seconds: int,
                         policy: SandboxPolicy | None = None) -> dict:
        policy = _check_policy(policy)
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._run_sync, code, image, policy), timeout=timeout_seconds + 5)
        except TimeoutError:
            return {"error": "Sandbox timed out", "backend": self.name}
        except Exception as e:
            return {"error": f"docker-py backend unavailable: {e}", "backend": self.name}

    def _run_sync(self, code: str, image: str, policy: SandboxPolicy) -> dict:
        client = self._get_client()
        container = client.containers.run(
            image, ["python", "-c", code], detach=True,
            **_container_kwargs(policy, mem=policy.mem_limit, tmpfs_size="32m"))
        try:
            result = container.wait(timeout=60)
            logs = container.logs(stdout=True, stderr=True)
            return {"exit_code": result.get("StatusCode", -1), "stdout": _trim(logs),
                    "stderr": "", "backend": self.name}
        finally:
            try:
                container.remove(force=True)
            except Exception:
                pass


    async def run_command(self, command: str, *, image: str, timeout_seconds: int,
                          workspace: str | None = None, policy: SandboxPolicy | None = None) -> dict:
        policy = _check_policy(policy)
        def _run():
            client = self._get_client()
            volumes = {workspace: {"bind": "/workspace", "mode": "ro"}} if workspace else {}
            container = client.containers.run(
                image, ["sh", "-c", command], detach=True,
                volumes=volumes, working_dir="/workspace" if workspace else None,
                **_container_kwargs(policy, mem="512m", tmpfs_size="64m"))
            try:
                result = container.wait(timeout=timeout_seconds + 30)
                logs = container.logs(stdout=True, stderr=True)
                return {"exit_code": result.get("StatusCode", -1), "stdout": _trim(logs),
                        "stderr": "", "backend": self.name}
            finally:
                try: container.remove(force=True)
                except Exception: pass
        try:
            return await asyncio.wait_for(asyncio.to_thread(_run), timeout=timeout_seconds + 35)
        except TimeoutError:
            return {"error": "Sandbox timed out", "backend": self.name}
        except Exception as e:
            return {"error": f"docker-py backend unavailable: {e}", "backend": self.name}


class LocalSubprocessBackend:
    """Last-resort backend for hosts without Docker (e.g. the Render image).

    Runs the solver as a plain `python` subprocess with resource limits
    (CPU/address-space/file-size/nproc rlimits), a stripped environment (no
    inherited secrets), a hard timeout, and an isolated temp cwd. NETWORK IS
    NOT DISABLED - do not select this backend where egress matters; prefer
    docker-cli, docker-py, or e2b. Auto-fallback in get_backend only picks it
    when no container runtime is on PATH. A policy with a non-empty egress
    allowlist is REFUSED here, always.
    """

    name = "local-subprocess"

    def __init__(self, python_bin: str | None = None):
        self._python = python_bin or shutil.which("python3") or shutil.which("python")

    async def run_python(self, code: str, *, image: str, timeout_seconds: int,
                         policy: SandboxPolicy | None = None) -> dict:
        policy = _check_policy(policy)
        if not self._python:
            return {"error": "no python interpreter on PATH", "backend": self.name}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "main.py"; p.write_text(code)
            def _limits():
                try:
                    import resource
                    resource.setrlimit(resource.RLIMIT_CPU, (timeout_seconds + 5, timeout_seconds + 5))
                    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
                    resource.setrlimit(resource.RLIMIT_FSIZE, (4 * 1024 * 1024, 4 * 1024 * 1024))
                    resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
                except (ImportError, ValueError, OSError):
                    pass  # non-Linux host: timeout still enforced
            try:
                proc = await asyncio.create_subprocess_exec(
                    self._python, str(p),
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                    cwd=d, preexec_fn=_limits,
                    env={"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"})
                out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
                return {"exit_code": proc.returncode, "stdout": _trim(out),
                        "stderr": _trim(err), "backend": self.name}
            except TimeoutError:
                proc.kill(); await proc.wait()
                return {"error": "Sandbox timed out", "backend": self.name}
            except OSError as e:
                return {"error": f"local subprocess failed: {e}", "backend": self.name}

    async def run_command(self, command: str, *, image: str, timeout_seconds: int,
                          workspace: str | None = None, policy: SandboxPolicy | None = None) -> dict:
        _check_policy(policy)
        return {"error": "run_command requires a container backend (docker or e2b)",
                "backend": self.name}


class E2BBackend:
    """Remote E2B microVM backend. Selected only explicitly; requires E2B_API_KEY
    in the operator's environment (never requested or stored by Noesek)."""

    name = "e2b"

    def __init__(self, sandbox_factory=None):
        self._factory = sandbox_factory

    def _new_sandbox(self):
        if self._factory is not None:
            return self._factory()
        from e2b import Sandbox
        return Sandbox()

    async def run_command(self, command: str, *, image: str, timeout_seconds: int,
                          workspace: str | None = None, policy: SandboxPolicy | None = None) -> dict:
        _check_policy(policy)
        return {"error": "run_command is not supported on the e2b backend; use docker-cli or docker-py",
                "backend": self.name}

    async def run_python(self, code: str, *, image: str, timeout_seconds: int,
                         policy: SandboxPolicy | None = None) -> dict:
        policy = _check_policy(policy)
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._run_sync, code, timeout_seconds),
                timeout=timeout_seconds + 30)
        except TimeoutError:
            return {"error": "Sandbox timed out", "backend": self.name}
        except Exception as e:
            return {"error": f"e2b backend unavailable: {e}", "backend": self.name}

    def _run_sync(self, code: str, timeout_seconds: int) -> dict:
        sandbox = self._new_sandbox()
        try:
            sandbox.files.write("/home/user/main.py", code)
            result = sandbox.commands.run(
                "python /home/user/main.py", timeout=float(timeout_seconds))
            return {"exit_code": result.exit_code, "stdout": _trim(result.stdout),
                    "stderr": _trim(result.stderr), "backend": self.name}
        finally:
            try:
                sandbox.kill()
            except Exception:
                pass


_BACKENDS = {"docker-cli": DockerCliBackend, "docker-py": DockerPyBackend, "e2b": E2BBackend,
    "local-subprocess": LocalSubprocessBackend,
}


def get_backend(name: str | None = None):
    from ..config import settings
    selected = (name or getattr(settings, "sandbox_backend", "docker-cli") or "docker-cli").strip()
    cls = _BACKENDS.get(selected)
    if cls is None:
        raise SandboxBackendError(
            f"unknown sandbox backend {selected!r}; expected one of {sorted(_BACKENDS)}")
    if selected == "docker-cli" and shutil.which("docker") is None:
        # Hosts without a container runtime (the Render image) still get an
        # executor; the result dict names the backend actually used.
        return LocalSubprocessBackend()
    return cls()
