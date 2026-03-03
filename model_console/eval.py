from __future__ import annotations

import subprocess
from pathlib import Path
from time import monotonic

from .logging_utils import append_jsonl, utc_now_iso
from .models import AppConfig, CommandResult, EvalResult
from .safety import assert_command_safe


def run_eval_commands(
    app_cfg: AppConfig,
    commands: list[str],
    events_log: Path,
    commands_log: Path,
) -> EvalResult:
    results: list[dict] = []
    all_passed = True

    for command_text in commands:
        command = ["zsh", "-lc", command_text]
        assert_command_safe(command, app_cfg.policies)

        started = utc_now_iso()
        start = monotonic()
        proc = subprocess.run(
            command,
            cwd=app_cfg.workspace_root,
            capture_output=True,
            text=True,
            timeout=app_cfg.policies.run_timeout_seconds,
        )
        duration_ms = int((monotonic() - start) * 1000)
        finished = utc_now_iso()

        cmd_result = CommandResult(
            command=command,
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            started_at=started,
            finished_at=finished,
            duration_ms=duration_ms,
        )
        payload = {
            "kind": "eval_command",
            "command_text": command_text,
            "result": {
                "command": cmd_result.command,
                "exit_code": cmd_result.exit_code,
                "duration_ms": cmd_result.duration_ms,
                "stdout": cmd_result.stdout,
                "stderr": cmd_result.stderr,
            },
        }

        append_jsonl(commands_log, {"timestamp": finished, **payload})
        append_jsonl(
            events_log,
            {
                "timestamp": finished,
                "event": "eval_command_completed",
                "command_text": command_text,
                "exit_code": proc.returncode,
                "duration_ms": duration_ms,
            },
        )

        results.append(payload)
        if proc.returncode != 0:
            all_passed = False

    return EvalResult(passed=all_passed, commands=results)
