from __future__ import annotations

import argparse
import json
import shutil
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
    task_file = _resolve_within_workspace(workspace, args.task, "--task")
    config_dir = _resolve_within_workspace(workspace, args.config_dir, "--config-dir")
    schemas_dir = _resolve_within_workspace(workspace, args.schemas_dir, "--schemas-dir")
    prompts_dir = _resolve_within_workspace(workspace, args.prompts_dir, "--prompts-dir")
    runs_dir = _resolve_within_workspace(workspace, args.runs_dir, "--runs-dir")
    app_cfg = load_app_config(
        workspace_root=workspace,
        config_dir=config_dir,
        schemas_dir=schemas_dir,
        prompts_dir=prompts_dir,
        run_root=runs_dir,
    )

    engine = LoopEngine(
        app_cfg=app_cfg,
        loop_id=args.loop,
        task_file=task_file,
        run_id=args.run_id,
        resume=False,
        event_handler=_event_printer(args.live),
    )
    report = engine.run()
    prune_summary = _prune_completed_runs(
        runs_dir,
        max_completed_runs=app_cfg.policies.max_completed_runs,
        protected_run_ids={str(report.get("run_id", ""))},
    )
    _print_prune_summary(prune_summary)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    runs_dir = _resolve_within_workspace(workspace, args.runs_dir, "--runs-dir")
    run_dir = _resolve_run_dir(runs_dir, args.run_id)
    state_file = run_dir / "state.json"
    if not state_file.exists():
        raise FileNotFoundError(f"Run state not found: {state_file}")

    state = json.loads(state_file.read_text(encoding="utf-8"))
    loop_id = state["loop_id"]
    task_file = _resolve_within_workspace(workspace, state["task_file"], "state.task_file")
    config_dir = _resolve_within_workspace(workspace, args.config_dir, "--config-dir")
    schemas_dir = _resolve_within_workspace(workspace, args.schemas_dir, "--schemas-dir")
    prompts_dir = _resolve_within_workspace(workspace, args.prompts_dir, "--prompts-dir")

    app_cfg = load_app_config(
        workspace_root=workspace,
        config_dir=config_dir,
        schemas_dir=schemas_dir,
        prompts_dir=prompts_dir,
        run_root=runs_dir,
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
    prune_summary = _prune_completed_runs(
        runs_dir,
        max_completed_runs=app_cfg.policies.max_completed_runs,
        protected_run_ids={args.run_id},
    )
    _print_prune_summary(prune_summary)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    runs_dir = _resolve_within_workspace(workspace, args.runs_dir, "--runs-dir")
    run_dir = _resolve_run_dir(runs_dir, args.run_id)
    state_file = run_dir / "state.json"
    if not state_file.exists():
        available = _available_run_ids(runs_dir)
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


def _resolve_within_workspace(workspace: Path, raw_path: str, arg_name: str) -> Path:
    user_path = Path(raw_path).expanduser()
    resolved = (
        user_path.resolve() if user_path.is_absolute() else (workspace / user_path).resolve()
    )
    if resolved != workspace and workspace not in resolved.parents:
        raise ValueError(
            f"{arg_name} must stay inside workspace `{workspace}`; got `{resolved}`"
        )
    return resolved


def _resolve_run_dir(runs_dir: Path, run_id: str) -> Path:
    run_dir = (runs_dir / run_id).resolve()
    if run_dir != runs_dir and runs_dir not in run_dir.parents:
        raise ValueError(f"--run-id resolves outside --runs-dir: {run_id}")
    return run_dir


def _prune_completed_runs(
    runs_root: Path,
    max_completed_runs: int | None,
    protected_run_ids: set[str] | None = None,
) -> dict[str, Any]:
    if max_completed_runs is None:
        return {"enabled": False, "deleted_run_ids": [], "bytes_reclaimed": 0, "errors": []}
    if max_completed_runs < 0:
        raise ValueError("policies.max_completed_runs must be >= 0")
    if not runs_root.exists():
        return {
            "enabled": True,
            "limit": max_completed_runs,
            "deleted_run_ids": [],
            "bytes_reclaimed": 0,
            "errors": [],
        }

    protected = {rid for rid in (protected_run_ids or set()) if rid}
    candidates: list[tuple[float, Path]] = []
    for child in runs_root.iterdir():
        if not child.is_dir() or child.name in protected:
            continue
        state_file = child / "state.json"
        if not state_file.exists():
            continue
        state = _read_state_safely(state_file)
        if not state.get("terminated", False):
            continue
        candidates.append((_run_sort_key(child, state), child))

    # Newest first; prune only oldest entries beyond the configured cap.
    candidates.sort(key=lambda item: item[0], reverse=True)
    to_remove = candidates[max_completed_runs:]

    deleted_run_ids: list[str] = []
    errors: list[str] = []
    bytes_reclaimed = 0
    for _, run_dir in to_remove:
        try:
            bytes_reclaimed += _dir_size_bytes(run_dir)
            shutil.rmtree(run_dir)
            deleted_run_ids.append(run_dir.name)
        except OSError as exc:
            errors.append(f"{run_dir.name}: {exc}")

    return {
        "enabled": True,
        "limit": max_completed_runs,
        "deleted_run_ids": deleted_run_ids,
        "bytes_reclaimed": bytes_reclaimed,
        "errors": errors,
    }


def _print_prune_summary(summary: dict[str, Any]) -> None:
    if not summary.get("enabled", False):
        return
    deleted = summary.get("deleted_run_ids") or []
    reclaimed = int(summary.get("bytes_reclaimed", 0) or 0)
    errors = summary.get("errors") or []
    if not deleted and not errors:
        return

    reclaimed_mb = reclaimed / (1024 * 1024)
    print(
        f"RETENTION deleted={len(deleted)} reclaimed_mb={reclaimed_mb:.2f} "
        f"limit={summary.get('limit')} errors={len(errors)}",
        file=sys.stderr,
    )
    if deleted:
        print(f"RETENTION removed run_ids={','.join(deleted)}", file=sys.stderr)
    for err in errors:
        print(f"RETENTION error {err}", file=sys.stderr)


def _read_state_safely(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _run_sort_key(run_dir: Path, state: dict[str, Any]) -> float:
    started_at = state.get("started_at")
    if isinstance(started_at, str) and started_at:
        try:
            return datetime.fromisoformat(started_at.replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
    try:
        return run_dir.stat().st_mtime
    except OSError:
        return 0.0


def _dir_size_bytes(path: Path) -> int:
    total = 0
    for candidate in path.rglob("*"):
        try:
            if candidate.is_file():
                total += candidate.stat().st_size
        except OSError:
            continue
    return total


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
