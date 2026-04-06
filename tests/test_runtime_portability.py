from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from model_console.agents.command_builder import build_agent_command
from model_console.models import AgentConfig, AppConfig, Policies
from model_console.safety import assert_command_safe


class ShellPortabilityTests(unittest.TestCase):
    def test_build_shell_command_uses_powershell_on_windows(self) -> None:
        from model_console.runtime import build_shell_command

        def _which(name: str) -> str | None:
            if name == "powershell":
                return r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
            return None

        with patch("shutil.which", side_effect=_which):
            command = build_shell_command("python -m unittest", system="Windows")

        self.assertEqual(
            command,
            [
                "powershell",
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "python -m unittest",
            ],
        )

    def test_assert_command_safe_accepts_powershell_wrapper_for_allowlisted_inner_command(self) -> None:
        policies = Policies(
            allow_command_prefixes=["python3"],
            deny_command_patterns=[],
            run_timeout_seconds=1,
            model_timeout_seconds=1,
            max_completed_runs=None,
        )

        assert_command_safe(
            [
                "pwsh",
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "python -m unittest",
            ],
            policies,
        )


class MockCommandPortabilityTests(unittest.TestCase):
    def test_mock_provider_falls_back_to_current_python_when_python3_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            round_dir = workspace / "rounds" / "r01"
            round_dir.mkdir(parents=True, exist_ok=True)
            schema_path = workspace / "schema.json"
            schema_path.write_text('{"type":"object"}', encoding="utf-8")

            app_cfg = AppConfig(
                workspace_root=workspace,
                run_root=workspace / "runs",
                agents={},
                loops={},
                policies=Policies(
                    allow_command_prefixes=["python3"],
                    deny_command_patterns=[],
                    run_timeout_seconds=1,
                    model_timeout_seconds=1,
                    max_completed_runs=None,
                ),
                schemas_dir=workspace / "schemas",
                prompts_dir=workspace / "prompts",
            )
            agent = AgentConfig(
                agent_id="mock_impl",
                provider="mock",
                model="mock-implementer",
                cli_path="python3",
                extra_args=[],
                env={},
            )

            with patch("shutil.which", return_value=None):
                command = build_agent_command(
                    app_cfg=app_cfg,
                    agent=agent,
                    role="IMPLEMENTER",
                    prompt="Return JSON",
                    schema_path=schema_path,
                    round_dir=round_dir,
                    last_message_path=round_dir / "raw" / "implementer.last_message.txt",
                )

        self.assertEqual(command[0], sys.executable)


if __name__ == "__main__":
    unittest.main()
