"""MorningStar engine -- the autonomous coding loop."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from rich.console import Console

AGENT_PROMPT = """\
You are an autonomous coding agent. You read PRDs and implement them in existing codebases.

## Rules
1. Read CLAUDE.md and README.md first to understand project conventions
2. Follow existing codebase patterns exactly -- match style, naming, imports, structure
3. Write tests for every change you make
4. Run tests after every change and fix failures before finishing
5. If tests fail, diagnose the root cause and fix (max 2 retry attempts)
6. Never change unrelated code
7. Use the project's existing linter, formatter, and build tools
8. Prefer small, focused changes over large refactors
9. Check for existing utilities before writing new ones

## When you need human input
If you cannot proceed without a decision from a human, include this in your response:
QUESTION: [your question here]
CONTEXT: [why you need this answered, what options you see]
DEFAULT: [what you'll do if no answer comes]
"""


@dataclass
class TaskResult:
    task_id: str
    title: str
    success: bool
    cost: float = 0.0
    session_id: str = ""
    error: str | None = None


@dataclass
class RunState:
    completed: int = 0
    failed: int = 0
    cost: float = 0.0
    tasks: list[dict] = field(default_factory=list)


def _run_claude(
    prompt: str,
    *,
    cwd: str | Path,
    model: str = "sonnet",
    budget: float = 5.0,
    tools: str = "Read,Glob,Grep,Bash",
    json_schema: str | None = None,
    resume: str | None = None,
) -> dict:
    """Invoke Claude Code CLI in headless mode and return parsed JSON."""
    cmd = [
        "claude", "-p", prompt,
        "--output-format", "json",
        "--max-budget-usd", str(budget),
        "--permission-mode", "dontAsk",
        "--model", model,
        "--allowedTools", tools,
        "--append-system-prompt", AGENT_PROMPT,
    ]

    if json_schema:
        cmd.extend(["--json-schema", json_schema])

    if resume:
        cmd.extend(["--resume", resume])

    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=1800,  # 30 min
        )
        output = result.stdout.strip()
        if output:
            return json.loads(output)
        return {
            "is_error": True,
            "result": result.stderr[:500] if result.stderr else "No output",
            "total_cost_usd": 0,
            "session_id": "",
        }
    except subprocess.TimeoutExpired:
        return {
            "is_error": True,
            "result": "Timed out after 30 minutes",
            "total_cost_usd": 0,
            "session_id": "",
        }
    except (json.JSONDecodeError, FileNotFoundError) as e:
        return {
            "is_error": True,
            "result": str(e),
            "total_cost_usd": 0,
            "session_id": "",
        }


def slack_post(webhook: str, message: str) -> None:
    """Post a message to Slack via incoming webhook."""
    try:
        httpx.post(
            webhook,
            json={"text": message},
            timeout=10,
        )
    except httpx.HTTPError:
        pass


def fetch_prd(
    notion_url: str,
    *,
    model: str,
    log_dir: Path,
    console: Console,
) -> str:
    """Step 1: Fetch PRD content from Notion."""
    result = _run_claude(
        f"Fetch the content of this Notion page and return the FULL text, "
        f"preserving all sections, headings, tables, and details. "
        f"Do not summarize -- return everything. Page URL or ID: {notion_url}",
        cwd=Path.home(),
        model=model,
        budget=1.0,
        tools="Read,Bash",
    )

    prd_text = result.get("result", "")
    cost = result.get("total_cost_usd", 0)

    if result.get("is_error") or not prd_text:
        (log_dir / "prd-error.json").write_text(json.dumps(result, indent=2))
        raise RuntimeError("Failed to fetch PRD from Notion")

    (log_dir / "prd.md").write_text(prd_text)
    return prd_text


def generate_tasks(
    prd_text: str,
    *,
    repo_path: Path,
    model: str,
    log_dir: Path,
    console: Console,
) -> list[dict]:
    """Step 2: Analyze codebase and generate task list."""
    task_schema = json.dumps({
        "type": "object",
        "properties": {
            "tasks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "acceptance_criteria": {"type": "string"},
                        "test_command": {"type": "string"},
                    },
                    "required": ["id", "title", "description"],
                },
            },
        },
        "required": ["tasks"],
    })

    prompt = (
        f"You have access to this codebase. Here is the PRD:\n\n"
        f"--- PRD START ---\n{prd_text}\n--- PRD END ---\n\n"
        f"Analyze the codebase thoroughly. Read CLAUDE.md, README.md, and key source files. "
        f"Identify what features from the PRD are NOT yet implemented or are incomplete.\n\n"
        f"Create a task list of concrete, implementable work items. Each task should be small "
        f"enough to complete in one session (1-3 files changed). Order by dependency.\n\n"
        f"For each task:\n"
        f"- id: short kebab-case identifier\n"
        f"- title: one-line description\n"
        f"- description: what to implement, which files, what patterns to follow\n"
        f"- acceptance_criteria: how to verify\n"
        f"- test_command: shell command to run tests"
    )

    result = _run_claude(
        prompt,
        cwd=repo_path,
        model=model,
        budget=3.0,
        tools="Read,Glob,Grep,Bash",
        json_schema=task_schema,
    )

    cost = result.get("total_cost_usd", 0)

    # Try structured_output first, then parse result
    tasks = None
    structured = result.get("structured_output")
    if structured and isinstance(structured, dict):
        tasks = structured.get("tasks")

    if not tasks:
        try:
            parsed = json.loads(result.get("result", "{}"))
            tasks = parsed.get("tasks", [])
        except (json.JSONDecodeError, TypeError):
            tasks = []

    if not tasks:
        (log_dir / "tasks-error.json").write_text(json.dumps(result, indent=2))
        raise RuntimeError("Failed to generate task list")

    (log_dir / "tasks.json").write_text(json.dumps(tasks, indent=2))
    return tasks


def execute_task(
    task: dict,
    *,
    repo_path: Path,
    model: str,
    budget_per_task: float,
    log_dir: Path,
) -> TaskResult:
    """Step 3: Execute a single task."""
    task_id = task["id"]
    title = task["title"]
    desc = task.get("description", "")
    ac = task.get("acceptance_criteria", "Tests pass")
    test_cmd = task.get("test_command", "")

    prompt_parts = [
        f"Implement this task in the codebase:\n\n"
        f"Task: {title}\n"
        f"Description: {desc}\n"
        f"Acceptance Criteria: {ac}\n\n"
        f"Rules:\n"
        f"- Read CLAUDE.md first for project conventions\n"
        f"- Follow existing codebase patterns exactly\n"
        f"- Write or update tests for your changes\n"
        f"- Run tests after making changes and fix any failures\n"
        f"- Do not modify unrelated code\n"
        f"- Do not add unnecessary dependencies",
    ]

    if test_cmd:
        prompt_parts.append(f"- Run this test command to verify: {test_cmd}")

    prompt = "\n".join(prompt_parts)

    result = _run_claude(
        prompt,
        cwd=repo_path,
        model=model,
        budget=budget_per_task,
        tools="Read,Write,Edit,Bash,Glob,Grep",
    )

    cost = result.get("total_cost_usd", 0)
    is_error = result.get("is_error", False)
    session_id = result.get("session_id", "")

    (log_dir / f"task-{task_id}.json").write_text(json.dumps(result, indent=2))

    # Retry once on error
    if is_error and session_id:
        retry = _run_claude(
            "The previous attempt had an error. Review what went wrong, "
            "fix it, and complete the task. Run tests to verify.",
            cwd=repo_path,
            model=model,
            budget=3.0,
            tools="Read,Write,Edit,Bash,Glob,Grep",
            resume=session_id,
        )
        retry_cost = retry.get("total_cost_usd", 0)
        cost += retry_cost
        is_error = retry.get("is_error", False)
        (log_dir / f"task-{task_id}-retry.json").write_text(
            json.dumps(retry, indent=2)
        )

    # Commit changes
    _git_commit(repo_path, title, task_id, cost)

    return TaskResult(
        task_id=task_id,
        title=title,
        success=not is_error,
        cost=cost,
        session_id=session_id,
    )


def _git_commit(repo_path: Path, title: str, task_id: str, cost: float) -> None:
    """Commit any pending changes, excluding .agent-logs."""
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
        )
        if not status.stdout.strip():
            return

        subprocess.run(
            ["git", "add", "-A", "--", ":!.agent-logs"],
            cwd=str(repo_path),
            capture_output=True,
        )
        subprocess.run(
            [
                "git", "commit", "-m",
                f"feat: {title}\n\nImplemented by MorningStar (task: {task_id})\nCost: ${cost:.2f}",
            ],
            cwd=str(repo_path),
            capture_output=True,
        )
    except FileNotFoundError:
        pass
