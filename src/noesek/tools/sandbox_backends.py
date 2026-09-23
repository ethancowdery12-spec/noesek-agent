"""Sandboxed-execution backends behind Noesek's sandbox tool interface.

Three pinned backends, one policy surface (noesek.tools.sandbox.run_python):
- docker-cli: the original subprocess `docker run` path (unchanged default).
- docker-py: the pinned docker SDK (Apache-2.0), same isolation flags.
- e2b: the pinned E2B SDK (Apache-2.0) remote microVM. Requires the operator's
  own E2B_API_KEY env; Noesek never embeds or requests credentials, and this
  backend is only selected explicitly via NOESEK_SANDBOX_BACKEND=e2b.

Backends are constructed lazily and are dependency-injectable for tests.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ISOLATION = {
    "network_disabled": True,
    "read_only": True,
    "mem_limit": "256m",
    "nano_cpus": 1_000_000_000,
    "pids_limit": 64,
}


class SandboxBackendError(RuntimeError):
    pass


def _trim(data: bytes | str) -> str:
    text = data.decode(errors="replace") if isinstance(data, bytes) else str(data)
    return text[-12000:]


class DockerCliBackend:
    name = "docker-cli"

    async def run_python(self, code: str, *, image: str, timeout_seconds: int) -> dict:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "main.py"; p.write_text(code)
            cmd = ["docker", "run", "--rm", "--network=none", "--read-only",
                   "--memory=256m", "--cpus=1", "--pids-limit=64",
                   "--tmpfs", "/tmp:rw,noexec,nosuid,size=32m",
                   "-v", f"{p}:/work/main.py:ro", image, "python", "/work/main.py"]
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
                          workspace: str | None = None) -> dict:
        """Run a shell command with the workspace mounted read-only at /workspace.

        Network stays disabled; PYTHONDONTWRITEBYTECODE keeps the ro mount clean."""
        with tempfile.TemporaryDirectory() as d:
            cmd = ["docker", "run", "--rm", "--network=none", "--read-only",
                   "--memory=512m", "--cpus=1", "--pids-limit=64",
                   "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
                   "-e", "PYTHONDONTWRITEBYTECODE=1"]
            if workspace:
                cmd += ["-v", f"{workspace}:/workspace:ro", "-w", "/workspace"]
            cmd += [image, "sh", "-c", command]
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

    async def run_python(self, code: str, *, image: str, timeout_seconds: int) -> dict:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._run_sync, code, image), timeout=timeout_seconds + 5)
        except TimeoutError:
            return {"error": "Sandbox timed out", "backend": self.name}
        except Exception as e:
            return {"error": f"docker-py backend unavailable: {e}", "backend": self.name}

    def _run_sync(self, code: str, image: str) -> dict:
        client = self._get_client()
        container = client.containers.run(
            image, ["python", "-c", code],
            detach=True, network_disabled=ISOLATION["network_disabled"],
            read_only=ISOLATION["read_only"], mem_limit=ISOLATION["mem_limit"],
            nano_cpus=ISOLATION["nano_cpus"], pids_limit=ISOLATION["pids_limit"],
            tmpfs={"/tmp": "rw,noexec,nosuid,size=32m"})
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
                          workspace: str | None = None) -> dict:
        def _run():
            client = self._get_client()
            volumes = {workspace: {"bind": "/workspace", "mode": "ro"}} if workspace else {}
            container = client.containers.run(
                image, ["sh", "-c", command], detach=True,
                network_disabled=ISOLATION["network_disabled"],
                read_only=ISOLATION["read_only"], mem_limit="512m",
                nano_cpus=ISOLATION["nano_cpus"], pids_limit=ISOLATION["pids_limit"],
                tmpfs={"/tmp": "rw,noexec,nosuid,size=64m"},
                environment={"PYTHONDONTWRITEBYTECODE": "1"},
                volumes=volumes, working_dir="/workspace" if workspace else None)
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
    when no container runtime is on PATH.
    """

    name = "local-subprocess"

    def __init__(self, python_bin: str | None = None):
        self._python = python_bin or shutil.which("python3") or shutil.which("python")

    async def run_python(self, code: str, *, image: str, timeout_seconds: int) -> dict:
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
                          workspace: str | None = None) -> dict:
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
                          workspace: str | None = None) -> dict:
        return {"error": "run_command is not supported on the e2b backend; use docker-cli or docker-py",
                "backend": self.name}

    async def run_python(self, code: str, *, image: str, timeout_seconds: int) -> dict:
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
