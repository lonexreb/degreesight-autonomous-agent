"""Tests for engine.py core functions with mocked subprocess."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from morningstar.engine import (
    RunState,
    TaskResult,
    _git_commit,
    _run_claude,
    execute_task,
    fetch_prd,
    generate_tasks,
    slack_post,
)


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    """Create a temp directory simulating a git repo."""
    (tmp_path / ".git").mkdir()
    return tmp_path


@pytest.fixture
def log_dir(tmp_path: Path) -> Path:
    logs = tmp_path / ".agent-logs"
    logs.mkdir()
    return logs


def _claude_response(
    result: str = "done",
    cost: float = 1.0,
    is_error: bool = False,
    session_id: str = "sess-abc123-def456",
    structured_output: dict | None = None,
) -> str:
    """Build a mock Claude CLI JSON response."""
    data = {
        "result": result,
        "total_cost_usd": cost,
        "is_error": is_error,
        "session_id": session_id,
    }
    if structured_output:
        data["structured_output"] = structured_output
    return json.dumps(data)


# ── _run_claude ───────────────────────────────────────────────


class TestRunClaude:
    @patch("morningstar.engine.subprocess.run")
    def test_builds_correct_command(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=_claude_response(), stderr="",
        )

        _run_claude("test prompt", cwd=tmp_path, model="sonnet", budget=2.0)

        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "claude"
        assert "-p" in cmd
        assert "test prompt" in cmd
        assert "--output-format" in cmd
        assert "json" in cmd
        assert "--max-budget-usd" in cmd
        assert "2.0" in cmd
        assert "--model" in cmd
        assert "sonnet" in cmd
        assert "--permission-mode" in cmd
        assert "dontAsk" in cmd

    @patch("morningstar.engine.subprocess.run")
    def test_parses_json_output(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=_claude_response(result="hello", cost=0.5),
            stderr="",
        )

        result = _run_claude("prompt", cwd=tmp_path)
        assert result["result"] == "hello"
        assert result["total_cost_usd"] == 0.5

    @patch("morningstar.engine.subprocess.run")
    def test_handles_timeout(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=1800)

        result = _run_claude("prompt", cwd=tmp_path)
        assert result["is_error"] is True
        assert "Timed out" in result["result"]

    @patch("morningstar.engine.subprocess.run")
    def test_handles_missing_claude(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.side_effect = FileNotFoundError("claude not found")

        result = _run_claude("prompt", cwd=tmp_path)
        assert result["is_error"] is True

    @patch("morningstar.engine.subprocess.run")
    def test_handles_empty_stdout(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="some error",
        )

        result = _run_claude("prompt", cwd=tmp_path)
        assert result["is_error"] is True
        assert "some error" in result["result"]

    @patch("morningstar.engine.subprocess.run")
    def test_handles_invalid_json(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="not json", stderr="",
        )

        result = _run_claude("prompt", cwd=tmp_path)
        assert result["is_error"] is True

    @patch("morningstar.engine.subprocess.run")
    def test_adds_resume_flag_when_valid(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=_claude_response(), stderr="",
        )

        _run_claude("prompt", cwd=tmp_path, resume="valid-session-12345678")
        cmd = mock_run.call_args[0][0]
        assert "--resume" in cmd
        assert "valid-session-12345678" in cmd

    @patch("morningstar.engine.subprocess.run")
    def test_skips_resume_when_invalid(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=_claude_response(), stderr="",
        )

        _run_claude("prompt", cwd=tmp_path, resume="../../bad")
        cmd = mock_run.call_args[0][0]
        assert "--resume" not in cmd

    @patch("morningstar.engine.subprocess.run")
    def test_adds_json_schema(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=_claude_response(), stderr="",
        )

        schema = '{"type":"object"}'
        _run_claude("prompt", cwd=tmp_path, json_schema=schema)
        cmd = mock_run.call_args[0][0]
        assert "--json-schema" in cmd
        assert schema in cmd


# ── slack_post ────────────────────────────────────────────────


class TestSlackPost:
    @patch("morningstar.engine.httpx.post")
    def test_posts_message(self, mock_post: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        slack_post("https://hooks.slack.com/services/T1/B2/abc", "hello")

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs[1]["json"] == {"text": "hello"}

    @patch("morningstar.engine.httpx.post")
    def test_does_not_throw_on_error(self, mock_post: MagicMock) -> None:
        import httpx
        mock_post.side_effect = httpx.TransportError("connection failed")

        # Should not raise
        slack_post("https://hooks.slack.com/services/T1/B2/abc", "hello")


# ── fetch_prd ─────────────────────────────────────────────────


class TestFetchPrd:
    @patch("morningstar.engine._run_claude")
    def test_returns_prd_text_and_cost(self, mock_claude: MagicMock, log_dir: Path) -> None:
        mock_claude.return_value = {
            "result": "# My PRD\n\nFeature list here.",
            "total_cost_usd": 0.45,
            "is_error": False,
        }

        text, cost = fetch_prd("notion-123", model="sonnet", log_dir=log_dir)
        assert "My PRD" in text
        assert cost == 0.45
        assert (log_dir / "prd.md").exists()

    @patch("morningstar.engine._run_claude")
    def test_raises_on_error(self, mock_claude: MagicMock, log_dir: Path) -> None:
        mock_claude.return_value = {
            "result": "",
            "total_cost_usd": 0,
            "is_error": True,
        }

        with pytest.raises(RuntimeError, match="Failed to fetch PRD"):
            fetch_prd("bad-url", model="sonnet", log_dir=log_dir)

        assert (log_dir / "prd-error.json").exists()

    @patch("morningstar.engine._run_claude")
    def test_uses_read_only_tools(self, mock_claude: MagicMock, log_dir: Path) -> None:
        mock_claude.return_value = {
            "result": "PRD content",
            "total_cost_usd": 0.3,
            "is_error": False,
        }

        fetch_prd("url", model="sonnet", log_dir=log_dir)

        call_kwargs = mock_claude.call_args[1]
        assert call_kwargs["tools"] == "Read"


# ── generate_tasks ────────────────────────────────────────────


class TestGenerateTasks:
    @patch("morningstar.engine._run_claude")
    def test_returns_tasks_from_structured_output(
        self, mock_claude: MagicMock, tmp_repo: Path, log_dir: Path,
    ) -> None:
        mock_claude.return_value = {
            "structured_output": {
                "tasks": [
                    {"id": "task-1", "title": "First task", "description": "Do thing"},
                    {"id": "task-2", "title": "Second task", "description": "Do other"},
                ]
            },
            "total_cost_usd": 1.2,
            "is_error": False,
            "result": "",
        }

        tasks, cost = generate_tasks(
            "PRD text", repo_path=tmp_repo, model="sonnet", log_dir=log_dir,
        )
        assert len(tasks) == 2
        assert tasks[0]["id"] == "task-1"
        assert cost == 1.2

    @patch("morningstar.engine._run_claude")
    def test_falls_back_to_result_parsing(
        self, mock_claude: MagicMock, tmp_repo: Path, log_dir: Path,
    ) -> None:
        mock_claude.return_value = {
            "result": json.dumps({
                "tasks": [{"id": "fallback-1", "title": "Fallback", "description": "..."}]
            }),
            "total_cost_usd": 0.8,
            "is_error": False,
        }

        tasks, cost = generate_tasks(
            "PRD", repo_path=tmp_repo, model="sonnet", log_dir=log_dir,
        )
        assert len(tasks) == 1
        assert tasks[0]["id"] == "fallback-1"

    @patch("morningstar.engine._run_claude")
    def test_raises_on_empty_tasks(
        self, mock_claude: MagicMock, tmp_repo: Path, log_dir: Path,
    ) -> None:
        mock_claude.return_value = {
            "structured_output": {"tasks": []},
            "total_cost_usd": 0.5,
            "is_error": False,
            "result": "{}",
        }

        with pytest.raises(RuntimeError, match="Failed to generate task list"):
            generate_tasks("PRD", repo_path=tmp_repo, model="sonnet", log_dir=log_dir)

    @patch("morningstar.engine._run_claude")
    def test_sanitizes_task_ids(
        self, mock_claude: MagicMock, tmp_repo: Path, log_dir: Path,
    ) -> None:
        mock_claude.return_value = {
            "structured_output": {
                "tasks": [
                    {"id": "../../evil", "title": "Bad task", "description": "..."},
                ]
            },
            "total_cost_usd": 0.5,
            "is_error": False,
            "result": "",
        }

        tasks, _ = generate_tasks(
            "PRD", repo_path=tmp_repo, model="sonnet", log_dir=log_dir,
        )
        assert "/" not in tasks[0]["id"]
        assert ".." not in tasks[0]["id"]

    @patch("morningstar.engine._run_claude")
    def test_enforces_max_tasks(
        self, mock_claude: MagicMock, tmp_repo: Path, log_dir: Path,
    ) -> None:
        many_tasks = [
            {"id": f"task-{i}", "title": f"Task {i}", "description": "..."}
            for i in range(50)
        ]
        mock_claude.return_value = {
            "structured_output": {"tasks": many_tasks},
            "total_cost_usd": 1.0,
            "is_error": False,
            "result": "",
        }

        tasks, _ = generate_tasks(
            "PRD", repo_path=tmp_repo, model="sonnet", log_dir=log_dir, max_tasks=5,
        )
        assert len(tasks) == 5

    @patch("morningstar.engine._run_claude")
    def test_uses_read_only_tools(
        self, mock_claude: MagicMock, tmp_repo: Path, log_dir: Path,
    ) -> None:
        mock_claude.return_value = {
            "structured_output": {
                "tasks": [{"id": "t1", "title": "T", "description": "D"}]
            },
            "total_cost_usd": 0.5,
            "is_error": False,
            "result": "",
        }

        generate_tasks("PRD", repo_path=tmp_repo, model="sonnet", log_dir=log_dir)

        call_kwargs = mock_claude.call_args[1]
        assert "Write" not in call_kwargs["tools"]
        assert "Bash" not in call_kwargs["tools"]


# ── execute_task ──────────────────────────────────────────────


class TestExecuteTask:
    @patch("morningstar.engine._git_commit")
    @patch("morningstar.engine._run_claude")
    def test_returns_success_result(
        self, mock_claude: MagicMock, mock_git: MagicMock,
        tmp_repo: Path, log_dir: Path,
    ) -> None:
        mock_claude.return_value = {
            "result": "implemented",
            "total_cost_usd": 2.5,
            "is_error": False,
            "session_id": "sess-12345678",
        }

        result = execute_task(
            {"id": "test-task", "title": "Test", "description": "Do it"},
            repo_path=tmp_repo, model="sonnet", budget_per_task=5.0, log_dir=log_dir,
        )

        assert result.success is True
        assert result.cost == 2.5
        assert result.task_id == "test-task"
        mock_git.assert_called_once()

    @patch("morningstar.engine._git_commit")
    @patch("morningstar.engine._run_claude")
    def test_retries_on_error(
        self, mock_claude: MagicMock, mock_git: MagicMock,
        tmp_repo: Path, log_dir: Path,
    ) -> None:
        mock_claude.side_effect = [
            # First call fails
            {
                "result": "error",
                "total_cost_usd": 1.0,
                "is_error": True,
                "session_id": "sess-retry-12345678",
            },
            # Retry succeeds
            {
                "result": "fixed",
                "total_cost_usd": 2.0,
                "is_error": False,
                "session_id": "sess-retry-12345678",
            },
        ]

        result = execute_task(
            {"id": "retry-task", "title": "Retry", "description": "..."},
            repo_path=tmp_repo, model="sonnet", budget_per_task=5.0, log_dir=log_dir,
        )

        assert result.success is True
        assert result.cost == 3.0  # 1.0 + 2.0
        assert mock_claude.call_count == 2

    @patch("morningstar.engine._git_commit")
    @patch("morningstar.engine._run_claude")
    def test_no_retry_without_session_id(
        self, mock_claude: MagicMock, mock_git: MagicMock,
        tmp_repo: Path, log_dir: Path,
    ) -> None:
        mock_claude.return_value = {
            "result": "error",
            "total_cost_usd": 1.0,
            "is_error": True,
            "session_id": "",  # No session ID
        }

        result = execute_task(
            {"id": "no-retry", "title": "No Retry", "description": "..."},
            repo_path=tmp_repo, model="sonnet", budget_per_task=5.0, log_dir=log_dir,
        )

        assert result.success is False
        assert mock_claude.call_count == 1  # No retry

    @patch("morningstar.engine._git_commit")
    @patch("morningstar.engine._run_claude")
    def test_writes_task_log(
        self, mock_claude: MagicMock, mock_git: MagicMock,
        tmp_repo: Path, log_dir: Path,
    ) -> None:
        mock_claude.return_value = {
            "result": "done",
            "total_cost_usd": 1.0,
            "is_error": False,
            "session_id": "sess-log-12345678",
        }

        execute_task(
            {"id": "log-task", "title": "Log", "description": "..."},
            repo_path=tmp_repo, model="sonnet", budget_per_task=5.0, log_dir=log_dir,
        )

        assert (log_dir / "task-log-task.json").exists()


# ── _git_commit ───────────────────────────────────────────────


class TestGitCommit:
    @patch("morningstar.engine.subprocess.run")
    def test_skips_when_no_changes(self, mock_run: MagicMock, tmp_repo: Path) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr="",
        )

        _git_commit(tmp_repo, "title", "task-1")
        assert mock_run.call_count == 1  # Only status check

    @patch("morningstar.engine.subprocess.run")
    def test_commits_when_changes_exist(self, mock_run: MagicMock, tmp_repo: Path) -> None:
        mock_run.side_effect = [
            # git status --porcelain
            subprocess.CompletedProcess(args=[], returncode=0, stdout="M file.py\n", stderr=""),
            # git add
            subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
            # git commit
            subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
        ]

        _git_commit(tmp_repo, "my feature", "task-1")
        assert mock_run.call_count == 3

        # Check commit message
        commit_cmd = mock_run.call_args_list[2][0][0]
        assert "feat: my feature" in commit_cmd[-1]
        assert "MorningStar" in commit_cmd[-1]

    @patch("morningstar.engine.subprocess.run")
    def test_excludes_sensitive_files(self, mock_run: MagicMock, tmp_repo: Path) -> None:
        mock_run.side_effect = [
            subprocess.CompletedProcess(args=[], returncode=0, stdout="M file.py\n", stderr=""),
            subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
            subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
        ]

        _git_commit(tmp_repo, "title", "task-1")

        add_cmd = mock_run.call_args_list[1][0][0]
        assert ":!*.env" in add_cmd
        assert ":!*.pem" in add_cmd
        assert ":!*.key" in add_cmd
        assert ":!.agent-logs" in add_cmd

    @patch("morningstar.engine.subprocess.run")
    def test_handles_git_not_found(self, mock_run: MagicMock, tmp_repo: Path) -> None:
        mock_run.side_effect = FileNotFoundError("git not found")

        # Should not raise
        _git_commit(tmp_repo, "title", "task-1")


# ── Data types ────────────────────────────────────────────────


class TestDataTypes:
    def test_task_result_is_frozen(self) -> None:
        result = TaskResult(task_id="t1", title="T", success=True, cost=1.0)
        with pytest.raises(AttributeError):
            result.cost = 2.0  # type: ignore[misc]

    def test_run_state_is_mutable(self) -> None:
        state = RunState()
        state.completed += 1
        state.cost += 5.0
        assert state.completed == 1
        assert state.cost == 5.0

    def test_run_state_defaults(self) -> None:
        state = RunState()
        assert state.completed == 0
        assert state.failed == 0
        assert state.cost == 0.0
        assert state.tasks == []
