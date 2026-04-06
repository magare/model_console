from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from model_console.engine import LoopEngine, _default_rubric
from model_console.executors import AgentExecutor
from model_console.validator import validate_with_schema
from model_console.models import (
    AgentConfig,
    AppConfig,
    LoopConfig,
    Policies,
    RoleAssignmentConfig,
)
from model_console.prompts import render_template
from model_console.transcript import extract_provider_trace


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
SCHEMAS_DIR = REPO_ROOT / "schemas"
PROMPTS_DIR = REPO_ROOT / "prompts"


def _test_app_config(workspace_root: Path, run_root: Path) -> AppConfig:
    agents = {
        "mock_impl": AgentConfig(
            agent_id="mock_impl",
            provider="mock",
            model="mock-implementer",
            cli_path="python3",
            env={"PYTHONPATH": str(SRC_ROOT)},
        ),
        "mock_rev": AgentConfig(
            agent_id="mock_rev",
            provider="mock",
            model="mock-reviewer",
            cli_path="python3",
            env={"PYTHONPATH": str(SRC_ROOT)},
        ),
    }
    loops = {
        "bootstrap_loop": LoopConfig(
            loop_id="bootstrap_loop",
            artifact_kind="plan",
            max_rounds=2,
            score_threshold=80.0,
            stagnation_rounds=1,
            stagnation_epsilon=0.1,
            swap_next_round=False,
            swap_on_failure=True,
            role_assignment=RoleAssignmentConfig(
                strategy="static",
                implementers=["mock_impl"],
                reviewers=["mock_rev"],
                implementer_count=1,
                reviewer_count=1,
            ),
            eval_commands=["echo 'bootstrap eval ok'"],
        )
    }
    policies = Policies(
        allow_command_prefixes=["python3", "echo"],
        deny_command_patterns=[],
        model_timeout_seconds=30,
        run_timeout_seconds=30,
        max_completed_runs=None,
    )
    return AppConfig(
        workspace_root=workspace_root,
        run_root=run_root,
        agents=agents,
        loops=loops,
        policies=policies,
        schemas_dir=SCHEMAS_DIR,
        prompts_dir=PROMPTS_DIR,
    )


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


class ProviderTraceTests(unittest.TestCase):
    def test_extract_codex_trace_captures_reasoning(self) -> None:
        stdout = "\n".join(
            [
                "2026-03-20T17:24:46.696879Z WARN ignored preamble",
                '{"type":"thread.started","thread_id":"t1"}',
                '{"type":"turn.started"}',
                '{"type":"item.completed","item":{"id":"item_0","type":"reasoning","text":"**Crafting deterministic test plan JSON**"}}',
                '{"type":"item.completed","item":{"id":"item_1","type":"agent_message","text":"{\\"ok\\":true}"}}',
                '{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":5}}',
            ]
        )

        trace = extract_provider_trace("codex", stdout)

        self.assertEqual(trace.provider, "codex")
        self.assertEqual(trace.final_text, '{"ok":true}')
        self.assertEqual(trace.reasoning, ["**Crafting deterministic test plan JSON**"])
        self.assertEqual(trace.assistant_messages, ['{"ok":true}'])
        self.assertEqual(trace.stats["output_tokens"], 5)

    def test_extract_gemini_trace_captures_thought_tokens(self) -> None:
        stdout = json.dumps(
            {
                "response": '{"ok":true}',
                "stats": {
                    "models": {
                        "gemini-2.5-flash-lite": {
                            "tokens": {"thoughts": 3726},
                            "roles": {
                                "main": {
                                    "tokens": {"thoughts": 3726},
                                }
                            },
                        }
                    }
                },
            }
        )

        trace = extract_provider_trace("gemini", stdout)

        self.assertEqual(trace.provider, "gemini")
        self.assertEqual(trace.final_text, '{"ok":true}')
        self.assertEqual(trace.thought_tokens, 3726)

    def test_extract_gemini_stream_trace_captures_assistant_message(self) -> None:
        stdout = "\n".join(
            [
                "Loaded cached credentials.",
                '{"type":"init","timestamp":"2026-03-20T17:25:12.761Z","session_id":"s1","model":"gemini-2.5-flash-lite"}',
                '{"type":"message","timestamp":"2026-03-20T17:25:12.762Z","role":"user","content":"Reply with exactly: {\\"ok\\":true}"}',
                '{"type":"message","timestamp":"2026-03-20T17:25:13.980Z","role":"assistant","content":"{\\"ok\\":true}","delta":true}',
                '{"type":"result","timestamp":"2026-03-20T17:25:13.993Z","status":"success","stats":{"total_tokens":6400}}',
            ]
        )

        trace = extract_provider_trace("gemini", stdout)

        self.assertEqual(trace.raw_format, "stream-json")
        self.assertEqual(trace.final_text, '{"ok":true}')
        self.assertEqual(trace.assistant_messages, ['{"ok":true}'])

    def test_extract_claude_json_result_trace_uses_inner_result(self) -> None:
        stdout = json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "result": '```json\n{"ok":true}\n```',
                "usage": {"input_tokens": 10, "output_tokens": 5},
            }
        )

        trace = extract_provider_trace("claude", stdout)

        self.assertEqual(trace.raw_format, "json")
        self.assertEqual(trace.final_text, '```json\n{"ok":true}\n```')
        self.assertEqual(trace.assistant_messages, ['```json\n{"ok":true}\n```'])
        self.assertEqual(trace.stats["output_tokens"], 5)

    def test_extract_copilot_trace_captures_reasoning_and_usage(self) -> None:
        stdout = "\n".join(
            [
                '{"type":"assistant.reasoning","data":{"reasoningId":"r1","content":"Plan the JSON response."}}',
                '{"type":"assistant.message","data":{"messageId":"m1","content":"{\\"ok\\":true}"}}',
                '{"type":"assistant.usage","data":{"model":"claude-sonnet-4.5","inputTokens":10,"outputTokens":5}}',
            ]
        )

        trace = extract_provider_trace("copilot", stdout)

        self.assertEqual(trace.provider, "copilot")
        self.assertEqual(trace.raw_format, "jsonl")
        self.assertEqual(trace.final_text, '{"ok":true}')
        self.assertEqual(trace.reasoning, ["Plan the JSON response."])
        self.assertEqual(trace.assistant_messages, ['{"ok":true}'])
        self.assertEqual(trace.stats["outputTokens"], 5)

    def test_extract_copilot_trace_falls_back_to_stream_deltas(self) -> None:
        stdout = "\n".join(
            [
                '{"type":"assistant.reasoning_delta","data":{"reasoningId":"r1","deltaContent":"Think "}}',
                '{"type":"assistant.reasoning_delta","data":{"reasoningId":"r1","deltaContent":"carefully."}}',
                '{"type":"assistant.message_delta","data":{"messageId":"m1","deltaContent":"{\\"ok\\""}}',
                '{"type":"assistant.message_delta","data":{"messageId":"m1","deltaContent":":true}"}}',
            ]
        )

        trace = extract_provider_trace("copilot", stdout)

        self.assertEqual(trace.final_text, '{"ok":true}')
        self.assertEqual(trace.assistant_messages, ['{"ok":true}'])
        self.assertEqual(trace.reasoning, ["Think carefully."])


class TranscriptIntegrationTests(unittest.TestCase):
    def test_executor_preserves_attempt_specific_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run_root = workspace / "runs"
            app_cfg = _test_app_config(workspace, run_root)
            executor = AgentExecutor(
                app_cfg=app_cfg,
                events_log=run_root / "events.jsonl",
                commands_log=run_root / "commands.jsonl",
                transcript_log=run_root / "transcript.jsonl",
            )
            round_dir = workspace / "r01"
            round_dir.mkdir(parents=True, exist_ok=True)
            agent = app_cfg.agents["mock_impl"]
            prompt = "Return a valid implementer payload."

            executor.run_role(
                agent=agent,
                run_id="attempt-test",
                loop_id="bootstrap_loop",
                role="IMPLEMENTER",
                prompt=prompt,
                schema_path=SCHEMAS_DIR / "implementer.output.schema.json",
                round_dir=round_dir,
                attempt_index=1,
            )
            executor.run_role(
                agent=agent,
                run_id="attempt-test",
                loop_id="bootstrap_loop",
                role="IMPLEMENTER",
                prompt=prompt + " Retry.",
                schema_path=SCHEMAS_DIR / "implementer.output.schema.json",
                round_dir=round_dir,
                attempt_index=2,
            )

            self.assertTrue((round_dir / "prompts" / "implementer.attempt01.prompt.txt").exists())
            self.assertTrue((round_dir / "prompts" / "implementer.attempt02.prompt.txt").exists())
            self.assertTrue((round_dir / "raw" / "implementer.attempt01.last_message.txt").exists())
            self.assertTrue((round_dir / "raw" / "implementer.attempt02.last_message.txt").exists())
            self.assertTrue((round_dir / "raw" / "implementer.attempt01.stdout.log").exists())
            self.assertTrue((round_dir / "raw" / "implementer.attempt02.stdout.log").exists())
            self.assertTrue((round_dir / "trace" / "implementer.attempt01.provider_trace.json").exists())
            self.assertTrue((round_dir / "trace" / "implementer.attempt02.provider_trace.json").exists())
            latest_prompt = (round_dir / "prompts" / "implementer.prompt.txt").read_text(
                encoding="utf-8"
            )
            latest_last_message = (round_dir / "raw" / "implementer.last_message.txt").read_text(
                encoding="utf-8"
            )
            attempt_two_last_message = (
                round_dir / "raw" / "implementer.attempt02.last_message.txt"
            ).read_text(encoding="utf-8")
            self.assertEqual(latest_prompt, prompt + " Retry.")
            self.assertEqual(latest_last_message, attempt_two_last_message)

    def test_loop_run_writes_cross_model_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run_root = workspace / "runs"
            task_file = workspace / "tasks" / "bootstrap.md"
            task_file.parent.mkdir(parents=True, exist_ok=True)
            task_file.write_text(
                "Create a short implementation-ready plan for testing the model-console orchestration.\n",
                encoding="utf-8",
            )
            app_cfg = _test_app_config(workspace, run_root)
            engine = LoopEngine(
                app_cfg=app_cfg,
                loop_id="bootstrap_loop",
                task_file=task_file,
                run_id="trace-smoke",
            )

            report = engine.run()

            self.assertEqual(report["run_id"], "trace-smoke")
            transcript_path = run_root / "trace-smoke" / "logs" / "transcript.jsonl"
            round_trace_path = (
                run_root
                / "trace-smoke"
                / "loop_bootstrap_loop"
                / "rounds"
                / "r01"
                / "trace"
                / "conversation.jsonl"
            )
            self.assertTrue(transcript_path.exists())
            self.assertTrue(round_trace_path.exists())

            events = _read_jsonl(transcript_path)
            event_types = {event["event"] for event in events}
            self.assertIn("prompt_sent", event_types)
            self.assertIn("model_response", event_types)
            self.assertIn("artifact_handoff", event_types)

            prompt_recipients = [event["recipient"] for event in events if event["event"] == "prompt_sent"]
            self.assertIn("mock_impl", prompt_recipients)
            self.assertIn("mock_rev", prompt_recipients)

            provider_trace = (
                run_root
                / "trace-smoke"
                / "loop_bootstrap_loop"
                / "rounds"
                / "r01"
                / "trace"
                / "implementer.provider_trace.json"
            )
            self.assertTrue(provider_trace.exists())


class PromptAndExecutorContractTests(unittest.TestCase):
    def test_implementer_prompt_uses_loop_artifact_kind(self) -> None:
        template = (PROMPTS_DIR / "implementer.template.txt").read_text(encoding="utf-8")

        prompt = render_template(
            template,
            {
                "loop_id": "kanban_loop",
                "round_id": "r01",
                "artifact_id": "kanban-001-task",
                "objective": "Generate kanban board",
                "artifact_snapshot": "[no artifact yet]",
                "prioritized_fixes": "[]",
                "task_mode": "simple",
                "workflow_context": "[workflow mode disabled]",
                "selected_step_id": "",
                "schema_path": "/tmp/schema.json",
                "artifact_kind": "kanban",
            },
        )

        self.assertIn('"kind": "kanban"', prompt)
        self.assertNotIn('"kind": "spec"', prompt)

    def test_claude_command_embeds_schema_json_instead_of_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run_root = workspace / "runs"
            app_cfg = _test_app_config(workspace, run_root)
            executor = AgentExecutor(
                app_cfg=app_cfg,
                events_log=run_root / "events.jsonl",
                commands_log=run_root / "commands.jsonl",
                transcript_log=run_root / "transcript.jsonl",
            )
            round_dir = workspace / "r01"
            round_dir.mkdir(parents=True, exist_ok=True)

            schema_path = workspace / "schema.json"
            schema_path.write_text(
                '{"type":"object","required":["ok"],"properties":{"ok":{"type":"boolean"}}}',
                encoding="utf-8",
            )

            agent = AgentConfig(
                agent_id="claude_primary",
                provider="claude",
                model="claude-sonnet-4",
                cli_path="claude",
                env={},
            )

            command = executor._build_command(  # noqa: SLF001 - testing contract
                agent=agent,
                role="IMPLEMENTER",
                prompt="Return JSON",
                schema_path=schema_path,
                round_dir=round_dir,
                last_message_path=round_dir / "last_message.txt",
            )

            schema_flag_index = command.index("--json-schema") + 1
            self.assertEqual(
                command[schema_flag_index],
                schema_path.read_text(encoding="utf-8"),
            )
            self.assertNotEqual(command[schema_flag_index], str(schema_path))

    def test_copilot_command_uses_non_interactive_json_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run_root = workspace / "runs"
            app_cfg = _test_app_config(workspace, run_root)
            executor = AgentExecutor(
                app_cfg=app_cfg,
                events_log=run_root / "events.jsonl",
                commands_log=run_root / "commands.jsonl",
                transcript_log=run_root / "transcript.jsonl",
            )
            round_dir = workspace / "r01"
            round_dir.mkdir(parents=True, exist_ok=True)

            agent = AgentConfig(
                agent_id="copilot_primary",
                provider="copilot",
                model="claude-sonnet-4.5",
                cli_path="copilot",
                env={},
            )

            command = executor._build_command(  # noqa: SLF001 - testing contract
                agent=agent,
                role="IMPLEMENTER",
                prompt="Return JSON",
                schema_path=SCHEMAS_DIR / "implementer.output.schema.json",
                round_dir=round_dir,
                last_message_path=round_dir / "last_message.txt",
            )

            self.assertEqual(command[:3], ["copilot", "-p", "Return JSON"])
            self.assertIn("--output-format", command)
            self.assertIn("json", command)
            self.assertIn("--allow-all-tools", command)
            self.assertIn("--no-ask-user", command)
            self.assertIn("--stream", command)
            self.assertIn("off", command)
            self.assertIn("--add-dir", command)
            self.assertIn(str(workspace), command)

    def test_copilot_command_omits_model_flag_when_agent_model_is_blank(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            run_root = workspace / "runs"
            app_cfg = _test_app_config(workspace, run_root)
            executor = AgentExecutor(
                app_cfg=app_cfg,
                events_log=run_root / "events.jsonl",
                commands_log=run_root / "commands.jsonl",
                transcript_log=run_root / "transcript.jsonl",
            )
            round_dir = workspace / "r01"
            round_dir.mkdir(parents=True, exist_ok=True)

            agent = AgentConfig(
                agent_id="copilot_primary",
                provider="copilot",
                model="",
                cli_path="copilot",
                env={},
            )

            command = executor._build_command(  # noqa: SLF001 - testing contract
                agent=agent,
                role="IMPLEMENTER",
                prompt="Return JSON",
                schema_path=SCHEMAS_DIR / "implementer.output.schema.json",
                round_dir=round_dir,
                last_message_path=round_dir / "last_message.txt",
            )

            self.assertNotIn("--model", command)

    def test_implementer_schema_accepts_kanban_artifact_kind(self) -> None:
        payload = {
            "meta": {
                "model_id": "claude-sonnet-4",
                "role": "IMPLEMENTER",
                "loop_id": "product_kanban_loop",
                "round_id": "r01",
                "artifact_id": "kanban-001-task",
                "timestamp": "2026-03-25T00:00:00Z",
                "tool_version": "model_console",
            },
            "status": "ok",
            "artifact": {
                "kind": "kanban",
                "path": "kanban/001-reportpilot.md",
                "content": "# Board",
            },
            "change_summary": ["Generated kanban board"],
            "risk_notes": [],
            "todos": [],
            "progress": {
                "phase": "execute",
                "selected_step_id": "",
                "completed_step_ids": [],
                "pending_step_ids": [],
                "blocked_step_ids": [],
            },
            "unsure": [],
        }

        errors = validate_with_schema(SCHEMAS_DIR / "implementer.output.schema.json", payload)

        self.assertEqual(errors, [])


class RubricSelectionTests(unittest.TestCase):
    def test_prompt_loop_uses_prompt_specific_rubric(self) -> None:
        self.assertEqual(
            _default_rubric("prompt_loop"),
            "Completeness(30), Sequencing(25), Risks(25), Verifiability(20).",
        )


if __name__ == "__main__":
    unittest.main()
