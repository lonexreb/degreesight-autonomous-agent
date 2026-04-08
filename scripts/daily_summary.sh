#!/bin/bash
# Generate and post daily summary to Slack
# Run via cron: 0 17 * * * /path/to/daily_summary.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Load environment
if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    source "$PROJECT_DIR/.env"
    set +a
fi

claude -p "Generate a daily standup summary for the DegreeSight AI Agent and post it to Slack.

Check:
1. All PRs created by the agent in the last 24 hours (look for commits by the agent email)
2. All PRs merged in the last 24 hours
3. Any CI failures on agent PRs
4. Jira tickets moved to 'In Review' or 'Done' by the agent
5. Total estimated API cost for today's runs

Format as a clean Slack message with emoji and post to the configured channel." \
  --allowedTools "Bash,Read" \
  --max-turns 15 \
  --max-budget-usd 1.00 \
  --model claude-sonnet-4-6 \
  --mcp-config "$PROJECT_DIR/config/mcp.json"
