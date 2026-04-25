"""Tests for input validation functions in engine.py."""

import pytest

from morningstar.engine import (
    ALLOWED_MODELS,
    _sanitize_task_id,
    _validate_session_id,
    validate_model,
    validate_slack_webhook,
)

# ── validate_model ────────────────────────────────────────────


class TestValidateModel:
    @pytest.mark.parametrize("model", sorted(ALLOWED_MODELS))
    def test_accepts_all_allowed_models(self, model: str) -> None:
        assert validate_model(model) == model

    def test_rejects_unknown_model(self) -> None:
        with pytest.raises(ValueError, match="Invalid model"):
            validate_model("gpt-4o")

    def test_rejects_empty_string(self) -> None:
        with pytest.raises(ValueError):
            validate_model("")

    def test_rejects_model_with_flags(self) -> None:
        with pytest.raises(ValueError):
            validate_model("sonnet --dangerously-skip-permissions")


# ── validate_slack_webhook ────────────────────────────────────


class TestValidateSlackWebhook:
    def test_accepts_valid_webhook(self) -> None:
        url = "https://hooks.slack.com/services/T123ABC/B456DEF/abcXYZ789"
        assert validate_slack_webhook(url) == url

    def test_rejects_http(self) -> None:
        with pytest.raises(ValueError, match="Slack webhook"):
            validate_slack_webhook("http://hooks.slack.com/services/T1/B2/abc")

    def test_rejects_aws_metadata_ssrf(self) -> None:
        with pytest.raises(ValueError):
            validate_slack_webhook("http://169.254.169.254/latest/meta-data/")

    def test_rejects_internal_network(self) -> None:
        with pytest.raises(ValueError):
            validate_slack_webhook("http://10.0.0.1/admin/reset")

    def test_rejects_random_url(self) -> None:
        with pytest.raises(ValueError):
            validate_slack_webhook("https://example.com/webhook")

    def test_rejects_empty(self) -> None:
        with pytest.raises(ValueError):
            validate_slack_webhook("")

    def test_rejects_file_url(self) -> None:
        with pytest.raises(ValueError):
            validate_slack_webhook("file:///etc/passwd")


# ── _sanitize_task_id ─────────────────────────────────────────


class TestSanitizeTaskId:
    def test_clean_id_passes_through(self) -> None:
        assert _sanitize_task_id("analytics-backend") == "analytics-backend"

    def test_allows_underscores(self) -> None:
        assert _sanitize_task_id("task_one") == "task_one"

    def test_strips_path_traversal(self) -> None:
        result = _sanitize_task_id("../../etc/passwd")
        assert "/" not in result
        assert ".." not in result

    def test_strips_special_chars(self) -> None:
        result = _sanitize_task_id("task;rm -rf /")
        assert ";" not in result
        assert " " not in result

    def test_truncates_to_64(self) -> None:
        long_id = "a" * 100
        assert len(_sanitize_task_id(long_id)) <= 64

    def test_empty_gets_fallback(self) -> None:
        result = _sanitize_task_id("")
        assert result.startswith("task-")

    def test_dot_prefix_gets_fallback(self) -> None:
        result = _sanitize_task_id(".hidden")
        assert not result.startswith(".")

    def test_result_is_string(self) -> None:
        assert isinstance(_sanitize_task_id("test"), str)


# ── _validate_session_id ──────────────────────────────────────


class TestValidateSessionId:
    def test_accepts_valid_uuid_like(self) -> None:
        sid = "abc123-def456-ghi789"
        assert _validate_session_id(sid) == sid

    def test_accepts_alphanumeric(self) -> None:
        sid = "a1b2c3d4e5f6g7h8"
        assert _validate_session_id(sid) == sid

    def test_rejects_empty(self) -> None:
        assert _validate_session_id("") is None

    def test_rejects_too_short(self) -> None:
        assert _validate_session_id("abc") is None

    def test_rejects_path_traversal(self) -> None:
        assert _validate_session_id("../../evil") is None

    def test_rejects_shell_injection(self) -> None:
        assert _validate_session_id("abc; rm -rf /") is None

    def test_rejects_too_long(self) -> None:
        assert _validate_session_id("a" * 200) is None

    def test_returns_none_not_false(self) -> None:
        result = _validate_session_id("bad!")
        assert result is None
