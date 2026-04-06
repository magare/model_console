"""Configuration loader.

Reads agents.yaml, loops.yaml, and policies.yaml from the config directory
and assembles them into a typed AppConfig used by the rest of the system.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from ..models import (
    AgentConfig,
    AppConfig,
    LoopConfig,
    Policies,
    RoleAssignmentConfig,
)
from ..validation_helpers import require_mapping, require_string_field


def _read_yaml(path: Path) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(f"Missing config file: {path}")
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"Could not read config file: {path}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in config file: {path}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Config must be a mapping: {path}")
    return data


def load_app_config(
    workspace_root: Path,
    config_dir: Path,
    schemas_dir: Path,
    prompts_dir: Path,
    run_root: Path,
) -> AppConfig:
    agents_raw = _read_yaml(config_dir / "agents.yaml")
    loops_raw = _read_yaml(config_dir / "loops.yaml")
    policies_raw = _read_yaml(config_dir / "policies.yaml")

    agents_root = require_mapping(agents_raw.get("agents") or {}, "`agents` section")
    agents: dict[str, AgentConfig] = {}
    for agent_id, raw in agents_root.items():
        raw = require_mapping(raw, f"Agent `{agent_id}` config")
        agents[agent_id] = AgentConfig(
            agent_id=agent_id,
            provider=require_string_field(raw, "provider", f"Agent `{agent_id}`"),
            model=require_string_field(
                raw,
                "model",
                f"Agent `{agent_id}`",
                allow_empty=True,
            ),
            cli_path=raw.get("cli_path"),
            extra_args=list(raw.get("extra_args") or []),
            env=dict(raw.get("env") or {}),
        )

    loops_root = require_mapping(loops_raw.get("loops") or {}, "`loops` section")
    loops: dict[str, LoopConfig] = {}
    for loop_id, raw in loops_root.items():
        raw = require_mapping(raw, f"Loop `{loop_id}` config")
        role_raw = require_mapping(
            raw.get("role_assignment") or {},
            f"Loop `{loop_id}` role_assignment",
        )
        role_cfg = RoleAssignmentConfig(
            strategy=str(role_raw.get("strategy", "static")),
            implementers=list(role_raw.get("implementers") or []),
            reviewers=list(role_raw.get("reviewers") or []),
            implementer_count=int(role_raw.get("implementer_count", 1)),
            reviewer_count=int(role_raw.get("reviewer_count", 1)),
        )

        loops[loop_id] = LoopConfig(
            loop_id=loop_id,
            artifact_kind=str(raw.get("artifact_kind", "code")),
            max_rounds=int(raw.get("max_rounds", 3)),
            score_threshold=float(raw.get("score_threshold", 85)),
            stagnation_rounds=int(raw.get("stagnation_rounds", 2)),
            stagnation_epsilon=float(raw.get("stagnation_epsilon", 0.5)),
            swap_next_round=bool(raw.get("swap_next_round", False)),
            swap_on_failure=bool(raw.get("swap_on_failure", True)),
            execution_mode=str(raw.get("execution_mode", "standard")),
            max_step_retries=int(raw.get("max_step_retries", 1)),
            require_dependency_closure=bool(raw.get("require_dependency_closure", False)),
            require_final_integration_step=bool(
                raw.get("require_final_integration_step", False)
            ),
            role_assignment=role_cfg,
            eval_commands=list(raw.get("eval_commands") or []),
        )

    policy_root = require_mapping(policies_raw.get("policies") or {}, "`policies` section")
    policies = Policies(
        allow_command_prefixes=list(policy_root.get("allow_command_prefixes") or []),
        deny_command_patterns=list(policy_root.get("deny_command_patterns") or []),
        run_timeout_seconds=int(policy_root.get("run_timeout_seconds", 600)),
        model_timeout_seconds=int(policy_root.get("model_timeout_seconds", 240)),
        max_completed_runs=(
            int(policy_root["max_completed_runs"])
            if policy_root.get("max_completed_runs") is not None
            else None
        ),
    )

    if not agents:
        raise ValueError("No agents configured in config/agents.yaml")
    if not loops:
        raise ValueError("No loops configured in config/loops.yaml")

    return AppConfig(
        workspace_root=workspace_root,
        run_root=run_root,
        agents=agents,
        loops=loops,
        policies=policies,
        schemas_dir=schemas_dir,
        prompts_dir=prompts_dir,
    )
