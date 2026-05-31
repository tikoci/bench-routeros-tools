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

