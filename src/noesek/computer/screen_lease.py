"""Who may drive the noesek computer screen: the agent (default) or exactly one human viewer.

Adapted from Nous Research hermes-agent tools/bot_desktop/lease.py (MIT License).
See THIRD_PARTY_NOTICES. Adaptations: single profile (noesek runs one computer),
state dir from NOESEK_COMPUTER_HOME (default ~/.noesek-computer), no Hermes config
helpers, no multi-profile keying.

The lease is the single truth shared by the RFB bridge (drops human input from
non-holders), the computer tools (refuse to act while a human holds control - the
person may be typing a credential, so even screenshots are refused; fail closed
rather than trusting the agent to pause itself) and the viewer UI
(Watch / Take over / Hand back).

Scope: the lease is a TOOL-LEVEL fence, not a property of the X server. A process
the agent starts by hand against the published DISPLAY (a terminal tool, a script)
is inside the documented same-user boundary and is not stopped by it.

Authority lives ON DISK, <state>/screen/lease.json under an fcntl lock, because the
processes that must agree do not share memory: the server, a CLI turn and isolated
workers all drive the same display. Every read goes to the file; the in-process
Condition only wakes local waiters early. ``epoch`` increments on every transition
so an action admitted under one lease can tell that control changed underneath it.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

try:
    import fcntl
except ImportError:  # non-POSIX: no multi-process screen exists there
    fcntl = None

logger = logging.getLogger(__name__)

AGENT = "agent"
HUMAN = "human"


class HumanHasControl(RuntimeError):
    """Raised by screen-driving tools while a human holds the lease."""


def state_dir() -> Path:
    return Path(os.environ.get("NOESEK_COMPUTER_HOME", str(Path.home() / ".noesek-computer")))


@dataclass
class Lease:
    holder: str = AGENT
    viewer_id: Optional[str] = None
    since: float = field(default_factory=time.time)
    reason: str = ""
    epoch: int = 0

    def as_dict(self) -> Dict[str, object]:
        return asdict(self)


def public_view(lease: Lease) -> Dict[str, object]:
    """The lease as anything outside the server may see it: the holder's viewer id is a
    capability (whoever presents it co-drives or releases the lease), so it is replaced by
    a short hash the holder can match against its own id to know it is in control."""
    d = lease.as_dict()
    d["viewer_id"] = None
    d["viewer_hash"] = hashlib.sha256(lease.viewer_id.encode()).hexdigest()[:12] if lease.viewer_id else None
    return d


_lock = threading.Condition()
_listeners: List[Callable[[Lease], None]] = []


def _path() -> Path:
    return state_dir() / "screen" / "lease.json"


def _read(path: Path) -> Lease:
    """No file = fresh state, agent holds. A file that exists but cannot be parsed is a torn
    write or tampering: fail CLOSED (human holds) - an unreadable lease must never let the
    agent act on a screen a human may be using; the next successful write repairs it."""
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return Lease()
    except OSError:
        return Lease(holder=HUMAN, viewer_id="unreadable-lease", reason="lease file unreadable")
    try:
        data = json.loads(raw)
    except ValueError:
        data = None
    if not isinstance(data, dict) or data.get("holder") not in (AGENT, HUMAN):
        return Lease(holder=HUMAN, viewer_id="unreadable-lease", reason="lease file corrupt")
    try:
        return Lease(**{k: v for k, v in data.items() if k in Lease.__dataclass_fields__})
    except TypeError:
        return Lease(holder=HUMAN, viewer_id="unreadable-lease", reason="lease file corrupt")


def _private_dir(path: Path) -> None:
    """screen/ owner-only even when the lease is the first thing written there."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass


def _open_private(path, flags: int) -> int:
    """open(..., opener=_open_private): the file is created 0600 regardless of the umask."""
    return os.open(path, flags, 0o600)


def _write(path: Path, lease: Lease) -> None:
    _private_dir(path)
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8", opener=_open_private) as fh:
        fh.write(json.dumps(lease.as_dict()))
    os.replace(tmp, path)


class _locked:
    """Cross-process critical section over the lease file (fcntl on a sibling lock file)."""

    def __init__(self, path: Path):
        self._lockfile = path.with_suffix(".lock")
        self._fh = None

    def __enter__(self):
        if fcntl is None:
            return self
        _private_dir(self._lockfile)
        self._fh = open(self._lockfile, "a+", encoding="utf-8", opener=_open_private)  # noqa: SIM115
        fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        if self._fh is None:
            return
        fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        self._fh.close()


def get() -> Lease:
    return _read(_path())


def on_change(listener: Callable[[Lease], None]) -> Callable[[], None]:
    """Subscribe to lease transitions made IN THIS PROCESS. Transitions made by another
    process are observed by reading, not by callback."""
    with _lock:
        _listeners.append(listener)

    def _off() -> None:
        with _lock:
            if listener in _listeners:
                _listeners.remove(listener)
    return _off


def _notify(lease: Lease) -> None:
    for cb in list(_listeners):
        try:
            cb(lease)
        except Exception:  # a broken subscriber must not wedge the handoff
            pass


def _transition(mutate: Callable[[Lease], bool]) -> Lease:
    path = _path()
    with _locked(path):
        lease = _read(path)
        if not mutate(lease):
            return lease
        lease.epoch += 1
        _write(path, lease)
    with _lock:
        _lock.notify_all()
    _notify(lease)
    return lease


def acquire(viewer_id: str, *, reason: str = "") -> Lease:
    """Human ``viewer_id`` takes control. Last writer wins: a second viewer evicts the first,
    and the RFB bridge closes the evicted socket so its UI drops to view-only."""
    def _m(lease: Lease) -> bool:
        if lease.holder == HUMAN and lease.viewer_id == viewer_id:
            return False  # already theirs: no epoch bump
        lease.holder, lease.viewer_id, lease.since = HUMAN, viewer_id, time.time()
        lease.reason = reason or ""
        return True
    return _transition(_m)


def release(viewer_id: Optional[str] = None, *, unless_human: bool = False) -> Lease:
    """Return control to the agent. With ``viewer_id`` only that holder may release (a stale
    viewer closing its window must not yank control from the one who took over after it).
    ``unless_human`` makes a bare release a no-op while any human holds. Callers read the
    returned lease's holder to learn whether anything happened."""
    def _m(lease: Lease) -> bool:
        if unless_human and lease.holder == HUMAN:
            logger.info("screen lease: bare release ignored, a human holds")
            return False
        if viewer_id is not None and lease.holder == HUMAN and lease.viewer_id != viewer_id:
            logger.info("screen lease: release by %r ignored, another viewer holds", viewer_id)
            return False
        if lease.holder == AGENT:
            # Already the agent's. Bumping the epoch here would make a legitimately admitted
            # in-flight agent action look overtaken and get voided.
            return False
        lease.holder, lease.viewer_id, lease.since, lease.reason = AGENT, None, time.time(), ""
        return True
    return _transition(_m)


def human_holds() -> bool:
    return get().holder == HUMAN


def viewer_may_send_input(viewer_id: str) -> bool:
    lease = get()
    return lease.holder == HUMAN and lease.viewer_id == viewer_id
