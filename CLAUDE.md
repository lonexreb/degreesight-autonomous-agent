# MorningStar

Autonomous coding agent that reads a PRD from Notion, analyzes a codebase, generates tasks, and implements them using Claude Code CLI. Posts progress to Slack.

## Tech Stack

- Python 3.10+ with `typer` + `rich`
- Claude Code CLI (headless mode via `-p`)
- Notion MCP for PRD ingestion
- Slack webhooks for status updates

## Install

```bash
pip install -e ".[dev]"
```

## Usage

```bash
morningstar run \
  --notion-url "https://notion.so/PRD-abc123" \
  --slack-webhook "https://hooks.slack.com/services/..." \
  --repo /path/to/repo
```

## Project Structure

```
src/morningstar/
  __init__.py    -- version
  cli.py         -- typer CLI entry point (run, version, dry-run, confirm gate)
  engine.py      -- core loop (fetch PRD, generate tasks, execute, git commit)
  banner.py      -- ASCII art banner and branding
```

## Conventions

- `TaskResult` is frozen (immutable). `RunState` is mutable (accumulated in the loop).
- All Claude CLI calls go through `_run_claude()` in engine.py
- Slack posts go through `slack_post()` in engine.py
- Logs written to `<target-repo>/.agent-logs/`
- Budget tracked via `RunState.cost` -- includes PRD fetch + task gen + execution
- All user-supplied inputs are validated before use (model allowlist, webhook URL, task IDs)
- AI-generated task IDs are sanitized via `_sanitize_task_id()` before filesystem use
- `git add` excludes sensitive file patterns (`.env`, `*.pem`, `*.key`, etc.)
- PRD fetch runs in a temp directory with read-only tools (no Bash)
- Task generation uses read-only tools (no Bash) -- only execution gets write + Bash

## Dev Commands

```bash
ruff check src/         # lint
mypy src/               # type check
pytest                  # tests
```
