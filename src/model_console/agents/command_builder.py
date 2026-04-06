"""Provider-specific model command and output helpers."""

from __future__ import annotations

import json
from pathlib import Path

from ..models import AgentConfig, AppConfig
from ..runtime import resolve_mock_python_command


def build_agent_command(
    *,
    app_cfg: AppConfig,
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
    workspace = str(app_cfg.workspace_root)

    if provider == "claude":
        schema_json = schema_path.read_text(encoding="utf-8")
        command = [
            cli,
            "-p",
            prompt,
            "--output-format",
            "json",
            "--json-schema",
            schema_json,
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
    elif provider == "copilot":
        command = [
            cli,
            "-p",
            prompt,
            "--output-format",
            "json",
        ]
        if model:
            command.extend(["--model", model])
        command.extend(
            [
                "--allow-all-tools",
                "--no-ask-user",
                "--add-dir",
                workspace,
                "--stream",
                "off",
                "--no-auto-update",
                "--no-color",
            ]
        )
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
            resolve_mock_python_command(agent.cli_path or cli),
            "-m",
            "model_console.agents.mock",
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


def select_provider_output_text(
    agent: AgentConfig,
    stdout: str,
    last_message_path: Path,
) -> str:
    provider = agent.provider.lower()
    if provider == "codex" and last_message_path.exists():
        return last_message_path.read_text(encoding="utf-8")
    if provider == "claude":
        payload = _load_json_object(stdout, must_start_with_brace=True)
        if payload is not None:
            result = payload.get("result")
            if isinstance(result, str):
                return result
    if provider == "gemini":
        payload = _load_json_object(stdout)
        if payload is not None:
            response = payload.get("response")
            if isinstance(response, str):
                return response
    return stdout


def _load_json_object(text: str, *, must_start_with_brace: bool = False) -> dict[str, object] | None:
    if must_start_with_brace and not text.strip().startswith("{"):
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None
