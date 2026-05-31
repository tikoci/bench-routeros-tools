"""Boot a CHR (RouterOS) VM in QEMU and validate commands via /console/inspect.

This is the "ground truth" validator. It is best-effort: if QEMU/the image is
missing or the VM doesn't answer REST in time, callers get ChrUnavailable and
fall back to the static-schema oracle (rosetta). That realizes the user's
"both" choice: CHR when available, static fallback otherwise.

Validation strategy (offline, never mutates the device):
  - `request:"child"` to confirm each path segment exists.
  - `request:"syntax"` on the leaf to confirm the command + its named args are
    real. Unknown path/arg => the command is invalid.
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request

CHR_IMG_CANDIDATES = [
    os.environ.get("CHR_IMG", ""),
    "~/GitHub/chr-armed/Machines/chr-7.22.1-x86.img",
    "~/GitHub/chr-armed/Machines/chr-7.22.1-x86.qcow2",
]
DEFAULT_PORT = 9180
USER = os.environ.get("CHR_USER", "admin")
PASSWORD = os.environ.get("CHR_PASSWORD", "")


class ChrUnavailable(RuntimeError):
    pass


def _img() -> str | None:
    for c in CHR_IMG_CANDIDATES:
        if not c:
            continue
        p = os.path.expanduser(c)
        if os.path.exists(p):
            return p
    return None


def _accel() -> str:
    if os.uname().sysname == "Darwin":
        try:
            out = subprocess.check_output(["sysctl", "-n", "kern.hv_support"]).strip()
            if out == b"1":
                return "hvf"
        except Exception:
            pass
    if os.path.exists("/dev/kvm") and os.access("/dev/kvm", os.W_OK):
        return "kvm"
    return "tcg"


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _auth_header() -> dict:
    tok = base64.b64encode(f"{USER}:{PASSWORD}".encode()).decode()
    return {"Authorization": f"Basic {tok}", "Content-Type": "application/json"}


class Chr:
    def __init__(self, port: int = DEFAULT_PORT, boot_timeout: int = 180):
        self.port = port
        self.boot_timeout = int(os.environ.get("CHR_BOOT_TIMEOUT", boot_timeout))
        self.proc: subprocess.Popen | None = None
        self.base = f"http://127.0.0.1:{port}"

    # -- lifecycle --------------------------------------------------------- #
    def start(self) -> "Chr":
        if shutil.which("qemu-system-x86_64") is None:
            raise ChrUnavailable("qemu-system-x86_64 not found")
        img = _img()
        if img is None:
            raise ChrUnavailable("no CHR image found")
        if self._rest_ready():
            return self  # already running (reuse)

        log = open("/tmp/chr-benchmark.log", "wb")
        self.proc = subprocess.Popen(
            [
                "qemu-system-x86_64", "-M", "q35", "-m", "256", "-smp", "1",
                "-accel", _accel(),
                "-drive", f"file={img},format={'qcow2' if img.endswith('qcow2') else 'raw'},if=virtio",
                "-netdev", f"user,id=net0,hostfwd=tcp::{self.port}-:80",
                "-device", "virtio-net-pci,netdev=net0",
                "-display", "none", "-serial", "file:/tmp/chr-serial.log",
            ],
            stdout=log, stderr=log,
        )
        try:
            deadline = time.time() + self.boot_timeout
            while time.time() < deadline:
                if self.proc.poll() is not None:
                    raise ChrUnavailable("qemu exited during boot (see /tmp/chr-benchmark.log)")
                if self._rest_ready():
                    return self
                time.sleep(2)
            raise ChrUnavailable(f"CHR REST not ready within {self.boot_timeout}s")
        except Exception:
            self.stop()
            raise

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def _rest_ready(self) -> bool:
        if not _port_open(self.port):
            return False
        try:
            self._rest("GET", "/rest/system/resource", timeout=3)
            return True
        except Exception:
            return False

    # -- REST -------------------------------------------------------------- #
    def _rest(self, method: str, path: str, body: dict | None = None, timeout: int = 10):
        data = json.dumps(body).encode() if body is not None else None
        last_error: Exception | None = None
        for attempt in range(5):
            req = urllib.request.Request(self.base + path, data=data, method=method,
                                         headers=_auth_header())
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    raw = r.read().decode()
                    return json.loads(raw) if raw.strip() else {}
            except urllib.error.HTTPError:
                raise
            except (ConnectionResetError, TimeoutError, urllib.error.URLError, OSError) as e:
                last_error = e
                if attempt == 4:
                    break
                time.sleep(1 + attempt)
        raise last_error if last_error else ChrUnavailable("REST request failed")

    def inspect(self, request: str, path: str) -> object:
        """Call /console/inspect. `path` is comma-separated (e.g. 'ip,address')."""
        return self._rest("POST", "/rest/console/inspect",
                          {"request": request, "path": path})

    # -- command validation ------------------------------------------------ #
    def validate(self, command: str) -> tuple[bool, str]:
        """Return (is_valid, detail). Validates path existence via inspect.

        Conservative: a command is valid if every menu path segment resolves
        through `request:"child"`. Argument-level validation uses `syntax`.
        """
        tokens = command.strip().split()
        if not tokens:
            return False, "empty"
        raw_path = tokens[0]
        verbs = {"add", "set", "remove", "print", "save", "disable", "enable", "export"}
        segs = [s for s in raw_path.split("/") if s]
        verb = None
        # verb may be the trailing path segment (/ip/route/add) ...
        if segs and segs[-1] in verbs:
            verb = segs[-1]
            segs = segs[:-1]
        # ... or the second whitespace token (/ip/route add ...)
        elif len(tokens) > 1 and tokens[1] in verbs:
            verb = tokens[1]
        # walk the tree
        prefix = ""
        for i, seg in enumerate(segs):
            try:
                children = self.inspect("child", ",".join(segs[:i]) if i else "")
            except urllib.error.HTTPError as e:
                return False, f"http {e.code} at '{prefix}'"
            except Exception as e:
                return False, f"inspect error: {e}"
            names = _child_names(children)
            if names is not None and seg not in names:
                return False, f"unknown path segment '{seg}' under '/{'/'.join(segs[:i])}'"
            prefix = "/" + "/".join(segs[: i + 1])

        # argument-level validation for add/set (catches hallucinated properties)
        if verb in {"add", "set"} and "[find" not in command:
            args = _parse_args(command)
            if args:
                try:
                    syntax = self.inspect("syntax", ",".join(segs + [verb]))
                    valid = _syntax_symbols(syntax)
                except Exception:
                    valid = None
                if valid:
                    unknown = [a for a in args if a not in valid]
                    if unknown:
                        return False, f"unknown argument(s) {unknown} for /{'/'.join(segs)} {verb}"
        return True, f"path ok ({'/'.join(segs)}{(' verb=' + verb) if verb else ''})"


def _child_names(resp: object) -> set[str] | None:
    """Extract child node names from an inspect response, or None if unknown shape."""
    if isinstance(resp, list):
        out = set()
        for item in resp:
            if isinstance(item, dict):
                nm = item.get("name") or item.get("node") or item.get("token")
                if nm:
                    out.add(str(nm))
        return out or None
    return None


def _syntax_symbols(resp: object) -> set[str] | None:
    """Valid argument names from a `request:'syntax'` response."""
    if isinstance(resp, list):
        out = set()
        for item in resp:
            if isinstance(item, dict) and item.get("symbol-type") == "explanation":
                sym = item.get("symbol")
                if sym:
                    out.add(str(sym))
        return out or None
    return None


def _parse_args(command: str) -> list[str]:
    """Extract argument names (the `key` in key=value) from a command string."""
    import re

    # strip the leading path token
    rest = command.strip().split(None, 1)
    body = rest[1] if len(rest) > 1 else ""
    return re.findall(r"(?:^|\s)([a-z][a-z0-9-]*)=", body)
