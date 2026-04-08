"""Jira integration client for fetching and updating tickets."""

from __future__ import annotations

import httpx
import structlog

from src.agent.coding_agent import JiraTicket

logger = structlog.get_logger()


class JiraClient:
    """Client for interacting with Jira REST API v3."""

    def __init__(self, base_url: str, email: str, api_token: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._auth = (email, api_token)
        self._client = httpx.AsyncClient(
            base_url=f"{self._base_url}/rest/api/3",
            auth=self._auth,
            headers={"Accept": "application/json"},
            timeout=30.0,
        )

    async def get_assignable_tickets(
        self,
        project_key: str,
        label: str = "ai-ready",
        max_results: int = 10,
    ) -> list[JiraTicket]:
        """Fetch tickets labeled for AI agent processing."""
        jql = (
            f'project = "{project_key}" '
            f'AND labels = "{label}" '
            f"AND status = \"To Do\" "
            f"ORDER BY priority DESC, created ASC"
        )

        response = await self._client.get(
            "/search",
            params={"jql": jql, "maxResults": max_results, "fields": "summary,description,labels,customfield_10016"},
        )
        response.raise_for_status()
        data = response.json()

        tickets = []
        for issue in data.get("issues", []):
            fields = issue["fields"]
            tickets.append(
                JiraTicket(
                    key=issue["key"],
                    summary=fields.get("summary", ""),
                    description=_extract_text(fields.get("description")),
                    acceptance_criteria=_extract_acceptance_criteria(fields.get("description")),
                    repo_url="",  # Will be resolved from project config
                    labels=fields.get("labels", []),
                    story_points=fields.get("customfield_10016"),
                )
            )

        logger.info("fetched_tickets", count=len(tickets), project=project_key)
        return tickets

    async def transition_ticket(self, ticket_key: str, status: str) -> None:
        """Move a ticket to a new status."""
        # First get available transitions
        response = await self._client.get(f"/issue/{ticket_key}/transitions")
        response.raise_for_status()

        transitions = response.json().get("transitions", [])
        target = next(
            (t for t in transitions if t["name"].lower() == status.lower()),
            None,
        )

        if target is None:
            logger.warning(
                "transition_not_found",
                ticket=ticket_key,
                target_status=status,
                available=[t["name"] for t in transitions],
            )
            return

        await self._client.post(
            f"/issue/{ticket_key}/transitions",
            json={"transition": {"id": target["id"]}},
        )
        logger.info("ticket_transitioned", ticket=ticket_key, status=status)

    async def add_comment(self, ticket_key: str, comment: str) -> None:
        """Add a comment to a Jira ticket."""
        await self._client.post(
            f"/issue/{ticket_key}/comment",
            json={
                "body": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": comment}],
                        }
                    ],
                }
            },
        )
        logger.info("comment_added", ticket=ticket_key)

    async def close(self) -> None:
        await self._client.aclose()


def _extract_text(description: dict | None) -> str:
    """Extract plain text from Atlassian Document Format (ADF)."""
    if description is None:
        return ""
    if isinstance(description, str):
        return description

    texts: list[str] = []
    _walk_adf(description, texts)
    return "\n".join(texts)


def _walk_adf(node: dict, texts: list[str]) -> None:
    if node.get("type") == "text":
        texts.append(node.get("text", ""))
    for child in node.get("content", []):
        _walk_adf(child, texts)


def _extract_acceptance_criteria(description: dict | None) -> str:
    """Try to extract acceptance criteria section from description."""
    full_text = _extract_text(description)
    lower = full_text.lower()

    for marker in ["acceptance criteria", "ac:", "definition of done", "requirements"]:
        idx = lower.find(marker)
        if idx != -1:
            return full_text[idx:]

    return full_text
