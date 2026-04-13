```
                            .
                           /|\
                          / | \
                         /  |  \
                        /   |   \
                  .----'    |    '----.
                   \        |        /
                    \       |       /
                     \      |      /
                      \     |     /
                       \    |    /
                        \   |   /
                         \  |  /
                          \ | /
                           \|/
                            '

  ███╗   ███╗ ██████╗ ██████╗ ███╗   ██╗██╗███╗   ██╗ ██████╗ ███████╗████████╗ █████╗ ██████╗
  ████╗ ████║██╔═══██╗██╔══██╗████╗  ██║██║████╗  ██║██╔════╝ ██╔════╝╚══██╔══╝██╔══██╗██╔══██╗
  ██╔████╔██║██║   ██║██████╔╝██╔██╗ ██║██║██╔██╗ ██║██║  ███╗███████╗   ██║   ███████║██████╔╝
  ██║╚██╔╝██║██║   ██║██╔══██╗██║╚██╗██║██║██║╚██╗██║██║   ██║╚════██║   ██║   ██╔══██║██╔══██╗
  ██║ ╚═╝ ██║╚██████╔╝██║  ██║██║ ╚████║██║██║ ╚████║╚██████╔╝███████║   ██║   ██║  ██║██║  ██║
  ╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝╚═╝╚═╝  ╚═══╝ ╚═════╝ ╚══════╝   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝
```

**Autonomous coding agent that turns Notion PRDs into working code.**

Give it a PRD, a repo, and a Slack webhook. It reads the requirements, analyzes the codebase, figures out what's missing, and builds it -- task by task, with tests, commits, and progress updates.

---

## Install

```bash
pipx install morningstar-agent
```

Or from source:

```bash
git clone https://github.com/lonexreb/degreesight-autonomous-agent.git
cd degreesight-autonomous-agent
pip install -e .
```

### Prerequisites

- Python 3.11+
- [Claude Code CLI](https://claude.ai/code) installed and authenticated
- Notion MCP connected in your Claude Code config

---

## Usage

```bash
morningstar run \
  --notion-url "https://notion.so/Your-PRD-Page-abc123" \
  --slack-webhook "https://hooks.slack.com/services/T.../B.../xxx" \
  --repo /path/to/your/project
```

### Options

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `--notion-url` | `-n` | required | Notion page URL or ID with the PRD |
| `--slack-webhook` | `-s` | required | Slack webhook for status updates |
| `--repo` | `-r` | required | Path to the target repository |
| `--model` | `-m` | `sonnet` | Claude model (`sonnet`, `opus`, `haiku`) |
| `--budget` | `-b` | `50.00` | Total USD budget for the run |
| `--task-budget` | | `5.00` | Max USD per individual task |

---

## How It Works

```
 1. Fetch PRD          Read full Notion page via Claude Code + MCP
                        |
 2. Analyze             Explore the codebase, diff against PRD requirements
                        |
 3. Plan                Generate a structured task list (ordered by dependency)
                        |
 4. Execute             For each task:
                          - Implement code changes
                          - Write/update tests
                          - Run tests, fix failures
                          - Git commit
                          - Post to Slack
                        |
 5. Summary             Report: tasks done, tasks failed, total cost
```

If a task fails, MorningStar retries once using Claude Code's session resumption to preserve context from the first attempt.

---

## Slack Updates

MorningStar posts to your Slack channel at every step:

```
MorningStar started. Reading PRD from Notion...
Found 7 tasks to implement. Starting work...
[1/7] Starting: Implement attendance analytics service
[1/7] Completed: Implement attendance analytics service ($1.80)
[2/7] Starting: Add homework analytics endpoints
[2/7] Completed: Add homework analytics endpoints ($1.50)
...
MorningStar complete: 7 done, 0 failed. Cost: $12.50/$50.00
```

---

## Logs

All agent output is saved to `<repo>/.agent-logs/`:

| File | Content |
|------|---------|
| `prd.md` | Full PRD text fetched from Notion |
| `tasks.json` | Generated task list |
| `task-<id>.json` | Claude's full output per task |
| `task-<id>-retry.json` | Retry output (if task failed first attempt) |

---

## Environment

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Your Anthropic API key |

The Claude Code CLI must be authenticated (`claude auth login`).

---

## License

MIT
