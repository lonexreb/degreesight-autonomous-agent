# MorningStar Handover Runbook

This is the single page you need to start, stop, debug, and hand off the 24/7 MorningStar system. Bookmark it.

---

## What MorningStar does on a schedule

Every 15 minutes, a GitHub Actions workflow (`morningstar-scheduled.yml`) runs on ubuntu-latest. It:

1. Queries a **Notion database** for rows with `Status = Pending`.
2. Queries **Jira** for tickets labeled `morningstar` in `To Do`.
3. For each item found:
   - Flips status to `Running`.
   - Creates a branch `morningstar/<source>-<id>` in the target repo.
   - Reads the PRD (Notion page content or Jira ticket description).
   - Generates an ordered task list.
   - Executes each task: code changes + tests + git commits.
   - Pushes the branch and opens a PR via `gh pr create`.
   - Flips status to `Done` (on success) or `Failed` (on any failure), attaches the PR URL and cost note.
4. Updates `.morningstar/weekly-spend.json` and stops if the weekly USD budget is hit.

A second, lighter **watcher** runs hourly as a Claude Code Cloud Task (`/morningstar:watch`) to catch cases where GH Actions missed a fire. It doesn't execute code — it just dispatches the executor workflow.

---

## First-time setup

### 1. Notion database schema

The target Notion database **must** have:

| Column | Type | Notes |
|---|---|---|
| `Name` (or similar title column) | Title | Becomes the PR title |
| `Status` | Select | Values: `Pending`, `Running`, `Done`, `Failed` |
| `PR` | URL | MorningStar writes the PR URL here when done |
| `Notes` | Rich text | MorningStar writes a cost + task summary here |
| `Notion URL` or `PRD URL` (optional) | URL | If set, MorningStar uses this as the PRD source. Otherwise the row's own page URL is used. |

Share the database with your Notion integration (Settings → Connections → add the integration that owns `MORNINGSTAR_NOTION_TOKEN`).

### 2. Jira setup

- Create a project label called `morningstar`.
- Tickets in `To Do` with this label are picked up.
- MorningStar transitions them to `In Progress` when starting, `Done` or `Failed` after finishing.
- If the ticket description contains a Notion URL, that's used as the PRD; otherwise the description body is used inline.
- Jira API token: https://id.atlassian.com/manage-profile/security/api-tokens

### 3. GitHub configuration (in the repo where the workflow runs)

**Variables** (Settings → Secrets and variables → Actions → Variables):
| Variable | Example | Purpose |
|---|---|---|
| `MORNINGSTAR_ENV` | `prod` | Picks the GH environment for scoped secrets |
| `MORNINGSTAR_NOTION_DB_ID` | `a1b2c3...` (32 hex) | The PRD queue |
| `MORNINGSTAR_JIRA_URL` | `https://degreesight.atlassian.net` | |
| `MORNINGSTAR_JIRA_PROJECT_KEY` | `DS` | |
| `MORNINGSTAR_WEEKLY_BUDGET` | `200` | USD cap per ISO week |
| `MORNINGSTAR_TARGET_REPO` | `degreesight/product` | The repo to modify (leave empty to modify this one) |
| `MORNINGSTAR_TARGET_BRANCH` | `main` | Default: `main` |

**Secrets** (environment-scoped on the `MORNINGSTAR_ENV` environment):
| Secret | How to get it |
|---|---|
| `ANTHROPIC_API_KEY` | https://console.anthropic.com |
| `MORNINGSTAR_NOTION_TOKEN` | Notion integration (starts with `secret_` or `ntn_`) |
| `MORNINGSTAR_JIRA_EMAIL` | Your Atlassian account email |
| `MORNINGSTAR_JIRA_TOKEN` | Atlassian API token |
| `MORNINGSTAR_SLACK_WEBHOOK` | Slack Incoming Webhooks |
| `MORNINGSTAR_SLACK_BOT_TOKEN` | `xoxb-...` bot token (optional, for two-way Q&A) |
| `MORNINGSTAR_SLACK_CHANNEL_ID` | e.g. `C01234567` (optional, for two-way Q&A) |
| `MORNINGSTAR_TARGET_REPO_TOKEN` | PAT with `repo` + `workflow` scopes on the target repo |

### 4. Watcher (optional, hourly)

Inside a Claude Code session, run:

```
/schedule /morningstar:watch --cron "0 * * * *"
```

The Cloud Task auto-expires after 7 days — re-register weekly, or rely only on the GH Actions 15-min cron (the primary runner; the watcher is defense in depth).

---

## Day-to-day operations

### Start a queue run manually (smoke test)

GitHub UI → Actions → `morningstar-scheduled` → Run workflow. No input needed.

For a no-cost preview: Actions → `morningstar-scheduled-dryrun` → Run workflow. This only scans the queue and reports counts; it does not execute.

For a zero-cost local smoke test that exercises the full pipeline against a temp git repo with all integrations mocked:

```bash
python morningstar_demo.py
```

Use this on a local checkout to confirm the engine builds, plans, and commits correctly after a deploy.

### Check queue health at any time

```bash
morningstar status --repo /path/to/target-repo
```

Reads `.morningstar/run-history.jsonl` (auto-written by every queue run) and prints:

- A weekly-spend bar: `<spend> / <weekly_budget>` for the current ISO week, color-coded against the cap.
- The last N runs (default 10) with timestamp, scanned/succeeded/failed/skipped, cost, and live-vs-dry mode.
- Aggregate success rate over the displayed window — color-coded so a glance tells you whether the system is healthy.
- The most recent PR URLs.

Use this for fast triage before opening GH Actions logs. No external services required — it works offline against the repo.

To see a longer history: `morningstar status -r /path/to/repo --limit 50`.

### Pause the 24/7 system

GitHub UI → Actions → `morningstar-scheduled` → ⋯ → **Disable workflow**. The cron stops firing immediately. No other state changes.

### Read logs for a specific run

1. GitHub UI → Actions → pick the run.
2. Scroll to the `Upload logs` step output.
3. Download the `agent-logs-<run-id>` artifact.
4. Inside you'll find:
   - `.agent-logs/prd.md` — the fetched PRD
   - `.agent-logs/tasks.json` — the generated task list
   - `.agent-logs/task-<id>.json` — per-task Claude output
   - `.agent-logs/task-<id>-retry.json` — retry output (if any)
   - `.agent-logs/task-<id>-answer.json` — Slack Q&A follow-up (if any)
   - `.morningstar/weekly-spend.json` — budget ledger
   - `.morningstar/run-history.jsonl` — append-only audit trail of every queue run (powers `morningstar status`)

### Rotate a secret

GitHub UI → Settings → Secrets and variables → Actions → Environment → `MORNINGSTAR_ENV` → edit the secret. Next cron tick picks it up automatically.

### Recover a stuck "Running" item

If an item's status is stuck on `Running` because the runner crashed mid-flight:

1. Check the GH Actions log for that run to confirm the crash.
2. Manually flip the Notion row (or Jira ticket) back to `Pending`.
3. The next cron tick re-processes it.

There's no automatic lock-recovery — by design, 15-minute cron cadence plus idempotent status flips avoid most races.

### Emergency stop (runaway spend)

1. Disable `morningstar-scheduled` workflow (GitHub UI).
2. In Slack, verify no task is mid-execution.
3. If cost is the concern, lower `MORNINGSTAR_WEEKLY_BUDGET` and re-enable; the next run will self-stop if the budget is exceeded.

---

## Debugging checklist

| Symptom | Likely cause | Fix |
|---|---|---|
| Workflow runs but finds 0 items | Notion integration not shared with DB, or wrong DB ID | Check integration connections in Notion; verify `MORNINGSTAR_NOTION_DB_ID` |
| `Notion status update failed` warning | Token doesn't have write access | Re-grant write permission to integration |
| Jira returns 401 | Token expired or email mismatch | Regenerate Atlassian API token |
| `gh pr create` fails | `MORNINGSTAR_TARGET_REPO_TOKEN` missing `repo` scope | Re-mint PAT with both `repo` + `workflow` |
| Tasks repeatedly fail on same PRD | PRD is ambiguous, too large, or needs human input | Move row to `Failed`; rewrite PRD; re-mark `Pending` |
| Weekly budget hit early | Single run is too expensive | Lower `--task-budget` default or split PRDs |
| Slack silent | Webhook URL invalid | Re-check `MORNINGSTAR_SLACK_WEBHOOK` format |

---

## Architecture at a glance

See `docs/ARCHITECTURE.md` for the full diagram. One-line summary:

```
Notion + Jira  →  (watcher on Anthropic cloud, hourly)  →  dispatches
                                                             |
                                                             v
              GitHub Actions cron (15m)  →  morningstar process-queue
                                                             |
                                                             v
              branch + commits + tests + PR in target repo
```

Everything reuses the existing engine (`src/morningstar/engine.py`) — `process_queue()` wraps `fetch_prd` → `generate_tasks` → `execute_task` in a loop with Notion/Jira status bookkeeping. No new storage layer.

---

## Contacts

- Original author: @lonexreb (Shubhankar)
- Issues: https://github.com/lonexreb/morningstar/issues
- Runtime logs: GitHub Actions → `morningstar-scheduled`
- Cost dashboard: https://console.anthropic.com → Usage
