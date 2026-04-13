# MorningStar

Autonomous coding agent that reads a PRD from Notion, analyzes a codebase, generates tasks, and implements them using Claude Code CLI. Posts progress to Slack.

## Tech Stack

- Python 3.10+ with `typer` + `rich`
- Claude Code CLI (headless mode via `-p`)
- Notion MCP for PRD ingestion
- Slack webhooks for status updates

## Install

```bash
pip install -e .
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
  cli.py         -- typer CLI entry point (run, version commands)
  engine.py      -- core loop (fetch PRD, generate tasks, execute, git commit)
  banner.py      -- ASCII art banner and branding
```

## Conventions

- Immutable dataclasses for state (`RunState`, `TaskResult`)
- All Claude CLI calls go through `_run_claude()` in engine.py
- Slack posts go through `slack_post()` in engine.py
- Logs written to `<target-repo>/.agent-logs/`
- Budget tracked via `RunState.cost` -- checked before each task
