from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AgentConfig:
    agent_id: str
    provider: str
    model: str
    cli_path: str | None = None
    extra_args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RoleAssignmentConfig:
    strategy: str
    implementers: list[str]
    reviewers: list[str]
    implementer_count: int = 1
    reviewer_count: int = 1


@dataclass(frozen=True)
class LoopConfig:
    loop_id: str
    artifact_kind: str
    max_rounds: int
    score_threshold: float
    stagnation_rounds: int
    stagnation_epsilon: float
    swap_next_round: bool
    swap_on_failure: bool
    role_assignment: RoleAssignmentConfig
    execution_mode: str = "standard"
    max_step_retries: int = 1
    require_dependency_closure: bool = False
    require_final_integration_step: bool = False
    eval_commands: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Policies:
    allow_command_prefixes: list[str]
    deny_command_patterns: list[str]
    run_timeout_seconds: int = 600
    model_timeout_seconds: int = 240
    max_completed_runs: int | None = None


@dataclass(frozen=True)
class AppConfig:
    workspace_root: Path
    run_root: Path
    agents: dict[str, AgentConfig]
    loops: dict[str, LoopConfig]
    policies: Policies
    schemas_dir: Path
    prompts_dir: Path


@dataclass(frozen=True)
class Assignment:
    implementers: list[str]
    reviewers: list[str]


@dataclass
class CommandResult:
    command: list[str]
    exit_code: int
    stdout: str
    stderr: str
    started_at: str
    finished_at: str
    duration_ms: int


@dataclass
class EvalResult:
    passed: bool
    commands: list[dict[str, Any]]


@dataclass
class RoundResult:
    round_id: str
    assignment: Assignment
    implementer_output: dict[str, Any]
    reviewer_outputs: list[dict[str, Any]]
    merged_review: dict[str, Any]
    eval_result: EvalResult
    score: float
    terminated: bool
    failure: bool
    rollback_applied: bool
    notes: list[str] = field(default_factory=list)
