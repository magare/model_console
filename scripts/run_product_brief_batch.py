from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
import shutil


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
QUICK_APPS_ROOT = (
    Path(os.environ["MODEL_CONSOLE_QUICK_APPS_ROOT"]).expanduser().resolve()
    if os.environ.get("MODEL_CONSOLE_QUICK_APPS_ROOT")
    else (REPO_ROOT.parent / "quick_apps").resolve()
)
IDEAS_PATH = QUICK_APPS_ROOT / "ideas.md"
PROMPT_PATH = QUICK_APPS_ROOT / "idea_to_product_brief_prompt.md"
TASKS_DIR = REPO_ROOT / "tasks" / "inbox" / "product_briefs"
OUTPUT_DIR = REPO_ROOT / "artifacts" / "product_briefs"
GEMINI_DRAFTS_DIR = REPO_ROOT / "artifacts" / "product_brief_drafts"
REPORTS_DIR = REPO_ROOT / "artifacts" / "product_brief_batch_reports"


def _python_env() -> dict[str, str]:
    env = os.environ.copy()
    src_path = str(SRC_ROOT)
    existing = env.get("PYTHONPATH", "")
    if existing:
        env["PYTHONPATH"] = os.pathsep.join([src_path, existing])
    else:
        env["PYTHONPATH"] = src_path
    return env


@dataclass
class IdeaRow:
    rank: int
    idea: str
    project_name: str
    software_type: str
    buyer: str
    pain_trigger: str
    mvp: str
    monetization_path: str
    price_point: str
    acquisition_channel: str
    cash_score: str

    @property
    def slug(self) -> str:
        base = self.project_name or self.idea
        slug = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")
        return f"{self.rank:03d}-{slug}"

    @property
    def output_relpath(self) -> str:
        return f"artifacts/product_briefs/{self.slug}.md"

    @property
    def task_relpath(self) -> str:
        return f"tasks/inbox/product_briefs/{self.slug}.md"

    @property
    def run_id(self) -> str:
        return f"pb-{self.slug}"[:55]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate product briefs for all ideas via model_console")
    parser.add_argument("--start-rank", type=int, default=1)
    parser.add_argument("--end-rank", type=int, default=9999)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--sleep-seconds", type=float, default=1.0)
    return parser.parse_args()


def parse_markdown_table(path: Path) -> list[IdeaRow]:
    rows: list[IdeaRow] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        if "---" in line:
            continue
        parts = [part.strip() for part in line.split("|")[1:-1]]
        if not parts or parts[0] == "Rank":
            continue
        if len(parts) != 11:
            continue
        try:
            rank = int(parts[0])
        except ValueError:
            continue
        rows.append(
            IdeaRow(
                rank=rank,
                idea=parts[1],
                project_name=parts[2],
                software_type=parts[3],
                buyer=parts[4],
                pain_trigger=parts[5],
                mvp=parts[6],
                monetization_path=parts[7],
                price_point=parts[8],
                acquisition_channel=parts[9],
                cash_score=parts[10],
            )
        )
    return rows


def render_idea_block(idea: IdeaRow) -> str:
    return "\n".join(
        [
            f"- Rank: {idea.rank}",
            f"- Idea: {idea.idea}",
            f"- Project name: {idea.project_name}",
            f"- Recommended software type: {idea.software_type}",
            f"- Buyer: {idea.buyer}",
            f"- Pain trigger: {idea.pain_trigger}",
            f"- 7-day MVP: {idea.mvp}",
            f"- First monetization path: {idea.monetization_path}",
            f"- Price point: {idea.price_point}",
            f"- Fast acquisition channel: {idea.acquisition_channel}",
            f"- Cash score: {idea.cash_score}/25",
        ]
    )


def build_task_text(prompt_template: str, idea: IdeaRow) -> str:
    prompt_body = prompt_template.replace("[PASTE APP IDEA HERE]", render_idea_block(idea))
    gemini_draft_path = GEMINI_DRAFTS_DIR / f"{idea.slug}.md"
    gemini_draft_text = ""
    if gemini_draft_path.exists():
        gemini_draft_text = gemini_draft_path.read_text(encoding="utf-8")
    draft_section = ""
    if gemini_draft_text.strip():
        draft_section = f"""
Use the following Gemini draft as raw source material. Improve it, correct it, and make the final brief sharper and more decisive, but keep it tightly scoped:

--- BEGIN GEMINI DRAFT ---
{gemini_draft_text}
--- END GEMINI DRAFT ---
"""
    return f"""Create a single Markdown product brief for the idea below.

Write the artifact to this exact path:
{idea.output_relpath}

Requirements:
- The artifact path must be exactly `{idea.output_relpath}`.
- The artifact content must be Markdown.
- Use the exact section structure requested below.
- Tailor every section to the provided idea details.
- Keep the brief practical for a solo builder or very small team.
- Be decisive and concrete, not generic.
- Preserve the recommended software type unless there is a truly material reason not to.
- Include explicit v1 exclusions.
- Include the required executive summary and brutally honest verdict at the end.

Use this brief-generation instruction:

{prompt_body}
{draft_section}
"""


def ensure_dirs() -> None:
    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    GEMINI_DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def write_task_file(idea: IdeaRow, prompt_template: str, overwrite: bool) -> Path:
    path = REPO_ROOT / idea.task_relpath
    if path.exists() and not overwrite:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_task_text(prompt_template, idea), encoding="utf-8")
    return path


def run_task(idea: IdeaRow) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        "-m",
        "model_console",
        "run",
        "--workspace",
        str(REPO_ROOT),
        "--task",
        idea.task_relpath,
        "--loop",
        "product_brief_loop",
        "--run-id",
        idea.run_id,
        "--no-live",
    ]
    return subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=_python_env(),
        text=True,
        capture_output=True,
    )


def output_exists(idea: IdeaRow) -> bool:
    path = REPO_ROOT / idea.output_relpath
    return path.exists() and path.stat().st_size > 0


def select_rows(rows: list[IdeaRow], start_rank: int, end_rank: int, limit: int | None) -> list[IdeaRow]:
    selected = [row for row in rows if start_rank <= row.rank <= end_rank]
    if limit is not None:
        return selected[:limit]
    return selected


def main() -> int:
    args = parse_args()
    ensure_dirs()

    prompt_template = PROMPT_PATH.read_text(encoding="utf-8")
    rows = select_rows(
        parse_markdown_table(IDEAS_PATH),
        start_rank=args.start_rank,
        end_rank=args.end_rank,
        limit=args.limit,
    )
    if not rows:
        print("No idea rows selected.", file=sys.stderr)
        return 1

    report: dict[str, object] = {
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "selected_count": len(rows),
        "output_dir": str(OUTPUT_DIR),
        "items": [],
    }

    for row in rows:
        write_task_file(row, prompt_template, overwrite=args.overwrite)

    if args.prepare_only:
        report["status"] = "prepared_only"
        report_path = REPORTS_DIR / "prepared_only.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 0

    failures = 0
    for row in rows:
        artifact_path = REPO_ROOT / row.output_relpath
        run_dir = REPO_ROOT / "runs" / row.run_id
        if artifact_path.exists() and not args.overwrite:
            item = {
                "rank": row.rank,
                "slug": row.slug,
                "status": "skipped_existing",
                "artifact_path": row.output_relpath,
            }
            report["items"].append(item)
            continue

        if args.overwrite:
            if artifact_path.exists():
                artifact_path.unlink()
            if run_dir.exists():
                shutil.rmtree(run_dir)

        last_stdout = ""
        last_stderr = ""
        success = False
        attempts = args.retries + 1
        for attempt in range(1, attempts + 1):
            proc = run_task(row)
            last_stdout = proc.stdout
            last_stderr = proc.stderr
            if proc.returncode == 0 and output_exists(row):
                success = True
                report["items"].append(
                    {
                        "rank": row.rank,
                        "slug": row.slug,
                        "status": "ok",
                        "attempt": attempt,
                        "artifact_path": row.output_relpath,
                        "run_id": row.run_id,
                    }
                )
                break
            if run_dir.exists():
                shutil.rmtree(run_dir)
            time.sleep(args.sleep_seconds)

        if not success:
            failures += 1
            report["items"].append(
                {
                    "rank": row.rank,
                    "slug": row.slug,
                    "status": "failed",
                    "artifact_path": row.output_relpath,
                    "run_id": row.run_id,
                    "stdout_tail": last_stdout[-4000:],
                    "stderr_tail": last_stderr[-4000:],
                }
            )

    report["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    report["failures"] = failures
    report["status"] = "ok" if failures == 0 else "partial"

    report_path = REPORTS_DIR / "last_run.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if failures == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
