# How MorningStar differs from sweeper-style agents

This page exists because MorningStar gets compared to OpenClaw's **ClawSweeper** more often than it should. They are not substitutes -- they live at opposite ends of the engineering workflow.

## TL;DR

- **ClawSweeper** is a *housekeeping* skill in the [OpenClaw](https://github.com/openclaw/openclaw) ecosystem. It scans your existing GitHub issues and PRs, suggests which ones to close, and (optionally) closes them. It runs weekly and writes nothing into the codebase.
- **MorningStar** is a *production* agent. It picks up a Notion page or Jira ticket, analyzes the target codebase, generates a task plan, implements each task with tests and per-task commits, and opens a PR. It runs on a 15-minute cron and posts to Slack at every step, with two-way Q&A when it gets stuck.

ClawSweeper trims the input pile. MorningStar drains it into PRs. They are complementary.

---

## At a glance

| Dimension | ClawSweeper (OpenClaw skill) | MorningStar (this repo) |
|---|---|---|
| **Job to be done** | Repo hygiene -- surfaces stale issues / PRs and suggests closes | Forward motion -- turns a PRD into a shipped PR |
| **Direction of work** | Backwards-looking (audits what already exists) | Forwards-looking (creates new code) |
| **Inputs** | Open issues + PRs in a GitHub repo | A Notion page or Jira ticket containing a PRD |
| **Outputs** | A "what to close, and why" report; optional close actions | A new branch, commits, tests, and an opened PR |
| **Cadence** | Weekly | Every 15 minutes (24/7 GitHub Actions cron) |
| **Side effects** | Read GitHub, comment / close issues | Read Notion+Jira, write code, run tests, push commits, open PR, post Slack |
| **Scope per run** | One repo, dozens of items skimmed | One PRD -> 1-20 implementation tasks -> one PR |
| **Risk profile** | Low -- worst case is a wrong "close" suggestion | High -- executes generated code with shell access; needs budget caps and `git add` excludes |
| **Blast radius** | The issue tracker | The codebase, CI, the wallet |
| **Distribution** | OpenClaw skill (`~/.openclaw/workspace/skills/`) | Claude Code plugin + standalone Python CLI + GitHub Actions cron |
| **Host runtime** | OpenClaw Gateway (Node.js, port 18789) | Claude Code (interactive) or `claude -p` headless (in CI) |
| **Two-way comms** | Optional, in-channel | First-class -- Slack bot token + channel polling for blocking questions |
| **Budget controls** | None documented | Per-task, per-run, and weekly-ledger budgets, with auto-stop |
| **State across runs** | Stateless (re-scans each time) | `weekly-spend.json` ledger, `.agent-logs/` per repo, status round-trip on Notion + Jira |

---

## How they relate

A team running both would use them in series, not parallel:

```
                    +------------------+
   open issues  --> |   ClawSweeper    | --> trimmed backlog
                    |  (weekly pass)   |
                    +------------------+
                                 |
                                 v
                    +------------------+
   PRD pages    --> |   MorningStar    | --> opened PRs
                    |  (15-min cron)   |
                    +------------------+
                                 |
                                 v
                          human review +
                          merge decision
```

The interface between them is the issue tracker itself. Neither tool needs to know the other exists. ClawSweeper keeps the surface clean; MorningStar consumes whatever PRDs land on it. Human review still gates merge in both directions.

---

## When to pick which

| If your bottleneck is... | Pick |
|---|---|
| "Our issue tracker is full of stale tickets nobody will ever close" | **ClawSweeper** (or any sweeper-style hygiene agent) |
| "We have approved PRDs piling up faster than engineers can pick them up" | **MorningStar** |
| Both | Run them as the diagram above. They do not conflict. |

Neither is a fit for: research-heavy spikes, cross-repo refactors, or work that requires human judgement on every change. Both open or annotate; neither merges.

---

## Why MorningStar exists

MorningStar was scoped specifically against the *forward-motion* gap that sweeper-style agents do not address. An earlier OpenClaw-based deployment ran for over a month without producing the desired Jira-to-PR throughput, and the conclusion was that hygiene tooling and a production coding agent are different products with different design centers:

- A sweeper can be wrong cheaply -- worst case, a "Close?" suggestion is ignored.
- A coding agent that opens PRs is on the critical path. It needs budget guards, two-way Slack Q&A, sensitive-file `.gitignore`-style excludes, per-task atomic commits, and a queue with explicit `Pending -> Running -> Done | Failed` state. None of these are skill-level concerns; they are platform concerns.

That is the reason MorningStar ships as a Claude Code plugin *and* a standalone CLI *and* a GitHub Actions workflow rather than as a single OpenClaw skill -- the dual distribution is what makes the production loop reliable.

---

## Sources

- ClawSweeper / OpenClaw skills system: [openclaw/openclaw](https://github.com/openclaw/openclaw), [docs.openclaw.ai/tools/skills](https://docs.openclaw.ai/tools/skills).
- OpenClaw architecture (Gateway + skills): [openclaw.ai](https://openclaw.ai/), [NVIDIA Technical Blog](https://developer.nvidia.com/blog/build-a-secure-always-on-local-ai-agent-with-nvidia-nemoclaw-and-openclaw/).
- MorningStar: [README](../README.md), [ARCHITECTURE](ARCHITECTURE.md), [HANDOVER](../HANDOVER.md), [USER_GUIDE](USER_GUIDE.md).
