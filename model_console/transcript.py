from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .logging_utils import append_jsonl


@dataclass
class ProviderTrace:
    provider: str
    raw_format: str
    final_text: str
    assistant_messages: list[str] = field(default_factory=list)
    reasoning: list[str] = field(default_factory=list)
    thought_tokens: int | None = None
    stats: dict[str, Any] = field(default_factory=dict)


def extract_provider_trace(
    provider: str,
    stdout: str,
    *,
    stderr: str = "",
    final_text_override: str | None = None,
) -> ProviderTrace:
    provider_key = provider.lower().strip()
    if provider_key == "codex":
        return _extract_codex_trace(stdout, final_text_override)
    if provider_key == "gemini":
        return _extract_gemini_trace(stdout, final_text_override)
    if provider_key == "claude":
        return _extract_claude_trace(stdout, stderr, final_text_override)
    return _extract_plain_trace(provider_key, stdout, final_text_override)


def transcript_paths(run_transcript_log: Path | None, round_dir: Path) -> list[Path]:
    paths = [round_dir / "trace" / "conversation.jsonl"]
    if run_transcript_log is not None:
        paths.insert(0, run_transcript_log)
    return paths


def append_transcript_entry(
    run_transcript_log: Path | None,
    round_dir: Path,
    payload: dict[str, Any],
) -> None:
    for path in transcript_paths(run_transcript_log, round_dir):
        append_jsonl(path, payload)


def _extract_codex_trace(stdout: str, final_text_override: str | None) -> ProviderTrace:
    reasoning: list[str] = []
    assistant_messages: list[str] = []
    stats: dict[str, Any] = {}

    for event in _iter_json_events(stdout):
        event_type = str(event.get("type", ""))
        if event_type == "item.completed":
            item = event.get("item") or {}
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type", ""))
            text = _coerce_text(item.get("text"))
            if item_type == "reasoning" and text:
                reasoning.append(text)
            if item_type == "agent_message" and text:
                assistant_messages.append(text)
        elif event_type == "turn.completed":
            usage = event.get("usage")
            if isinstance(usage, dict):
                stats = usage

    final_text = final_text_override or (assistant_messages[-1] if assistant_messages else "")
    return ProviderTrace(
        provider="codex",
        raw_format="jsonl",
        final_text=final_text,
        assistant_messages=assistant_messages,
        reasoning=reasoning,
        stats=stats,
    )


def _extract_gemini_trace(stdout: str, final_text_override: str | None) -> ProviderTrace:
    events = _iter_json_events(stdout)
    if events and any("type" in event for event in events):
        return _extract_gemini_stream_trace(events, final_text_override)
    return _extract_gemini_json_trace(stdout, final_text_override)


def _extract_gemini_stream_trace(
    events: list[dict[str, Any]],
    final_text_override: str | None,
) -> ProviderTrace:
    delta_chunks: list[str] = []
    assistant_messages: list[str] = []
    stats: dict[str, Any] = {}

    for event in events:
        event_type = str(event.get("type", ""))
        if event_type == "message" and str(event.get("role", "")) == "assistant":
            content = _coerce_text(event.get("content"))
            if not content:
                continue
            if bool(event.get("delta", False)):
                delta_chunks.append(content)
            else:
                assistant_messages.append(content)
        elif event_type == "result":
            raw_stats = event.get("stats")
            if isinstance(raw_stats, dict):
                stats = raw_stats

    stream_text = assistant_messages[-1] if assistant_messages else "".join(delta_chunks)
    if stream_text and not assistant_messages:
        assistant_messages = [stream_text]

    return ProviderTrace(
        provider="gemini",
        raw_format="stream-json",
        final_text=final_text_override or stream_text,
        assistant_messages=assistant_messages,
        thought_tokens=_extract_gemini_thought_tokens(stats),
        stats=stats,
    )


def _extract_gemini_json_trace(stdout: str, final_text_override: str | None) -> ProviderTrace:
    payload = _parse_single_json_object(stdout)
    response = _coerce_text(payload.get("response")) if payload else ""
    stats = payload.get("stats") if isinstance(payload, dict) else {}
    if not isinstance(stats, dict):
        stats = {}

    assistant_messages = [response] if response else []
    return ProviderTrace(
        provider="gemini",
        raw_format="json",
        final_text=final_text_override or response,
        assistant_messages=assistant_messages,
        thought_tokens=_extract_gemini_thought_tokens(stats),
        stats=stats,
    )


def _extract_claude_trace(
    stdout: str,
    stderr: str,
    final_text_override: str | None,
) -> ProviderTrace:
    events = _iter_json_events(stdout)
    assistant_messages: list[str] = []
    stats: dict[str, Any] = {}

    for event in events:
        event_type = str(event.get("type", ""))
        if event_type == "assistant":
            message = event.get("message") or {}
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            text = _claude_message_text(content)
            if text:
                assistant_messages.append(text)
        elif event_type == "result":
            usage = event.get("usage")
            if isinstance(usage, dict):
                stats = usage

    final_text = final_text_override or (assistant_messages[-1] if assistant_messages else "")
    if not final_text and stdout.strip():
        final_text = stdout.strip()
    if not final_text and stderr.strip():
        final_text = stderr.strip()

    return ProviderTrace(
        provider="claude",
        raw_format="stream-json" if events else "text",
        final_text=final_text,
        assistant_messages=assistant_messages or ([final_text] if final_text else []),
        stats=stats,
    )


def _extract_plain_trace(
    provider: str,
    stdout: str,
    final_text_override: str | None,
) -> ProviderTrace:
    final_text = final_text_override or stdout.strip()
    assistant_messages = [final_text] if final_text else []
    return ProviderTrace(
        provider=provider,
        raw_format="text",
        final_text=final_text,
        assistant_messages=assistant_messages,
    )


def _extract_gemini_thought_tokens(stats: dict[str, Any]) -> int | None:
    if not stats:
        return None

    direct_total = stats.get("thoughts")
    if isinstance(direct_total, int):
        return direct_total

    models = stats.get("models")
    if isinstance(models, dict):
        for payload in models.values():
            if not isinstance(payload, dict):
                continue
            tokens = payload.get("tokens")
            if isinstance(tokens, dict) and isinstance(tokens.get("thoughts"), int):
                return int(tokens["thoughts"])
            roles = payload.get("roles")
            if isinstance(roles, dict):
                for role_payload in roles.values():
                    if not isinstance(role_payload, dict):
                        continue
                    role_tokens = role_payload.get("tokens")
                    if isinstance(role_tokens, dict) and isinstance(
                        role_tokens.get("thoughts"), int
                    ):
                        return int(role_tokens["thoughts"])
    return None


def _iter_json_events(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


def _parse_single_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _claude_message_text(content: Any) -> str:
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if str(item.get("type", "")) != "text":
            continue
        text = _coerce_text(item.get("text"))
        if text:
            parts.append(text)
    return "".join(parts)


def _coerce_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""
