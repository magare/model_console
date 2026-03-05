from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from time import monotonic

from .json_utils import extract_json_object
from .logging_utils import append_jsonl, ensure_dir, utc_now_iso
from .models import AgentConfig, AppConfig, CommandResult
from .safety import assert_command_safe


class AgentExecutor:
    def __init__(
        self,
        app_cfg: AppConfig,
        events_log: Path,
        commands_log: Path,
        event_handler: Callable[[dict], None] | None = None,
    ) -> None:
        self.app_cfg = app_cfg
        self.events_log = events_log
        self.commands_log = commands_log
        self.event_handler = event_handler

    def run_role(
        self,
        agent: AgentConfig,
        role: str,
        prompt: str,
        schema_path: Path,
        round_dir: Path,
    ) -> tuple[dict, CommandResult]:
        prompts_dir = round_dir / "prompts"
        raw_dir = round_dir / "raw"
        ensure_dir(prompts_dir)
        ensure_dir(raw_dir)

        prompt_path = prompts_dir / f"{role.lower()}.prompt.txt"
        prompt_path.write_text(prompt, encoding="utf-8")

        command = self._build_command(agent, role, prompt, schema_path, round_dir)
        assert_command_safe(command, self.app_cfg.policies)

        started = utc_now_iso()
        self._emit(
            {
                "timestamp": started,
                "event": "model_command_started",
                "round_id": round_dir.name,
                "role": role,
                "agent_id": agent.agent_id,
                "provider": agent.provider,
                "model": agent.model,
                "command_preview": self._command_preview(command),
            }
        )
        start = monotonic()
        env = os.environ.copy()
        env.update(agent.env)
        proc = subprocess.run(
            command,
            cwd=self.app_cfg.workspace_root,
            capture_output=True,
            text=True,
            timeout=self.app_cfg.policies.model_timeout_seconds,
            env=env,
        )
        duration_ms = int((monotonic() - start) * 1000)
        finished = utc_now_iso()

        result = CommandResult(
            command=command,
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            started_at=started,
            finished_at=finished,
            duration_ms=duration_ms,
        )

        (raw_dir / f"{role.lower()}.stdout.log").write_text(proc.stdout, encoding="utf-8")
        (raw_dir / f"{role.lower()}.stderr.log").write_text(proc.stderr, encoding="utf-8")

        append_jsonl(
            self.commands_log,
            {
                "timestamp": finished,
                "kind": "model_command",
                "role": role,
                "agent_id": agent.agent_id,
                "provider": agent.provider,
                "command": command,
                "exit_code": proc.returncode,
                "duration_ms": duration_ms,
                "round_dir": str(round_dir),
            },
        )

        append_jsonl(
            self.events_log,
            {
                "timestamp": finished,
                "event": "model_command_completed",
                "round_id": round_dir.name,
                "role": role,
                "agent_id": agent.agent_id,
                "provider": agent.provider,
                "model": agent.model,
                "exit_code": proc.returncode,
                "duration_ms": duration_ms,
            },
        )
        self._emit(
            {
                "timestamp": finished,
                "event": "model_command_completed",
                "round_id": round_dir.name,
                "role": role,
                "agent_id": agent.agent_id,
                "provider": agent.provider,
                "model": agent.model,
                "exit_code": proc.returncode,
                "duration_ms": duration_ms,
            }
        )

        if proc.returncode != 0:
            raise RuntimeError(
                f"Agent `{agent.agent_id}` failed for role `{role}`: exit={proc.returncode}"
            )

        output_text = self._select_output_text(agent, role, round_dir, proc.stdout)
        parsed = extract_json_object(output_text)
        return parsed, result

    def _build_command(
        self,
        agent: AgentConfig,
        role: str,
        prompt: str,
        schema_path: Path,
        round_dir: Path,
    ) -> list[str]:
        provider = agent.provider.lower()
        cli = agent.cli_path or provider
        model = agent.model
        workspace = str(self.app_cfg.workspace_root)

        if provider == "claude":
            command = [
                cli,
                "-p",
                prompt,
                "--output-format",
                "json",
                "--json-schema",
                str(schema_path),
                "--model",
                model,
                "--max-turns",
                "8",
                "--permission-mode",
                "default",
                "--add-dir",
                workspace,
            ]
        elif provider == "codex":
            last_message = round_dir / "raw" / f"{role.lower()}.last_message.txt"
            command = [
                cli,
                "exec",
                prompt,
                "--json",
                "--output-schema",
                str(schema_path),
                "--output-last-message",
                str(last_message),
                "-m",
                model,
                "-C",
                workspace,
                "--skip-git-repo-check",
                "--sandbox",
                "workspace-write",
                "--full-auto",
            ]
        elif provider == "gemini":
            command = [
                cli,
                "-p",
                prompt,
                "--output-format",
                "json",
                "--model",
                model,
                "--approval-mode",
                "default",
                "--include-directories",
                workspace,
            ]
        elif provider == "mock":
            prompt_file = round_dir / "prompts" / f"{role.lower()}.prompt.txt"
            command = [
                "python3",
                "-m",
                "model_console.mock_agent",
                "--role",
                role,
                "--prompt-file",
                str(prompt_file),
                "--model-id",
                model,
            ]
        else:
            raise ValueError(f"Unsupported provider: {provider}")

        command.extend(agent.extra_args)
        return command

    def _select_output_text(
        self,
        agent: AgentConfig,
        role: str,
        round_dir: Path,
        stdout: str,
    ) -> str:
        provider = agent.provider.lower()
        if provider == "codex":
            last_message = round_dir / "raw" / f"{role.lower()}.last_message.txt"
            if last_message.exists():
                return last_message.read_text(encoding="utf-8")
        if provider == "gemini":
            try:
                payload = json.loads(stdout)
                if isinstance(payload, dict):
                    response = payload.get("response")
                    if isinstance(response, str):
                        return response
            except json.JSONDecodeError:
                pass
        return stdout

    def _emit(self, event: dict) -> None:
        if self.event_handler is not None:
            self.event_handler(event)

    def _command_preview(self, command: list[str]) -> str:
        if not command:
            return ""
        if len(command) >= 3 and command[0] == "codex" and command[1] == "exec":
            return "codex exec <PROMPT> ..."
        if len(command) >= 3 and command[1] == "-p":
            return f"{command[0]} -p <PROMPT> ..."
        return " ".join(command[:8]) + (" ..." if len(command) > 8 else "")
