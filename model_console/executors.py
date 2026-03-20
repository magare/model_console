"""Agent executor – runs AI model CLIs as subprocesses.

Builds provider-specific commands (Claude, Codex, Gemini, mock), invokes them,
captures stdout/stderr, logs events, and parses the JSON output.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from time import monotonic

from .json_utils import extract_json_object
from .logging_utils import append_jsonl, ensure_dir, utc_now_iso, write_json
from .models import AgentConfig, AppConfig, CommandResult
from .safety import assert_command_safe
from .transcript import append_transcript_entry, extract_provider_trace


class AgentExecutor:
    def __init__(
        self,
        app_cfg: AppConfig,
        events_log: Path,
        commands_log: Path,
        transcript_log: Path | None = None,
        event_handler: Callable[[dict], None] | None = None,
    ) -> None:
        self.app_cfg = app_cfg
        self.events_log = events_log
        self.commands_log = commands_log
        self.transcript_log = transcript_log
        self.event_handler = event_handler

    def run_role(
        self,
        agent: AgentConfig,
        run_id: str,
        loop_id: str,
        role: str,
        prompt: str,
        schema_path: Path,
        round_dir: Path,
        attempt_index: int = 1,
    ) -> tuple[dict, CommandResult]:
        prompts_dir = round_dir / "prompts"
        raw_dir = round_dir / "raw"
        trace_dir = round_dir / "trace"
        ensure_dir(prompts_dir)
        ensure_dir(raw_dir)
        ensure_dir(trace_dir)

        prompt_name = f"{role.lower()}.attempt{attempt_index:02d}.prompt.txt"
        prompt_path = prompts_dir / prompt_name
        latest_prompt_path = prompts_dir / f"{role.lower()}.prompt.txt"
        self._write_attempt_file(prompt_path, latest_prompt_path, prompt)

        last_message_path = trace_dir / f"{role.lower()}.attempt{attempt_index:02d}.last_message.txt"
        latest_last_message_path = raw_dir / f"{role.lower()}.last_message.txt"

        command = self._build_command(
            agent,
            role,
            prompt,
            schema_path,
            round_dir,
            last_message_path,
        )
        assert_command_safe(command, self.app_cfg.policies)

        started = utc_now_iso()
        round_id = round_dir.name
        self._append_transcript(
            round_dir,
            {
                "timestamp": started,
                "event": "prompt_sent",
                "run_id": run_id,
                "loop_id": loop_id,
                "round_id": round_id,
                "attempt_index": attempt_index,
                "speaker": "orchestrator",
                "recipient": agent.agent_id,
                "role": role,
                "provider": agent.provider,
                "model": agent.model,
                "text": prompt,
            },
        )
        self._emit(
            {
                "timestamp": started,
                "event": "model_command_started",
                "round_id": round_id,
                "role": role,
                "agent_id": agent.agent_id,
                "provider": agent.provider,
                "model": agent.model,
                "attempt_index": attempt_index,
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

        stdout_path = raw_dir / f"{role.lower()}.attempt{attempt_index:02d}.stdout.log"
        latest_stdout_path = raw_dir / f"{role.lower()}.stdout.log"
        stderr_path = raw_dir / f"{role.lower()}.attempt{attempt_index:02d}.stderr.log"
        latest_stderr_path = raw_dir / f"{role.lower()}.stderr.log"
        self._write_attempt_file(stdout_path, latest_stdout_path, proc.stdout)
        self._write_attempt_file(stderr_path, latest_stderr_path, proc.stderr)
        self._sync_last_message_alias(last_message_path, latest_last_message_path)

        output_text = self._select_output_text(agent, proc.stdout, last_message_path)
        provider_trace = extract_provider_trace(
            agent.provider,
            proc.stdout,
            stderr=proc.stderr,
            final_text_override=output_text,
        )
        trace_path = trace_dir / f"{role.lower()}.attempt{attempt_index:02d}.provider_trace.json"
        latest_trace_path = trace_dir / f"{role.lower()}.provider_trace.json"
        write_json(trace_path, provider_trace)
        write_json(latest_trace_path, provider_trace)

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
                "attempt_index": attempt_index,
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
                "attempt_index": attempt_index,
            },
        )
        self._emit(
            {
                "timestamp": finished,
                "event": "model_command_completed",
                "round_id": round_id,
                "role": role,
                "agent_id": agent.agent_id,
                "provider": agent.provider,
                "model": agent.model,
                "exit_code": proc.returncode,
                "duration_ms": duration_ms,
                "attempt_index": attempt_index,
            }
        )

        for reasoning_text in provider_trace.reasoning:
            self._append_transcript(
                round_dir,
                {
                    "timestamp": finished,
                    "event": "thinking_emitted",
                    "run_id": run_id,
                    "loop_id": loop_id,
                    "round_id": round_id,
                    "attempt_index": attempt_index,
                    "speaker": agent.agent_id,
                    "recipient": "orchestrator",
                    "role": role,
                    "provider": agent.provider,
                    "model": agent.model,
                    "text": reasoning_text,
                },
            )

        if provider_trace.thought_tokens is not None:
            self._append_transcript(
                round_dir,
                {
                    "timestamp": finished,
                    "event": "thinking_tokens_reported",
                    "run_id": run_id,
                    "loop_id": loop_id,
                    "round_id": round_id,
                    "attempt_index": attempt_index,
                    "speaker": agent.agent_id,
                    "recipient": "orchestrator",
                    "role": role,
                    "provider": agent.provider,
                    "model": agent.model,
                    "thought_tokens": provider_trace.thought_tokens,
                    "text": f"Provider reported {provider_trace.thought_tokens} thought tokens.",
                },
            )

        messages = provider_trace.assistant_messages or ([provider_trace.final_text] if provider_trace.final_text else [])
        for message_text in messages:
            self._append_transcript(
                round_dir,
                {
                    "timestamp": finished,
                    "event": "model_response",
                    "run_id": run_id,
                    "loop_id": loop_id,
                    "round_id": round_id,
                    "attempt_index": attempt_index,
                    "speaker": agent.agent_id,
                    "recipient": "orchestrator",
                    "role": role,
                    "provider": agent.provider,
                    "model": agent.model,
                    "text": message_text,
                },
            )

        if proc.returncode != 0:
            raise RuntimeError(
                f"Agent `{agent.agent_id}` failed for role `{role}`: exit={proc.returncode}"
            )

        parsed = extract_json_object(output_text)
        return parsed, result

    def _build_command(
        self,
        agent: AgentConfig,
        role: str,
        prompt: str,
        schema_path: Path,
        round_dir: Path,
        last_message_path: Path,
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
            command = [
                cli,
                "exec",
                prompt,
                "--json",
                "--output-schema",
                str(schema_path),
                "--output-last-message",
                str(last_message_path),
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
        stdout: str,
        last_message_path: Path,
    ) -> str:
        provider = agent.provider.lower()
        if provider == "codex":
            if last_message_path.exists():
                return last_message_path.read_text(encoding="utf-8")
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

    def _append_transcript(self, round_dir: Path, payload: dict[str, object]) -> None:
        append_transcript_entry(self.transcript_log, round_dir, payload)

    def _write_attempt_file(self, attempt_path: Path, latest_path: Path, content: str) -> None:
        attempt_path.write_text(content, encoding="utf-8")
        latest_path.write_text(content, encoding="utf-8")

    def _sync_last_message_alias(self, attempt_path: Path, latest_path: Path) -> None:
        if attempt_path.exists():
            latest_path.write_text(attempt_path.read_text(encoding="utf-8"), encoding="utf-8")
