from pydantic_settings import BaseSettings


class AgentConfig(BaseSettings):
    """Configuration for the autonomous coding agent."""

    # Anthropic
    anthropic_api_key: str

    # Jira
    jira_url: str
    jira_email: str
    jira_api_token: str

    # GitHub
    github_token: str
    github_org: str = "degreesight"

    # Slack
    slack_webhook_url: str
    slack_channel: str = "#dev-agent"

    # Agent controls
    agent_max_budget_usd: float = 5.00
    agent_max_turns: int = 50
    agent_model: str = "claude-opus-4-6"
    agent_poll_interval_minutes: int = 5
    agent_daily_budget_usd: float = 100.00

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
