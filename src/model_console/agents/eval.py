"""Eval-command runner.

Executes user-defined shell commands (e.g. linters, tests) after each round
and reports a combined pass/fail result back to the engine.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from time import monotonic

from ..observability.logging import append_jsonl, utc_now_iso
from ..models import AppConfig, CommandResult, EvalResult
from ..runtime import build_shell_command
from ..safety import assert_command_safe


def run_eval_commands(
    app_cfg: AppConfig,
    commands: list[str],
    events_log: Path,
    commands_log: Path,
) -> EvalResult:
    results: list[dict] = []
    all_passed = True

    for command_text in commands:
        command = build_shell_command(command_text)
        assert_command_safe(command, app_cfg.policies)

        started = utc_now_iso()
        start = monotonic()
        error_type = ""
        error_message = ""
        try:
            proc = subprocess.run(
                command,
                cwd=app_cfg.workspace_root,
                capture_output=True,
                text=True,
                timeout=app_cfg.policies.run_timeout_seconds,
            )
            exit_code = proc.returncode
            stdout = proc.stdout
            stderr = proc.stderr
        except subprocess.TimeoutExpired as exc:
            exit_code = -1
            stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr = exc.stderr if isinstance(exc.stderr, str) else ""
            error_type = "timeout"
            error_message = (
                f"Eval command timed out after {app_cfg.policies.run_timeout_seconds} seconds."
            )
            if error_message not in stderr:
                stderr = f"{stderr}\n{error_message}".strip()
        except OSError as exc:
            exit_code = -1
            stdout = ""
            stderr = str(exc)
            error_type = "launch_error"
            error_message = f"Eval command failed to launch: {exc}"
            if error_message not in stderr:
                stderr = f"{stderr}\n{error_message}".strip()
        duration_ms = int((monotonic() - start) * 1000)
        finished = utc_now_iso()

        cmd_result = CommandResult(
            command=command,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            started_at=started,
            finished_at=finished,
            duration_ms=duration_ms,
        )
        result_payload = {
            "command": cmd_result.command,
            "exit_code": cmd_result.exit_code,
            "duration_ms": cmd_result.duration_ms,
            "stdout": cmd_result.stdout,
            "stderr": cmd_result.stderr,
        }
        if error_type:
            result_payload["error_type"] = error_type
            result_payload["error_message"] = error_message

        payload = {
            "kind": "eval_command",
            "command_text": command_text,
            "result": result_payload,
        }

        append_jsonl(commands_log, {"timestamp": finished, **payload})
        append_jsonl(
            events_log,
            {
                "timestamp": finished,
                "event": "eval_command_completed",
                "command_text": command_text,
                "exit_code": exit_code,
                "duration_ms": duration_ms,
                "error_type": error_type,
            },
        )

        results.append(payload)
        if exit_code != 0:
            all_passed = False

    return EvalResult(passed=all_passed, commands=results)
