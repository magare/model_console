from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from model_console.models import AppConfig, Policies


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMAS_DIR = REPO_ROOT / "schemas"
PROMPTS_DIR = REPO_ROOT / "prompts"


class PathHelperTests(unittest.TestCase):
    def test_resolve_within_workspace_accepts_relative_paths(self) -> None:
        from model_console.paths import resolve_within_workspace

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)

            resolved = resolve_within_workspace(workspace, "tasks/inbox/demo.md", "--task")

            self.assertEqual(
                resolved,
                workspace.resolve() / "tasks" / "inbox" / "demo.md",
            )

    def test_resolve_within_workspace_rejects_workspace_escape(self) -> None:
        from model_console.paths import resolve_within_workspace

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)

            with self.assertRaisesRegex(ValueError, "must stay inside workspace"):
                resolve_within_workspace(workspace, "../outside.txt", "--task")


class CommandBuilderTests(unittest.TestCase):
    def test_build_agent_command_inlines_claude_schema(self) -> None:
        from model_console.command_builder import build_agent_command
        from model_console.models import AgentConfig

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            round_dir = workspace / "r01"
            round_dir.mkdir(parents=True, exist_ok=True)
            schema_path = workspace / "schema.json"
            schema_path.write_text(
                '{"type":"object","required":["ok"],"properties":{"ok":{"type":"boolean"}}}',
                encoding="utf-8",
            )
            agent = AgentConfig(
                agent_id="claude_primary",
                provider="claude",
                model="claude-sonnet-4",
                cli_path="claude",
            )

            command = build_agent_command(
                app_cfg=_test_app_config(workspace),
                agent=agent,
                role="IMPLEMENTER",
                prompt="Return JSON",
                schema_path=schema_path,
                round_dir=round_dir,
                last_message_path=round_dir / "last_message.txt",
            )

            schema_flag_index = command.index("--json-schema") + 1
            self.assertEqual(command[schema_flag_index], schema_path.read_text(encoding="utf-8"))
            self.assertNotEqual(command[schema_flag_index], str(schema_path))

    def test_build_agent_command_omits_blank_copilot_model(self) -> None:
        from model_console.command_builder import build_agent_command
        from model_console.models import AgentConfig

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            round_dir = workspace / "r01"
            round_dir.mkdir(parents=True, exist_ok=True)
            agent = AgentConfig(
                agent_id="copilot_primary",
                provider="copilot",
                model="",
                cli_path="copilot",
            )

            command = build_agent_command(
                app_cfg=_test_app_config(workspace),
                agent=agent,
                role="IMPLEMENTER",
                prompt="Return JSON",
                schema_path=SCHEMAS_DIR / "implementer.output.schema.json",
                round_dir=round_dir,
                last_message_path=round_dir / "last_message.txt",
            )

            self.assertNotIn("--model", command)


def _test_app_config(workspace_root: Path) -> AppConfig:
    return AppConfig(
        workspace_root=workspace_root,
        run_root=workspace_root / "runs",
        agents={},
        loops={},
        policies=Policies(
            allow_command_prefixes=[],
            deny_command_patterns=[],
        ),
        schemas_dir=SCHEMAS_DIR,
        prompts_dir=PROMPTS_DIR,
    )
