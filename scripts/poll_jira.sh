#!/bin/bash
# Poll Jira for ai-ready tickets and process them via Claude Code
# Run via cron: */5 * * * * /path/to/poll_jira.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOCKFILE="/tmp/degreesight-agent.lock"
LOG_DIR="$PROJECT_DIR/logs"

mkdir -p "$LOG_DIR"

# Process lock - prevent concurrent runs
if [ -f "$LOCKFILE" ]; then
    LOCK_PID=$(cat "$LOCKFILE")
    if kill -0 "$LOCK_PID" 2>/dev/null; then
        echo "Agent already running (PID $LOCK_PID). Skipping."
        exit 0
    fi
fi
echo $$ > "$LOCKFILE"
trap 'rm -f $LOCKFILE' EXIT

# Load environment
if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    source "$PROJECT_DIR/.env"
    set +a
fi

LOG_FILE="$LOG_DIR/$(date +%Y-%m-%d_%H-%M-%S).log"

echo "=== DegreeSight Agent Run: $(date) ===" | tee "$LOG_FILE"

# Use Claude Code to fetch and process tickets
claude -p "You are the DegreeSight autonomous coding agent.

1. Connect to Jira at $JIRA_URL and find tickets with label 'ai-ready' in status 'To Do'
2. For each ticket:
   a. Read the description and acceptance criteria
   b. Clone the associated repository
   c. Create a feature branch
   d. Implement the changes
   e. Run tests
   f. Commit and push
   g. Create a PR
   h. Update the Jira ticket status to 'In Review'
   i. Post a summary to Slack

Only process ONE ticket per run. Pick the highest priority unassigned ticket.

If no tickets are available, report that and exit." \
  --allowedTools "Read,Write,Edit,Bash,Glob,Grep" \
  --max-turns "$AGENT_MAX_TURNS" \
  --max-budget-usd "$AGENT_MAX_BUDGET_USD" \
  --model "$AGENT_MODEL" \
  --mcp-config "$PROJECT_DIR/config/mcp.json" \
  --output-format json 2>&1 | tee -a "$LOG_FILE"

echo "=== Run Complete: $(date) ===" | tee -a "$LOG_FILE"
