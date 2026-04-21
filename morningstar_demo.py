#!/usr/bin/env python3
"""Live demo of MorningStar's queue-processing loop.

Runs end-to-end -- fetch queue → update status → fetch PRD → generate tasks →
execute tasks → open PR -- against a throwaway git repo with all external
integrations (Notion, Jira, Claude CLI, GitHub `gh`) mocked out. Produces real
git commits so you can see the pipeline's tangible output without needing any
credentials.

Run:
    python morningstar_demo.py
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from morningstar.engine import (
    PendingItem,
    QueueConfig,
    TaskResult,
    process_queue,
    read_weekly_spend,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("morningstar.demo")

# ── Fake PRD + tasks ────────────────────────────────────────────

FAKE_PRD = """\
# Add hello world endpoint

## Problem
The service has no health-check surface yet -- ops needs something to ping
before we add more routes.

## Requirements
- New file `app.py` with a function `hello() -> str` that returns "hello world"
- Unit test `test_app.py` that asserts `hello() == "hello world"`
- Short README note describing the endpoint
"""

FAKE_TASKS = [
    {
        "id": "add-hello-endpoint",
        "title": "Add hello() function",
        "description": "Create app.py with hello() returning 'hello world'",
        "acceptance_criteria": "hello() returns 'hello world'",
        "test_command": "python -c 'from app import hello; assert hello() == \"hello world\"'",
    },
    {
        "id": "add-hello-test",
        "title": "Add unit test for hello()",
        "description": "Create test_app.py asserting hello() == 'hello world'",
        "acceptance_criteria": "pytest passes",
        "test_command": "pytest test_app.py -q",
    },
]


# ── Fake adapters ───────────────────────────────────────────────

def fake_fetch_pending_notion(db_id, token, **_kw):
    log.info("[notion] querying db=%s… found 1 Pending row", db_id[:8])
    return [
        PendingItem(
            source="notion",
            source_id="fake-page-abc123",
            title="Add hello world endpoint",
            prd_url="https://notion.so/fake-PRD-abc123",
        )
    ]


def fake_fetch_pending_jira(*_a, **_kw):
    log.info("[jira] (skipped -- no credentials in demo)")
    return []


def fake_set_notion_status(page_id, token, status, **kw):
    pr = kw.get("pr_url")
    notes = kw.get("notes")
    tail = f" pr={pr}" if pr else ""
    tail += f" notes={notes!r}" if notes else ""
    log.info("[notion] %s → %s%s", page_id, status, tail)
    return True


def fake_fetch_prd(url, *, model, log_dir):
    log.info("[claude] fetching PRD from %s via %s…", url, model)
    (log_dir / "prd.md").write_text(FAKE_PRD)
    return FAKE_PRD, 0.04


def fake_generate_tasks(prd, *, repo_path, model, log_dir, max_tasks):
    log.info("[claude] generating tasks (max=%d) via %s…", max_tasks, model)
    import json
    (log_dir / "tasks.json").write_text(json.dumps(FAKE_TASKS, indent=2))
    return FAKE_TASKS, 0.12


def fake_execute_task(task, *, repo_path, **_kw):
    task_id = task["id"]
    title = task["title"]
    log.info("[claude] executing task %s -- %s", task_id, title)

    # Create a real file and commit it so the demo shows tangible output.
    if task_id == "add-hello-endpoint":
        (repo_path / "app.py").write_text(
            "def hello() -> str:\n    return \"hello world\"\n"
        )
        _git(repo_path, "add", "app.py")
    else:
        (repo_path / "test_app.py").write_text(
            "from app import hello\n\n"
            "def test_hello() -> None:\n"
            "    assert hello() == \"hello world\"\n"
        )
        _git(repo_path, "add", "test_app.py")

    _git(repo_path, "commit", "-m", f"morningstar({task_id}): {title}")
    return TaskResult(
        task_id=task_id,
        title=title,
        success=True,
        cost=0.21,
        session_id=f"sess-{task_id[:12]}",
    )


def fake_open_github_pr(repo_path, branch, title, body, *, base="main"):
    log.info("[gh] would open PR %s → %s titled %r", branch, base, title)
    return f"https://github.com/degreesight/demo/pull/1#{branch}"


# ── git helpers ─────────────────────────────────────────────────

def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
    )


def _make_demo_repo(root: Path) -> Path:
    repo = root / "demo-repo"
    repo.mkdir()
    _git(repo, "init", "--initial-branch=main")
    _git(repo, "config", "user.email", "demo@morningstar.local")
    _git(repo, "config", "user.name", "MorningStar Demo")
    (repo / "README.md").write_text(
        "# demo-repo\n\nThrowaway repo used by morningstar_demo.py.\n"
    )
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "init: demo repo")
    return repo


# ── Demo driver ─────────────────────────────────────────────────

def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="morningstar-demo-"))
    try:
        print("\n┌──────────────────────────────────────────────────────────────┐")
        print("│ MorningStar queue processor -- live demo (all I/O mocked)   │")
        print("└──────────────────────────────────────────────────────────────┘\n")

        repo = _make_demo_repo(tmp)
        print(f"• Temp repo:  {repo}")

        cfg = QueueConfig(
            repo_path=repo,
            model="sonnet",
            per_run_budget=25.0,
            per_task_budget=5.0,
            weekly_budget=200.0,
            max_tasks=5,
            notion_db_id="a" * 32,
            notion_token="secret_demo_token_not_real",
            gh_repo="degreesight/demo",
            base_branch="main",
        )
        print(f"• Model:      {cfg.model}")
        print(f"• Budgets:    task=${cfg.per_task_budget} "
              f"run=${cfg.per_run_budget} week=${cfg.weekly_budget}\n")

        patches = [
            patch("morningstar.engine.fetch_pending_notion", fake_fetch_pending_notion),
            patch("morningstar.engine.fetch_pending_jira", fake_fetch_pending_jira),
            patch("morningstar.engine.set_notion_status", fake_set_notion_status),
            patch("morningstar.engine.fetch_prd", fake_fetch_prd),
            patch("morningstar.engine.generate_tasks", fake_generate_tasks),
            patch("morningstar.engine.execute_task", fake_execute_task),
            patch("morningstar.engine.open_github_pr", fake_open_github_pr),
        ]
        for p in patches:
            p.start()
        try:
            result = process_queue(cfg)
        finally:
            for p in patches:
                p.stop()

        # ── Summary ────────────────────────────────────────────
        week_key, spent = read_weekly_spend(repo)
        print("\n────────── Run summary ──────────")
        print(f"scanned      : {result.scanned}")
        print(f"succeeded    : {result.succeeded}")
        print(f"failed       : {result.failed}")
        print(f"skipped      : {result.skipped}")
        print(f"run cost     : ${result.total_cost:.2f}")
        print(f"PRs opened   : {result.prs_opened}")
        print(f"weekly spend : ${spent:.2f} ({week_key})")

        print("\n────────── git log on morningstar branch ──────────")
        out = subprocess.run(
            ["git", "log", "--oneline", "-10"],
            cwd=str(repo), capture_output=True, text=True,
        )
        print(out.stdout or "(no commits)")

        print("────────── files produced ──────────")
        for path in sorted(repo.rglob("*")):
            if ".git" in path.parts:
                continue
            rel = path.relative_to(repo)
            if path.is_file():
                print(f"  {rel}")

        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        print(f"\n• Cleaned up: {tmp}")


if __name__ == "__main__":
    sys.exit(main())
