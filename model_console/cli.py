from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import load_app_config
from .engine import LoopEngine


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mc", description="Model Console orchestration runner")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Start a new loop run")
    run_p.add_argument("--task", required=True, help="Task file path")
    run_p.add_argument("--loop", required=True, help="Loop id from config/loops.yaml")
    run_p.add_argument("--run-id", help="Optional explicit run id")
    run_p.add_argument("--workspace", default=".", help="Workspace root")
    run_p.add_argument("--config-dir", default="config", help="Config directory")
    run_p.add_argument("--schemas-dir", default="schemas", help="Schema directory")
    run_p.add_argument("--prompts-dir", default="prompts", help="Prompt template directory")
    run_p.add_argument("--runs-dir", default="runs", help="Runs directory")
    run_p.add_argument(
        "--live",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Show live progress events while the run is executing",
    )

    resume_p = sub.add_parser("resume", help="Resume an existing run")
    resume_p.add_argument("--run-id", required=True, help="Run id under runs/")
    resume_p.add_argument("--workspace", default=".", help="Workspace root")
    resume_p.add_argument("--config-dir", default="config", help="Config directory")
    resume_p.add_argument("--schemas-dir", default="schemas", help="Schema directory")
    resume_p.add_argument("--prompts-dir", default="prompts", help="Prompt template directory")
    resume_p.add_argument("--runs-dir", default="runs", help="Runs directory")
    resume_p.add_argument(
        "--live",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Show live progress events while resuming",
    )

    status_p = sub.add_parser("status", help="Show run status")
    status_p.add_argument("--run-id", required=True, help="Run id under runs/")
    status_p.add_argument("--workspace", default=".", help="Workspace root")
    status_p.add_argument("--runs-dir", default="runs", help="Runs directory")

    return parser


def cmd_run(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    app_cfg = load_app_config(
        workspace_root=workspace,
        config_dir=(workspace / args.config_dir).resolve(),
        schemas_dir=(workspace / args.schemas_dir).resolve(),
        prompts_dir=(workspace / args.prompts_dir).resolve(),
        run_root=(workspace / args.runs_dir).resolve(),
    )

    engine = LoopEngine(
        app_cfg=app_cfg,
        loop_id=args.loop,
        task_file=(workspace / args.task).resolve(),
        run_id=args.run_id,
        resume=False,
        event_handler=_event_printer(args.live),
    )
    report = engine.run()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    run_dir = (workspace / args.runs_dir / args.run_id).resolve()
    state_file = run_dir / "state.json"
    if not state_file.exists():
        raise FileNotFoundError(f"Run state not found: {state_file}")

    state = json.loads(state_file.read_text(encoding="utf-8"))
    loop_id = state["loop_id"]
    task_file = Path(state["task_file"]).resolve()

    app_cfg = load_app_config(
        workspace_root=workspace,
        config_dir=(workspace / args.config_dir).resolve(),
        schemas_dir=(workspace / args.schemas_dir).resolve(),
        prompts_dir=(workspace / args.prompts_dir).resolve(),
        run_root=(workspace / args.runs_dir).resolve(),
    )

    engine = LoopEngine(
        app_cfg=app_cfg,
        loop_id=loop_id,
        task_file=task_file,
        run_id=args.run_id,
        resume=True,
        event_handler=_event_printer(args.live),
    )
    report = engine.run()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    run_dir = (workspace / args.runs_dir / args.run_id).resolve()
    state_file = run_dir / "state.json"
    if not state_file.exists():
        runs_root = (workspace / args.runs_dir).resolve()
        available = _available_run_ids(runs_root)
        available_text = ", ".join(available) if available else "none"
        raise FileNotFoundError(
            "Run state not found: "
            f"{state_file}\nAvailable run IDs: {available_text}\n"
            "Start a run first, then check status with the same --run-id."
        )
    print(state_file.read_text(encoding="utf-8"))
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "run":
            return cmd_run(args)
        if args.command == "resume":
            return cmd_resume(args)
        if args.command == "status":
            return cmd_status(args)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    raise RuntimeError(f"Unsupported command {args.command}")


def _available_run_ids(runs_root: Path) -> list[str]:
    if not runs_root.exists():
        return []
    run_ids: list[str] = []
    for child in sorted(runs_root.iterdir()):
        if not child.is_dir():
            continue
        if (child / "state.json").exists():
            run_ids.append(child.name)
    return run_ids


def _event_printer(enabled: bool):
    if not enabled:
        return None

    def _print(event: dict[str, Any]) -> None:
        ts = _format_ts(str(event.get("timestamp", "")))
        kind = str(event.get("event", ""))
        if kind == "loop_started":
            print(
                f"[{ts}] LOOP start run={event.get('run_id')} loop={event.get('loop_id')}",
                flush=True,
            )
            return
        if kind == "roles_assigned":
            print(
                f"[{ts}] ROUND {event.get('round_id')} impl={event.get('implementers')} rev={event.get('reviewers')}",
                flush=True,
            )
            return
        if kind == "model_command_started":
            print(
                f"[{ts}] SEND {event.get('round_id')} role={event.get('role')} "
                f"agent={event.get('agent_id')} provider={event.get('provider')} model={event.get('model')}",
                flush=True,
            )
            return
        if kind == "model_command_completed":
            duration_ms = int(event.get("duration_ms", 0) or 0)
            duration_s = duration_ms / 1000.0
            print(
                f"[{ts}] DONE {event.get('round_id')} role={event.get('role')} "
                f"agent={event.get('agent_id')} exit={event.get('exit_code')} t={duration_s:.1f}s",
                flush=True,
            )
            return
        if kind == "round_failed":
            print(
                f"[{ts}] FAIL {event.get('round_id')} error={event.get('error')}",
                flush=True,
            )
            return
        if kind == "loop_completed":
            print(
                f"[{ts}] LOOP done run={event.get('run_id')} rounds={event.get('rounds_executed')} scores={event.get('scores')}",
                flush=True,
            )

    return _print


def _format_ts(timestamp: str) -> str:
    if not timestamp:
        return ""
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return dt.strftime("%H:%M:%S")
    except ValueError:
        return timestamp


if __name__ == "__main__":
    raise SystemExit(main())
