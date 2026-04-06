from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from model_console.cli import build_parser, cmd_resume
from model_console.config import load_app_config
from model_console.engine import LoopEngine
from model_console.eval import run_eval_commands
from model_console.executors import AgentExecutor
from model_console.models import AgentConfig, AppConfig, LoopConfig, Policies, RoleAssignmentConfig


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
SCHEMAS_DIR = REPO_ROOT / "schemas"
PROMPTS_DIR = REPO_ROOT / "prompts"


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build_workspace(root: Path) -> Path:
    workspace = root / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    _write_text(
        workspace / "config" / "agents.yaml",
        f"""agents:
  mock_impl:
    provider: mock
    model: mock-implementer
    cli_path: python3
    extra_args: []
    env:
      PYTHONPATH: "{SRC_ROOT}"

  mock_rev:
    provider: mock
    model: mock-reviewer
    cli_path: python3
    extra_args: []
    env:
      PYTHONPATH: "{SRC_ROOT}"
""",
    )
    _write_text(
        workspace / "config" / "loops.yaml",
        """loops:
  bootstrap_loop:
    artifact_kind: plan
    max_rounds: 2
    score_threshold: 80
    stagnation_rounds: 1
    stagnation_epsilon: 0.1
    swap_next_round: false
    swap_on_failure: true
    role_assignment:
      strategy: static
      implementers: [mock_impl]
      reviewers: [mock_rev]
      implementer_count: 1
      reviewer_count: 1
    eval_commands:
      - "echo 'bootstrap eval ok'"
""",
    )
    _write_text(
        workspace / "config" / "policies.yaml",
        """policies:
  allow_command_prefixes:
    - python3
    - echo
    - zsh
  deny_command_patterns: []
  run_timeout_seconds: 1
  model_timeout_seconds: 1
  max_completed_runs: 10
""",
    )
    return workspace


class EvalHardeningTests(unittest.TestCase):
    def test_run_eval_commands_returns_failed_result_on_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            app_cfg = AppConfig(
                workspace_root=workspace,
                run_root=workspace / "runs",
                agents={},
                loops={},
                policies=Policies(
                    allow_command_prefixes=["zsh", "python3"],
                    deny_command_patterns=[],
                    run_timeout_seconds=1,
                    model_timeout_seconds=1,
                    max_completed_runs=None,
                ),
                schemas_dir=SCHEMAS_DIR,
                prompts_dir=PROMPTS_DIR,
            )

            result = run_eval_commands(
                app_cfg=app_cfg,
                commands=["python3 -c 'import time; time.sleep(2)'"],
                events_log=workspace / "events.jsonl",
                commands_log=workspace / "commands.jsonl",
            )

            self.assertFalse(result.passed)
            self.assertEqual(result.commands[0]["result"]["exit_code"], -1)
            self.assertEqual(result.commands[0]["result"]["error_type"], "timeout")
            self.assertIn("timed out", result.commands[0]["result"]["stderr"])


class ExecutorHardeningTests(unittest.TestCase):
    def test_run_role_wraps_missing_cli_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run_root = workspace / "runs"
            app_cfg = AppConfig(
                workspace_root=workspace,
                run_root=run_root,
                agents={},
                loops={},
                policies=Policies(
                    allow_command_prefixes=["missing-copilot"],
                    deny_command_patterns=[],
                    run_timeout_seconds=1,
                    model_timeout_seconds=1,
                    max_completed_runs=None,
                ),
                schemas_dir=SCHEMAS_DIR,
                prompts_dir=PROMPTS_DIR,
            )
            executor = AgentExecutor(
                app_cfg=app_cfg,
                events_log=run_root / "events.jsonl",
                commands_log=run_root / "commands.jsonl",
                transcript_log=run_root / "transcript.jsonl",
            )
            round_dir = workspace / "r01"
            round_dir.mkdir(parents=True, exist_ok=True)

            agent = AgentConfig(
                agent_id="copilot_primary",
                provider="copilot",
                model="",
                cli_path="missing-copilot",
                env={},
            )

            with self.assertRaisesRegex(RuntimeError, "copilot_primary"):
                executor.run_role(
                    agent=agent,
                    run_id="hardening-test",
                    loop_id="bootstrap_loop",
                    role="IMPLEMENTER",
                    prompt="Return JSON",
                    schema_path=SCHEMAS_DIR / "implementer.output.schema.json",
                    round_dir=round_dir,
                )


class CLIHardeningTests(unittest.TestCase):
    def test_cmd_resume_rejects_malformed_state_file_with_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run_dir = workspace / "runs" / "broken"
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_text(run_dir / "state.json", "{invalid json")

            args = build_parser().parse_args(
                ["resume", "--run-id", "broken", "--workspace", str(workspace)]
            )

            with self.assertRaisesRegex(ValueError, "Malformed run state"):
                cmd_resume(args)


class ConfigHardeningTests(unittest.TestCase):
    def test_load_app_config_rejects_invalid_yaml_with_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            config_dir = workspace / "config"
            config_dir.mkdir(parents=True, exist_ok=True)
            _write_text(config_dir / "agents.yaml", "agents: [")
            _write_text(
                config_dir / "loops.yaml",
                """loops:
  bootstrap_loop:
    role_assignment:
      implementers: [mock_impl]
      reviewers: [mock_rev]
""",
            )
            _write_text(config_dir / "policies.yaml", "policies: {}")

            with self.assertRaisesRegex(ValueError, "Invalid YAML"):
                load_app_config(
                    workspace_root=workspace,
                    config_dir=config_dir,
                    schemas_dir=workspace / "schemas",
                    prompts_dir=workspace / "prompts",
                    run_root=workspace / "runs",
                )

    def test_load_app_config_rejects_non_mapping_agent_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            config_dir = workspace / "config"
            config_dir.mkdir(parents=True, exist_ok=True)
            _write_text(
                config_dir / "agents.yaml",
                """agents:
  bad_agent:
    - invalid
""",
            )
            _write_text(
                config_dir / "loops.yaml",
                """loops:
  bootstrap_loop:
    role_assignment:
      implementers: [bad_agent]
      reviewers: [bad_agent]
""",
            )
            _write_text(config_dir / "policies.yaml", "policies: {}")

            with self.assertRaisesRegex(ValueError, "Agent `bad_agent` config must be a mapping"):
                load_app_config(
                    workspace_root=workspace,
                    config_dir=config_dir,
                    schemas_dir=workspace / "schemas",
                    prompts_dir=workspace / "prompts",
                    run_root=workspace / "runs",
                )


class EngineHardeningTests(unittest.TestCase):
    def test_read_task_text_uses_cached_state_when_task_file_is_not_utf8(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            task_file = workspace / "tasks" / "broken.md"
            task_file.parent.mkdir(parents=True, exist_ok=True)
            task_file.write_bytes(b"\xff\xfe\x00")

            app_cfg = AppConfig(
                workspace_root=workspace,
                run_root=workspace / "runs",
                agents={},
                loops={
                    "bootstrap_loop": LoopConfig(
                        loop_id="bootstrap_loop",
                        artifact_kind="plan",
                        max_rounds=1,
                        score_threshold=80.0,
                        stagnation_rounds=1,
                        stagnation_epsilon=0.1,
                        swap_next_round=False,
                        swap_on_failure=True,
                        role_assignment=RoleAssignmentConfig(
                            strategy="static",
                            implementers=["mock_impl"],
                            reviewers=["mock_rev"],
                            implementer_count=1,
                            reviewer_count=1,
                        ),
                    )
                },
                policies=Policies(
                    allow_command_prefixes=["python3"],
                    deny_command_patterns=[],
                    run_timeout_seconds=1,
                    model_timeout_seconds=1,
                    max_completed_runs=None,
                ),
                schemas_dir=SCHEMAS_DIR,
                prompts_dir=PROMPTS_DIR,
            )
            engine = LoopEngine(
                app_cfg=app_cfg,
                loop_id="bootstrap_loop",
                task_file=task_file,
                run_id="utf8-fallback",
            )
            _write_text(
                engine.state_file,
                json.dumps({"task_text": "cached task text"}, indent=2),
            )

            self.assertEqual(engine._read_task_text(), "cached task text")
