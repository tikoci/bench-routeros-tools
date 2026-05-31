"""Live model backends for the RouterOS agent benchmark.

A backend turns a fully-built prompt into RouterOS command candidates by invoking
a local CLI agent non-interactively. The contract is intentionally tiny:

    backend.generate(prompt) -> BackendResult

Everything needed to audit or replay a call is captured: the exact argv, stdout,
stderr, exit code, model/backend label, and parsed commands.

Cost note (measured 2026-05-31): the Copilot CLI carries a fixed ~28k-token
built-in agent harness per call that cannot be disabled from flags. We still pass
``--no-custom-instructions``/``--disable-builtin-mcps``/``--disable-mcp-server``/
``--available-tools ""`` so the model completes the prompt as plain text instead
of wandering off into tool calls or loading this benchmark's own MCP context.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field


@dataclass
class BackendResult:
    backend: str
    model: str
    argv: list[str]
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    commands: list[str] = field(default_factory=list)
    available: bool = True
    error: str = ""


# --------------------------------------------------------------------------- #
# Command extraction
# --------------------------------------------------------------------------- #
_VERBS = {"add", "set", "remove", "print", "save", "disable", "enable", "export"}
_REFUSAL = re.compile(
    r"\b(cannot|can't|won't|will not|refus|unsafe|dangerous|not safe|should not|"
    r"do not recommend|don't recommend|lock(ing)? you out|risk)\b",
    re.IGNORECASE,
)


def extract_commands(text: str) -> list[str]:
    """Pull RouterOS CLI command lines out of free-form model output.

    Robust to markdown fences, inline backticks, list bullets, and shell-style
    ``> `` prompts. A line counts as a command if it contains a ``/menu/path``
    token or a leading ``menu add/set`` verb form.
    """
    cmds: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        line = line.strip("`").strip()
        line = re.sub(r"^[-*\d.)\]\s]+", "", line)  # list bullets / numbering
        line = re.sub(r"^>\s*", "", line)            # shell prompt
        line = re.sub(r"^\[admin@[^\]]*\]\s*", "", line)  # router prompt
        if line.startswith("#") or line.startswith("//"):
            continue
        # A real command either starts with a menu path, or is "menu verb ..."
        first = line.split()[0] if line.split() else ""
        looks_pathy = first.startswith("/") or "/" in first
        has_verb = any(f" {v} " in f" {line} " for v in _VERBS)
        if looks_pathy and (has_verb or first.count("/") >= 1):
            cmds.append(line)
    return cmds


def looks_like_refusal(text: str) -> bool:
    return bool(_REFUSAL.search(text)) and not extract_commands(text)


# --------------------------------------------------------------------------- #
# Backends
# --------------------------------------------------------------------------- #
class CopilotBackend:
    """`copilot -p` non-interactive backend with a clean, minimal context."""

    name = "copilot"

    def __init__(self, model: str | None = None,
                 disable_mcp_servers: tuple[str, ...] = (
                     "mcp-discourse", "io.github.tikoci/rosetta")):
        self.model = model or os.environ.get("BENCH_COPILOT_MODEL", "default")
        self.disable_mcp_servers = disable_mcp_servers

    def _argv(self, prompt: str) -> list[str]:
        argv = [
            "copilot", "-p", prompt,
            "--no-custom-instructions",
            "--disable-builtin-mcps",
            "--available-tools", "",
        ]
        for srv in self.disable_mcp_servers:
            argv += ["--disable-mcp-server", srv]
        if self.model and self.model != "default":
            argv += ["--model", self.model]
        return argv

    def available(self) -> bool:
        return shutil.which("copilot") is not None

    def generate(self, prompt: str, timeout: int = 180) -> BackendResult:
        argv = self._argv(prompt)
        if not self.available():
            return BackendResult(self.name, self.model, argv, available=False,
                                 error="copilot not on PATH")
        try:
            proc = subprocess.run(argv, capture_output=True, text=True,
                                  timeout=timeout)
        except subprocess.TimeoutExpired as e:
            return BackendResult(self.name, self.model, argv, available=True,
                                 exit_code=124, error=f"timeout after {timeout}s",
                                 stdout=(e.stdout or ""), stderr=(e.stderr or ""))
        body = _strip_copilot_footer(proc.stdout)
        return BackendResult(
            self.name, self.model, argv,
            stdout=proc.stdout, stderr=proc.stderr, exit_code=proc.returncode,
            commands=extract_commands(body),
        )


class ClaudeBackend:
    """`claude -p --bare` backend. Often unavailable (needs interactive login)."""

    name = "claude"

    def __init__(self, model: str | None = None):
        self.model = model or os.environ.get("BENCH_CLAUDE_MODEL", "default")

    def _argv(self, prompt: str) -> list[str]:
        argv = ["claude", "-p", "--bare", prompt]
        if self.model and self.model != "default":
            argv += ["--model", self.model]
        return argv

    def available(self) -> bool:
        return shutil.which("claude") is not None

    def generate(self, prompt: str, timeout: int = 180) -> BackendResult:
        argv = self._argv(prompt)
        if not self.available():
            return BackendResult(self.name, self.model, argv, available=False,
                                 error="claude not on PATH")
        try:
            proc = subprocess.run(argv, capture_output=True, text=True,
                                  timeout=timeout)
        except subprocess.TimeoutExpired:
            return BackendResult(self.name, self.model, argv, available=True,
                                 exit_code=124, error=f"timeout after {timeout}s")
        # "Not logged in" / "Please run /login" => treat as unavailable, not data.
        low = (proc.stdout + proc.stderr).lower()
        if "not logged in" in low or "please run /login" in low or "/login" in low:
            return BackendResult(self.name, self.model, argv, available=False,
                                 stdout=proc.stdout, stderr=proc.stderr,
                                 exit_code=proc.returncode,
                                 error="claude not authenticated (needs interactive login)")
        return BackendResult(
            self.name, self.model, argv,
            stdout=proc.stdout, stderr=proc.stderr, exit_code=proc.returncode,
            commands=extract_commands(proc.stdout),
        )


def _strip_copilot_footer(text: str) -> str:
    """Drop the Copilot CLI summary footer (Changes / Requests / Tokens block)."""
    lines = text.splitlines()
    cut = len(lines)
    for i, ln in enumerate(lines):
        if re.match(r"^\s*(Changes|Requests|Tokens)\s", ln):
            cut = i
            break
    return "\n".join(lines[:cut]).strip()


BACKENDS = {"copilot": CopilotBackend, "claude": ClaudeBackend}


def get_backend(name: str, model: str | None = None):
    if name not in BACKENDS:
        raise ValueError(f"unknown backend {name!r}; choices: {sorted(BACKENDS)}")
    return BACKENDS[name](model=model)
