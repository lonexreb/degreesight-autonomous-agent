"""Slack integration for posting agent status updates."""

from __future__ import annotations

import httpx
import structlog

from src.agent.coding_agent import AgentResult

logger = structlog.get_logger()


class SlackNotifier:
    """Posts agent status updates to Slack via webhook."""

    def __init__(self, webhook_url: str, channel: str = "#dev-agent") -> None:
        self._webhook_url = webhook_url
        self._channel = channel
        self._client = httpx.AsyncClient(timeout=10.0)

    async def notify_ticket_started(self, ticket_key: str, summary: str) -> None:
        await self._post(
            f":robot_face: *Agent picking up {ticket_key}*\n>{summary}"
        )

    async def notify_pr_created(self, result: AgentResult) -> None:
        if result.pr_url:
            await self._post(
                f":white_check_mark: *PR created for {result.ticket_key}*\n"
                f"<{result.pr_url}|View PR>"
            )
        else:
            await self._post(
                f":warning: *{result.ticket_key}* - Changes pushed to `{result.branch_name}` "
                f"but PR creation failed"
            )

    async def notify_failure(self, ticket_key: str, error: str) -> None:
        await self._post(
            f":x: *Agent failed on {ticket_key}*\n```{error[:500]}```"
        )

    async def post_daily_summary(
        self,
        tickets_attempted: int,
        prs_created: int,
        prs_merged: int,
        failures: int,
        total_cost: float,
    ) -> None:
        await self._post(
            f":bar_chart: *Daily Agent Summary*\n"
            f"- Tickets attempted: {tickets_attempted}\n"
            f"- PRs created: {prs_created}\n"
            f"- PRs merged: {prs_merged}\n"
            f"- Failures: {failures}\n"
            f"- Total cost: ${total_cost:.2f}"
        )

    async def _post(self, text: str) -> None:
        try:
            response = await self._client.post(
                self._webhook_url,
                json={"text": text, "channel": self._channel},
            )
            response.raise_for_status()
        except httpx.HTTPError:
            logger.exception("slack_post_failed")

    async def close(self) -> None:
        await self._client.aclose()
