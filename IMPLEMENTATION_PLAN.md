# Implementation Plan: DegreeSight Autonomous Coding Agent

## Phase 0: Immediate Win (Today - 2 hours)
**Goal: Show David a working PR from an AI agent by tonight**

### 0.1 GitHub Copilot Coding Agent for Jira
- [ ] Enable GitHub Copilot Coding Agent on DegreeSight repos
- [ ] Connect Jira to GitHub Copilot (public preview)
- [ ] Assign 3-5 well-defined bug fix tickets to Copilot
- [ ] Monitor first PRs and share results with David

### 0.2 Devin Quick Test (if David wants)
- [ ] Sign up for Devin Core ($20/month)
- [ ] Connect to DegreeSight GitHub repos
- [ ] Connect Jira integration (add `devin` label to tickets)
- [ ] Assign 3-5 well-defined tickets
- [ ] Evaluate output quality

---

## Phase 1: Core Pipeline (Day 1-2)
**Goal: Claude Code picks up Jira tickets and creates PRs**

### 1.1 Environment Setup
- [ ] Set up Python 3.12 project with FastAPI
- [ ] Install Claude Agent SDK (`pip install claude-agent-sdk`)
- [ ] Set up Docker environment for sandboxed agent runs
- [ ] Configure Anthropic API key and credentials

### 1.2 Jira Integration
- [ ] Set up Atlassian MCP Server (OAuth flow)
- [ ] Create Jira webhook for ticket assignment events
- [ ] Build ticket ingestion service (parse PRD, acceptance criteria, linked docs)
- [ ] Implement ticket filtering (by label, type, story points)

### 1.3 Agent Core
- [ ] Build the coding agent using Claude Agent SDK
- [ ] Implement codebase analysis step (clone, map structure)
- [ ] Implement coding step (generate code, run tests)
- [ ] Implement self-correction loop (fix failures, retry)
- [ ] Add budget controls (`--max-budget-usd`)

### 1.4 PR Creation
- [ ] Generate PR descriptions from Jira ticket context
- [ ] Push to feature branches with naming convention
- [ ] Create PR via GitHub API/gh CLI
- [ ] Link PR back to Jira ticket

---

## Phase 2: Feedback Loop (Day 2-3)
**Goal: Agent responds to PR review comments and CI failures**

### 2.1 PR Review Monitoring
- [ ] Set up GitHub webhook for PR review events
- [ ] Parse reviewer comments (general and inline)
- [ ] Trigger agent to address feedback
- [ ] Push fix commits to same PR branch

### 2.2 CI Integration
- [ ] Monitor CI status checks on PRs
- [ ] On failure: agent reads logs, diagnoses, fixes
- [ ] On success: notify via Slack

### 2.3 Slack Notifications
- [ ] Set up Slack webhook or MCP
- [ ] Post updates when: ticket picked up, PR created, PR updated, PR merged
- [ ] Daily standup summary at configured time

---

## Phase 3: Autonomy & Reliability (Day 3-5)
**Goal: Agent runs 24/7 without intervention**

### 3.1 Scheduling
- [ ] Set up cron job for periodic Jira polling
- [ ] Or: use Jira webhooks for event-driven triggers
- [ ] Implement task queue for multiple tickets
- [ ] Add concurrency controls (max parallel tasks)

### 3.2 Monitoring & Observability
- [ ] Audit logging for all agent actions
- [ ] Cost tracking per ticket
- [ ] Success/failure metrics
- [ ] Slack alerts for stuck/failed tasks

### 3.3 Safety Controls
- [ ] Docker sandboxing for every agent run
- [ ] Network restrictions (whitelist only)
- [ ] File system isolation
- [ ] Budget caps per ticket and daily
- [ ] Human-in-the-loop for merge (never auto-merge)

### 3.4 Daily Standup
- [ ] Automated daily summary of:
  - Tickets attempted
  - PRs created
  - PRs merged
  - Failures/blockers
  - Cost consumed
- [ ] Post to Slack at configured time

---

## Phase 4: Optimization (Week 2+)
**Goal: Improve success rate and reduce cost**

### 4.1 Context Enhancement
- [ ] Index codebase conventions (CLAUDE.md per repo)
- [ ] Learn from merged PR patterns
- [ ] Build repo-specific prompt templates
- [ ] Add Confluence integration for deeper PRD context

### 4.2 Ticket Triage Intelligence
- [ ] Auto-classify ticket complexity
- [ ] Route simple tickets to faster/cheaper models
- [ ] Flag tickets that need human attention
- [ ] Suggest ticket improvements for ambiguous PRDs

### 4.3 Multi-Repo Support
- [ ] Support multiple repositories
- [ ] Cross-repo context sharing
- [ ] Unified dashboard
