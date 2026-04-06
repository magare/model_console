"""Render transcript JSONL logs into a standalone HTML viewer."""

from __future__ import annotations

import json
import webbrowser
from collections import Counter
from html import escape
from pathlib import Path
from typing import Any

from .logging import ensure_dir

_TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "templates" / "transcript_viewer.html"


def load_transcript_entries(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Transcript not found: {path}")

    entries: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"Could not read transcript: {path}") from exc

    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSONL in {path} at line {line_number}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"Transcript entry must be a JSON object: {path} line {line_number}")
        entries.append(payload)
    return entries


def default_viewer_output_path(transcript_path: Path) -> Path:
    if transcript_path.name == "transcript.jsonl" and transcript_path.parent.name == "logs":
        return transcript_path.parent.parent / "reports" / "transcript_viewer.html"
    return transcript_path.with_name(f"{transcript_path.stem}.viewer.html")


def write_transcript_viewer(
    transcript_path: Path,
    output_path: Path,
    *,
    open_browser: bool = False,
) -> dict[str, Any]:
    entries = load_transcript_entries(transcript_path)
    html = render_transcript_html(entries, transcript_path)
    ensure_dir(output_path.parent)
    output_path.write_text(html, encoding="utf-8")
    if open_browser:
        webbrowser.open(output_path.resolve().as_uri())
    return {
        "transcript_path": str(transcript_path),
        "output_path": str(output_path),
        "events": len(entries),
    }


def render_transcript_html(entries: list[dict[str, Any]], transcript_path: Path) -> str:
    summary = _build_summary(entries, transcript_path)
    payload = _script_safe_json({"summary": summary, "entries": entries})
    title = escape(_viewer_title(summary))
    source_label = escape(summary["source_label"])
    return _render_template_html(
        title=title,
        source_label=source_label,
        payload=payload,
    )


def _render_template_html(*, title: str, source_label: str, payload: str) -> str:
    template = _TEMPLATE_PATH.read_text(encoding="utf-8")
    return (
        "<!doctype html>\n"
        + template.replace("__VIEWER_TITLE__", title)
        .replace("__SOURCE_LABEL__", source_label)
        .replace("__VIEW_MODEL_JSON__", payload)
    )


def _build_summary(entries: list[dict[str, Any]], transcript_path: Path) -> dict[str, Any]:
    event_counts = Counter()
    rounds: set[str] = set()
    roles: set[str] = set()
    speakers: set[str] = set()
    run_ids: set[str] = set()
    loop_ids: set[str] = set()
    timestamps: list[str] = []

    for entry in entries:
        event_name = _string_value(entry.get("event"))
        if event_name:
            event_counts[event_name] += 1
        round_id = _string_value(entry.get("round_id"))
        if round_id:
            rounds.add(round_id)
        role = _string_value(entry.get("role"))
        if role:
            roles.add(role)
        speaker = _string_value(entry.get("speaker"))
        if speaker:
            speakers.add(speaker)
        run_id = _string_value(entry.get("run_id"))
        if run_id:
            run_ids.add(run_id)
        loop_id = _string_value(entry.get("loop_id"))
        if loop_id:
            loop_ids.add(loop_id)
        timestamp = _string_value(entry.get("timestamp"))
        if timestamp:
            timestamps.append(timestamp)

    return {
        "source_label": str(transcript_path),
        "total_events": len(entries),
        "event_counts": dict(sorted(event_counts.items())),
        "rounds": sorted(rounds),
        "roles": sorted(roles),
        "speakers": sorted(speakers),
        "run_ids": sorted(run_ids),
        "loop_ids": sorted(loop_ids),
        "started_at": timestamps[0] if timestamps else "",
        "finished_at": timestamps[-1] if timestamps else "",
    }


def _viewer_title(summary: dict[str, Any]) -> str:
    run_ids = summary.get("run_ids") or []
    loop_ids = summary.get("loop_ids") or []
    if run_ids and loop_ids:
        return f"{run_ids[0]} / {loop_ids[0]}"
    if run_ids:
        return str(run_ids[0])
    if loop_ids:
        return str(loop_ids[0])
    return "Transcript Atlas"


def _script_safe_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")


def _string_value(value: Any) -> str:
    return str(value) if isinstance(value, str) and value else ""
