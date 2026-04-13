# Security Policy

## How MorningStar Works

MorningStar runs Claude Code CLI with `--permission-mode dontAsk` and full tool access (`Read`, `Write`, `Edit`, `Bash`, `Glob`, `Grep`) in your target repository. This means **it can execute arbitrary shell commands and modify any file** in the repo directory with the permissions of your OS user.

This is by design -- the agent needs to install dependencies, run tests, and write code. However, it means you should:

- Only run MorningStar on repositories you trust
- Only point it at Notion PRDs you trust (PRD content is passed to the LLM and could influence agent behavior)
- Review generated commits before pushing to shared branches
- Use the `--dry-run` flag to preview tasks before execution
- Set conservative `--budget` limits
- Run in an isolated environment (VM, container) for untrusted PRDs

## Security Mitigations

- **Confirmation prompt**: MorningStar asks for confirmation before executing tasks (bypass with `--yes`)
- **Budget limits**: Per-task and total budget caps prevent runaway costs
- **Sensitive file exclusion**: `git add` excludes `.env`, `*.pem`, `*.key`, `credentials.json`, and other secret patterns
- **Task ID sanitization**: AI-generated task IDs are sanitized to prevent path traversal
- **Session ID validation**: Claude session IDs are validated before reuse
- **Slack webhook validation**: Only `hooks.slack.com` URLs are accepted
- **Model allowlist**: Only known Claude model names are accepted
- **PRD fetch isolation**: PRD fetching runs in a temp directory with read-only tools
- **No home directory access**: Agent prompt explicitly prohibits reading `~/.ssh`, `~/.aws`, etc.

## Reporting Vulnerabilities

If you discover a security vulnerability, please report it privately:

1. **Do not** open a public GitHub issue
2. Email: [security contact email]
3. Include: description, reproduction steps, and potential impact

We will acknowledge within 48 hours and provide a fix timeline within 7 days.
