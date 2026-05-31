"""Adapter interfaces for future live-agent benchmark backends."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class AgentRunResult:
    approach: str
    task_id: str
    commands: list[str]
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    metadata: dict = field(default_factory=dict)


class AgentAdapter(Protocol):
    def run_task(self, task: dict, approach: str) -> AgentRunResult:
        """Return candidate RouterOS commands for a task under one approach."""


@dataclass
class CliAdapter:
    """Base class for CLI-backed adapters.

    Subclasses intentionally do not execute yet; the exact non-interactive flags
    for each CLI should be locked down before live results are treated as data.
    """

    executable: str
    repo_root: Path

    def build_prompt(self, task: dict, approach: str) -> str:
        return (
            f"Approach: {approach}\n"
            f"RouterOS version: {task.get('version', '7.x')}\n"
            f"Task: {task['intent']}\n\n"
            "Return only RouterOS CLI commands, one per line."
        )

    def run_task(self, task: dict, approach: str) -> AgentRunResult:
        raise NotImplementedError("live CLI invocation is intentionally not wired yet")


class ClaudeCliAdapter(CliAdapter):
    def __init__(self, repo_root: Path):
        super().__init__("claude", repo_root)


class CopilotCliAdapter(CliAdapter):
    def __init__(self, repo_root: Path):
        super().__init__("copilot", repo_root)


# --------------------------------------------------------------------------- #
# Concrete live adapter (implemented seam)
# --------------------------------------------------------------------------- #
class LiveAdapter:
    """Adapter that actually invokes a CLI backend and returns parsed commands.

    This is the realized form of the ``AgentAdapter`` protocol. It composes the
    approach-aware prompt builder (``harness.live.contexts``) with a CLI backend
    (``harness.live.backends``). Prefer ``harness/live/run_live.py`` for batch
    runs -- it adds caching, scoring, validation, and budget control around this.
    """

    def __init__(self, backend_name: str = "copilot", model: str = "default"):
        from harness.live.backends import get_backend
        self.backend = get_backend(backend_name, model)

    def run_task(self, task: dict, approach: str) -> AgentRunResult:
        from harness.live.contexts import build_prompt
        prompt, meta = build_prompt(task, approach)
        res = self.backend.generate(prompt)
        return AgentRunResult(
            approach=approach,
            task_id=task["id"],
            commands=res.commands,
            stdout=res.stdout,
            stderr=res.stderr,
            exit_code=res.exit_code,
            metadata={
                "backend": res.backend,
                "model": res.model,
                "argv": res.argv,
                "available": res.available,
                "error": res.error,
                **meta,
            },
        )

