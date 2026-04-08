# DegreeSight Autonomous Coding Agent

## Project Overview
Autonomous AI coding agent that runs 24/7, picks up Jira tickets, codes solutions, creates PRs, handles review feedback, and posts updates to Slack.

## Architecture
- **Orchestrator**: Python FastAPI service receiving Jira webhooks
- **Agent Engine**: Claude Code via Agent SDK (Opus 4.6)
- **Jira Integration**: Atlassian Official MCP Server
- **GitHub Integration**: claude-code-action + gh CLI
- **Slack Notifications**: Slack MCP or webhook
- **Sandboxing**: Docker containers per task
- **Scheduling**: System cron + Claude Code Remote Tasks

## Tech Stack
- Python 3.12+
- FastAPI
- Claude Agent SDK (`claude-agent-sdk`)
- Docker
- GitHub Actions

## Key Conventions
- All agent runs MUST be sandboxed in Docker containers
- Never use `--dangerously-skip-permissions` outside containers
- Use `--max-budget-usd` on every agent invocation
- Log all agent actions to audit trail
- PRs require human approval before merge
