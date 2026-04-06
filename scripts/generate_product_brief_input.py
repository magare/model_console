from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from run_product_brief_batch import (
    GEMINI_DRAFTS_DIR,
    IDEAS_PATH,
    PROMPT_PATH,
    REPO_ROOT,
    ensure_dirs,
    parse_markdown_table,
    render_idea_block,
    write_task_file,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a Gemini draft and task file for one idea rank")
    parser.add_argument("--rank", required=True, type=int)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def build_gemini_prompt(prompt_template: str, idea_block: str) -> str:
    return (
        prompt_template.replace("[PASTE APP IDEA HERE]", idea_block)
        + "\n\nOutput requirements for this draft stage:\n"
        + "- Return Markdown only.\n"
        + "- Do not wrap the response in JSON.\n"
        + "- Do not mention tool limitations.\n"
        + "- Keep the brief practical, specific, and tightly scoped.\n"
    )


def main() -> int:
    args = parse_args()
    ensure_dirs()
    rows = {row.rank: row for row in parse_markdown_table(IDEAS_PATH)}
    if args.rank not in rows:
        raise SystemExit(f"Rank {args.rank} not found in {IDEAS_PATH}")

    row = rows[args.rank]
    prompt_template = PROMPT_PATH.read_text(encoding="utf-8")
    gemini_prompt = build_gemini_prompt(prompt_template, render_idea_block(row))
    draft_path = GEMINI_DRAFTS_DIR / f"{row.slug}.md"

    if draft_path.exists() and not args.overwrite:
        write_task_file(row, prompt_template, overwrite=True)
        print(draft_path)
        return 0

    proc = subprocess.run(
        [
            "gemini",
            "-p",
            gemini_prompt,
            "--output-format",
            "json",
            "--model",
            "gemini-2.5-flash-lite",
            "--approval-mode",
            "default",
            "--include-directories",
            str(REPO_ROOT),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    # The CLI returns JSON with a `response` field in this mode.
    import json

    payload = json.loads(proc.stdout)
    response = payload.get("response", "")
    draft_path.write_text(response.strip() + "\n", encoding="utf-8")
    write_task_file(row, prompt_template, overwrite=True)
    print(draft_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
