"""Core autonomous coding agent using Claude Agent SDK.

This agent:
1. Receives a Jira ticket with PRD/description
2. Clones the target repo
3. Analyzes the codebase
4. Implements the changes
5. Runs tests and self-corrects
6. Creates a PR with descriptive summary
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import structlog

logger = structlog.get_logger()


@dataclass(frozen=True)
class JiraTicket:
    key: str
    summary: str
    description: str
    acceptance_criteria: str
    repo_url: str
    labels: list[str]
    story_points: int | None = None


@dataclass(frozen=True)
class AgentResult:
    ticket_key: str
    success: bool
    pr_url: str | None = None
    branch_name: str | None = None
    error: str | None = None
    cost_usd: float = 0.0


async def run_coding_agent(
    ticket: JiraTicket,
    *,
    anthropic_api_key: str,
    github_token: str,
    max_budget_usd: float = 5.00,
    max_turns: int = 50,
    model: str = "claude-opus-4-6",
) -> AgentResult:
    """Execute the coding agent for a single Jira ticket.

    Uses Claude Code CLI in headless mode within a temporary directory.
    """
    branch_name = f"agent/{ticket.key.lower()}"

    with tempfile.TemporaryDirectory(prefix=f"agent-{ticket.key}-") as work_dir:
        work_path = Path(work_dir)

        # Clone the repo
        clone_result = subprocess.run(
            ["git", "clone", "--depth=1", ticket.repo_url, str(work_path / "repo")],
            capture_output=True,
            text=True,
            timeout=120,
            env={"GIT_TERMINAL_PROMPT": "0", "GITHUB_TOKEN": github_token},
        )
        if clone_result.returncode != 0:
            return AgentResult(
                ticket_key=ticket.key,
                success=False,
                error=f"Clone failed: {clone_result.stderr}",
            )

        repo_path = work_path / "repo"

        # Create feature branch
        subprocess.run(
            ["git", "checkout", "-b", branch_name],
            cwd=repo_path,
            capture_output=True,
        )

        # Build the agent prompt
        prompt = _build_prompt(ticket)

        # Run Claude Code in headless mode
        try:
            result = subprocess.run(
                [
                    "claude",
                    "-p", prompt,
                    "--allowedTools", "Read,Write,Edit,Bash,Glob,Grep",
                    "--max-turns", str(max_turns),
                    "--max-budget-usd", str(max_budget_usd),
                    "--output-format", "json",
                    "--model", model,
                ],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=1800,  # 30 minute max
                env={
                    "ANTHROPIC_API_KEY": anthropic_api_key,
                    "PATH": subprocess.check_output(
                        ["bash", "-c", "echo $PATH"], text=True
                    ).strip(),
                },
            )
        except subprocess.TimeoutExpired:
            return AgentResult(
                ticket_key=ticket.key,
                success=False,
                error="Agent timed out after 30 minutes",
            )

        if result.returncode != 0:
            logger.error(
                "agent_failed",
                ticket=ticket.key,
                stderr=result.stderr[:500],
            )
            return AgentResult(
                ticket_key=ticket.key,
                success=False,
                error=f"Agent failed: {result.stderr[:500]}",
            )

        # Check if any changes were made
        diff_result = subprocess.run(
            ["git", "diff", "--stat"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        if not diff_result.stdout.strip():
            return AgentResult(
                ticket_key=ticket.key,
                success=False,
                error="Agent made no code changes",
            )

        # Commit, push, and create PR
        subprocess.run(
            ["git", "add", "-A"],
            cwd=repo_path,
            capture_output=True,
        )
        subprocess.run(
            [
                "git", "commit", "-m",
                f"feat({ticket.key}): {ticket.summary}\n\nImplemented by DegreeSight AI Agent",
            ],
            cwd=repo_path,
            capture_output=True,
        )
        push_result = subprocess.run(
            ["git", "push", "-u", "origin", branch_name],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        if push_result.returncode != 0:
            return AgentResult(
                ticket_key=ticket.key,
                success=False,
                branch_name=branch_name,
                error=f"Push failed: {push_result.stderr[:300]}",
            )

        # Create PR via gh CLI
        pr_body = _build_pr_body(ticket)
        pr_result = subprocess.run(
            [
                "gh", "pr", "create",
                "--title", f"[{ticket.key}] {ticket.summary}",
                "--body", pr_body,
                "--head", branch_name,
            ],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        pr_url = pr_result.stdout.strip() if pr_result.returncode == 0 else None

        logger.info(
            "agent_completed",
            ticket=ticket.key,
            pr_url=pr_url,
            branch=branch_name,
        )

        return AgentResult(
            ticket_key=ticket.key,
            success=True,
            pr_url=pr_url,
            branch_name=branch_name,
        )


def _build_prompt(ticket: JiraTicket) -> str:
    return f"""You are an autonomous coding agent working on a Jira ticket.

## Ticket: {ticket.key}
**Summary:** {ticket.summary}

**Description:**
{ticket.description}

**Acceptance Criteria:**
{ticket.acceptance_criteria}

## Instructions

1. First, explore the codebase to understand the project structure, conventions, and patterns.
2. Read any CLAUDE.md, README.md, or contributing guides.
3. Implement the changes described in the ticket.
4. Write or update tests to cover your changes.
5. Run the existing test suite to ensure nothing is broken.
6. If tests fail, fix your implementation until they pass.

## Rules
- Follow existing code conventions and patterns exactly.
- Do NOT change unrelated code.
- Do NOT add unnecessary dependencies.
- Write clean, production-ready code.
- Ensure all tests pass before finishing.
"""


def _build_pr_body(ticket: JiraTicket) -> str:
    return f"""## Summary
Automated implementation for [{ticket.key}]

**Jira Ticket:** {ticket.key} - {ticket.summary}

## Changes
See diff for implementation details.

## Acceptance Criteria
{ticket.acceptance_criteria}

## Test Plan
- [ ] All existing tests pass
- [ ] New tests added for changed functionality
- [ ] Manual verification of acceptance criteria

---
*Generated by DegreeSight AI Agent*
"""
