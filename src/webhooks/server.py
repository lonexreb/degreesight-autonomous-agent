"""FastAPI webhook server for receiving Jira and GitHub events."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Request, Response

from src.agent.coding_agent import AgentResult, JiraTicket, run_coding_agent
from src.agent.config import AgentConfig
from src.integrations.jira_client import JiraClient
from src.integrations.slack_notifier import SlackNotifier

logger = structlog.get_logger()

config = AgentConfig()  # type: ignore[call-arg]

# Track running tasks
_active_tasks: dict[str, asyncio.Task[AgentResult]] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    app.state.jira = JiraClient(config.jira_url, config.jira_email, config.jira_api_token)
    app.state.slack = SlackNotifier(config.slack_webhook_url, config.slack_channel)
    yield
    await app.state.jira.close()
    await app.state.slack.close()


app = FastAPI(title="DegreeSight Agent", lifespan=lifespan)


@app.post("/webhooks/jira")
async def jira_webhook(request: Request) -> Response:
    """Handle Jira webhook events.

    Triggers agent when a ticket is assigned to the AI user
    or when a ticket gets the 'ai-ready' label.
    """
    payload: dict[str, Any] = await request.json()
    event_type = payload.get("webhookEvent", "")

    if event_type not in ("jira:issue_updated", "jira:issue_created"):
        return Response(status_code=200)

    issue = payload.get("issue", {})
    ticket_key = issue.get("key", "")
    fields = issue.get("fields", {})
    labels = fields.get("labels", [])

    # Only process tickets with "ai-ready" label
    if "ai-ready" not in labels:
        return Response(status_code=200)

    # Don't process if already working on this ticket
    if ticket_key in _active_tasks:
        logger.info("ticket_already_active", ticket=ticket_key)
        return Response(status_code=200)

    # Build ticket object
    from src.integrations.jira_client import _extract_acceptance_criteria, _extract_text

    ticket = JiraTicket(
        key=ticket_key,
        summary=fields.get("summary", ""),
        description=_extract_text(fields.get("description")),
        acceptance_criteria=_extract_acceptance_criteria(fields.get("description")),
        repo_url=_resolve_repo_url(fields),
        labels=labels,
        story_points=fields.get("customfield_10016"),
    )

    # Start agent in background
    task = asyncio.create_task(_process_ticket(ticket, request.app))
    _active_tasks[ticket_key] = task

    return Response(status_code=202)


@app.post("/webhooks/github")
async def github_webhook(request: Request) -> Response:
    """Handle GitHub webhook events for PR review feedback."""
    payload: dict[str, Any] = await request.json()
    action = payload.get("action", "")

    if action == "submitted":
        # PR review submitted - trigger agent to address feedback
        review = payload.get("review", {})
        pr = payload.get("pull_request", {})

        if review.get("state") == "changes_requested":
            logger.info(
                "review_changes_requested",
                pr=pr.get("number"),
                reviewer=review.get("user", {}).get("login"),
            )
            # TODO: Trigger agent to address review feedback

    return Response(status_code=200)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "active_tasks": str(len(_active_tasks))}


async def _process_ticket(ticket: JiraTicket, app: FastAPI) -> AgentResult:
    """Process a ticket end-to-end: notify, code, create PR, update Jira."""
    slack: SlackNotifier = app.state.slack
    jira: JiraClient = app.state.jira

    try:
        # Notify start
        await slack.notify_ticket_started(ticket.key, ticket.summary)
        await jira.transition_ticket(ticket.key, "In Progress")
        await jira.add_comment(ticket.key, "AI Agent has picked up this ticket and is working on it.")

        # Run the coding agent
        result = await run_coding_agent(
            ticket,
            anthropic_api_key=config.anthropic_api_key,
            github_token=config.github_token,
            max_budget_usd=config.agent_max_budget_usd,
            max_turns=config.agent_max_turns,
            model=config.agent_model,
        )

        # Handle result
        if result.success:
            await slack.notify_pr_created(result)
            await jira.add_comment(
                ticket.key,
                f"AI Agent created a PR: {result.pr_url or result.branch_name}",
            )
            await jira.transition_ticket(ticket.key, "In Review")
        else:
            await slack.notify_failure(ticket.key, result.error or "Unknown error")
            await jira.add_comment(
                ticket.key,
                f"AI Agent failed to complete this ticket: {result.error}",
            )

        return result

    except Exception:
        logger.exception("ticket_processing_failed", ticket=ticket.key)
        await slack.notify_failure(ticket.key, "Unexpected error during processing")
        return AgentResult(ticket_key=ticket.key, success=False, error="Unexpected error")

    finally:
        _active_tasks.pop(ticket.key, None)


def _resolve_repo_url(fields: dict[str, Any]) -> str:
    """Resolve the repository URL from ticket fields or project config.

    TODO: Implement repo resolution from:
    - Custom Jira field containing repo URL
    - Project-level configuration mapping
    - Labels indicating the target repo
    """
    return ""
