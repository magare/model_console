"""Agent executor – runs AI model CLIs as subprocesses.

Builds provider-specific commands (Claude, Codex, Copilot, Gemini, mock),
invokes them, captures stdout/stderr, logs events, and parses the JSON output.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from time import monotonic
from typing import NoReturn

from .command_builder import build_agent_command, select_provider_output_text
from ..json_utils import extract_json_object
from ..observability.logging import append_jsonl, ensure_dir, utc_now_iso, write_json
from ..models import AgentConfig, AppConfig, CommandResult
from ..safety import assert_command_safe
from ..observability.transcript import append_transcript_entry, extract_provider_trace


class AgentExecutor:
    """Run one provider-backed role attempt and persist all round artifacts."""

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
        # Keep immutable attempt snapshots and a latest alias so the UI and
        # debugging workflows can inspect both the full history and the current view.
        self._write_attempt_file(prompt_path, latest_prompt_path, prompt)

        last_message_path = raw_dir / f"{role.lower()}.attempt{attempt_index:02d}.last_message.txt"
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
        stdout_path = raw_dir / f"{role.lower()}.attempt{attempt_index:02d}.stdout.log"
        latest_stdout_path = raw_dir / f"{role.lower()}.stdout.log"
        stderr_path = raw_dir / f"{role.lower()}.attempt{attempt_index:02d}.stderr.log"
        latest_stderr_path = raw_dir / f"{role.lower()}.stderr.log"
        start = monotonic()
        env = os.environ.copy()
        env.update(agent.env)
        try:
            proc = subprocess.run(
                command,
                cwd=self.app_cfg.workspace_root,
                capture_output=True,
                text=True,
                timeout=self.app_cfg.policies.model_timeout_seconds,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            stdout_text = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr_text = exc.stderr if isinstance(exc.stderr, str) else ""
            error_text = (
                f"Agent `{agent.agent_id}` timed out for role `{role}` after "
                f"{self.app_cfg.policies.model_timeout_seconds} seconds."
            )
            if error_text not in stderr_text:
                stderr_text = f"{stderr_text}\n{error_text}".strip()
            self._raise_execution_failure(
                cause=exc,
                command=command,
                started=started,
                start_time=start,
                round_dir=round_dir,
                round_id=round_id,
                role=role,
                agent=agent,
                attempt_index=attempt_index,
                stdout_path=stdout_path,
                latest_stdout_path=latest_stdout_path,
                stderr_path=stderr_path,
                latest_stderr_path=latest_stderr_path,
                stdout_text=stdout_text,
                stderr_text=stderr_text,
                error_text=error_text,
            )
        except OSError as exc:
            error_text = (
                f"Agent `{agent.agent_id}` failed to launch for role `{role}`: {exc}"
            )
            self._raise_execution_failure(
                cause=exc,
                command=command,
                started=started,
                start_time=start,
                round_dir=round_dir,
                round_id=round_id,
                role=role,
                agent=agent,
                attempt_index=attempt_index,
                stdout_path=stdout_path,
                latest_stdout_path=latest_stdout_path,
                stderr_path=stderr_path,
                latest_stderr_path=latest_stderr_path,
                stdout_text="",
                stderr_text=error_text,
                error_text=error_text,
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
        self._write_attempt_file(stdout_path, latest_stdout_path, proc.stdout)
        self._write_attempt_file(stderr_path, latest_stderr_path, proc.stderr)

        provider_trace = extract_provider_trace(
            agent.provider,
            proc.stdout,
            stderr=proc.stderr,
        )
        # Some CLIs expose the final assistant message outside stdout JSON, so
        # normalize that before schema extraction and transcript emission.
        fallback_output_text = self._select_output_text(agent, proc.stdout, last_message_path)
        if not provider_trace.final_text and fallback_output_text:
            provider_trace.final_text = fallback_output_text
        output_text = provider_trace.final_text or fallback_output_text
        self._write_attempt_file(last_message_path, latest_last_message_path, output_text)
        trace_path = trace_dir / f"{role.lower()}.attempt{attempt_index:02d}.provider_trace.json"
        latest_trace_path = trace_dir / f"{role.lower()}.provider_trace.json"
        write_json(trace_path, provider_trace)
        write_json(latest_trace_path, provider_trace)
        self._record_command_completion(
            finished=finished,
            round_dir=round_dir,
            round_id=round_id,
            role=role,
            agent=agent,
            attempt_index=attempt_index,
            result=result,
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
        return build_agent_command(
            app_cfg=self.app_cfg,
            agent=agent,
            role=role,
            prompt=prompt,
            schema_path=schema_path,
            round_dir=round_dir,
            last_message_path=last_message_path,
        )

    def _select_output_text(
        self,
        agent: AgentConfig,
        stdout: str,
        last_message_path: Path,
    ) -> str:
        return select_provider_output_text(agent, stdout, last_message_path)

    def _emit(self, event: dict) -> None:
        if self.event_handler is not None:
            self.event_handler(event)

    def _record_command_completion(
        self,
        *,
        finished: str,
        round_dir: Path,
        round_id: str,
        role: str,
        agent: AgentConfig,
        attempt_index: int,
        result: CommandResult,
        error: str = "",
    ) -> None:
        """Write the shared completion payload used by logs, UI, and live events."""
        command_payload = {
            "timestamp": finished,
            "kind": "model_command",
            "role": role,
            "agent_id": agent.agent_id,
            "provider": agent.provider,
            "command": result.command,
            "exit_code": result.exit_code,
            "duration_ms": result.duration_ms,
            "round_dir": str(round_dir),
            "attempt_index": attempt_index,
        }
        if error:
            command_payload["error"] = error
        append_jsonl(self.commands_log, command_payload)

        event_payload = {
            "timestamp": finished,
            "event": "model_command_completed",
            "round_id": round_id,
            "role": role,
            "agent_id": agent.agent_id,
            "provider": agent.provider,
            "model": agent.model,
            "exit_code": result.exit_code,
            "duration_ms": result.duration_ms,
            "attempt_index": attempt_index,
        }
        if error:
            event_payload["error"] = error
        append_jsonl(self.events_log, event_payload)
        self._emit(event_payload)

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

    def _raise_execution_failure(
        self,
        *,
        cause: BaseException,
        command: list[str],
        started: str,
        start_time: float,
        round_dir: Path,
        round_id: str,
        role: str,
        agent: AgentConfig,
        attempt_index: int,
        stdout_path: Path,
        latest_stdout_path: Path,
        stderr_path: Path,
        latest_stderr_path: Path,
        stdout_text: str,
        stderr_text: str,
        error_text: str,
    ) -> NoReturn:
        duration_ms = int((monotonic() - start_time) * 1000)
        finished = utc_now_iso()
        result = CommandResult(
            command=command,
            exit_code=-1,
            stdout=stdout_text,
            stderr=stderr_text,
            started_at=started,
            finished_at=finished,
            duration_ms=duration_ms,
        )
        self._write_attempt_file(stdout_path, latest_stdout_path, stdout_text)
        self._write_attempt_file(stderr_path, latest_stderr_path, stderr_text)
        self._record_command_completion(
            finished=finished,
            round_dir=round_dir,
            round_id=round_id,
            role=role,
            agent=agent,
            attempt_index=attempt_index,
            result=result,
            error=error_text,
        )
        raise RuntimeError(error_text) from cause
