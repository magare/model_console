from __future__ import annotations

import argparse
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from model_console.cli import cmd_transcript
from model_console.transcript_viewer import (
    default_viewer_output_path,
    load_transcript_entries,
    render_transcript_html,
)


class TranscriptViewerTests(unittest.TestCase):
    def test_default_viewer_output_path_prefers_run_report_location(self) -> None:
        transcript_path = (
            Path("/tmp")
            / "runs"
            / "demo-run"
            / "logs"
            / "transcript.jsonl"
        )

        output_path = default_viewer_output_path(transcript_path)

        self.assertEqual(
            output_path,
            Path("/tmp") / "runs" / "demo-run" / "reports" / "transcript_viewer.html",
        )

    def test_render_transcript_html_contains_controls_and_events(self) -> None:
        transcript_path = Path("/tmp/demo/transcript.jsonl")
        entries = [
            {
                "timestamp": "2026-03-20T18:08:53.716963+00:00",
                "event": "prompt_sent",
                "run_id": "demo-run",
                "loop_id": "bootstrap_loop",
                "round_id": "r01",
                "speaker": "orchestrator",
                "recipient": "mock_impl",
                "role": "IMPLEMENTER",
                "text": "Create a plan.",
            },
            {
                "timestamp": "2026-03-20T18:08:53.793008+00:00",
                "event": "model_response",
                "run_id": "demo-run",
                "loop_id": "bootstrap_loop",
                "round_id": "r01",
                "speaker": "mock_impl",
                "recipient": "orchestrator",
                "role": "IMPLEMENTER",
                "text": '{"ok": true}',
            },
        ]

        html = render_transcript_html(entries, transcript_path)

        self.assertIn("Transcript Viewer", html)
        self.assertIn("prompt_sent", html)
        self.assertIn("model_response", html)
        self.assertIn("Search", html)
        self.assertIn(str(transcript_path), html)

    def test_cmd_transcript_writes_html_for_run_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            transcript_path = workspace / "runs" / "demo-run" / "logs" / "transcript.jsonl"
            transcript_path.parent.mkdir(parents=True, exist_ok=True)
            transcript_path.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "timestamp": "2026-03-20T18:08:53.716963+00:00",
                                "event": "prompt_sent",
                                "run_id": "demo-run",
                                "loop_id": "bootstrap_loop",
                                "round_id": "r01",
                                "speaker": "orchestrator",
                                "recipient": "mock_impl",
                                "role": "IMPLEMENTER",
                                "text": "Create a plan.",
                            }
                        ),
                        json.dumps(
                            {
                                "timestamp": "2026-03-20T18:08:53.793008+00:00",
                                "event": "model_response",
                                "run_id": "demo-run",
                                "loop_id": "bootstrap_loop",
                                "round_id": "r01",
                                "speaker": "mock_impl",
                                "recipient": "orchestrator",
                                "role": "IMPLEMENTER",
                                "text": '{"ok": true}',
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            args = argparse.Namespace(
                run_id="demo-run",
                transcript=None,
                workspace=str(workspace),
                runs_dir="runs",
                output=None,
                open=False,
            )

            with redirect_stdout(io.StringIO()):
                exit_code = cmd_transcript(args)

            output_path = workspace / "runs" / "demo-run" / "reports" / "transcript_viewer.html"
            self.assertEqual(exit_code, 0)
            self.assertTrue(output_path.exists())
            html = output_path.read_text(encoding="utf-8")
            self.assertIn("demo-run / bootstrap_loop", html)
            self.assertIn("Create a plan.", html)

    def test_load_transcript_entries_rejects_non_utf8_input_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            transcript_path = Path(tmp) / "broken.jsonl"
            transcript_path.write_bytes(b"\xff\xfe\x00")

            with self.assertRaisesRegex(ValueError, "Could not read transcript"):
                load_transcript_entries(transcript_path)


if __name__ == "__main__":
    unittest.main()
