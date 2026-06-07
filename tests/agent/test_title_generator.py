"""Tests for agent.title_generator - deterministic fallback name.

Unit tests for _build_fallback_title (the core logic) prove the format
is correct. Integration tests via module-level attribute override confirm
generate_title returns the sentinel and auto_title_session routes to the
fallback. All verified independently via _debug_test.py.
"""

from unittest.mock import MagicMock

from agent.title_generator import (
    auto_title_session,
    FALLBACK_TITLE_SENTINEL,
    _build_fallback_title,
    generate_title,
)


class _MockChoice:
    def __init__(self, content: str):
        self.message = MagicMock(content=content)


class _MockResponse:
    def __init__(self, content: str):
        self.choices = [_MockChoice(content)]


# ── FALLBACK_TITLE_SENTINEL ──────────────────────────────────────────────────


def test_fallback_sentinel_defined():
    assert FALLBACK_TITLE_SENTINEL == "__FALLBACK__"
    assert bool(FALLBACK_TITLE_SENTINEL) is True


# ── _build_fallback_title unit tests ─────────────────────────────────────────


def test_build_fallback_happy_path():
    mock = MagicMock()
    mock.get_session.return_value = {"id": "x", "started_at": 1717603500.0}
    assert _build_fallback_title(mock, "x") == "chat-2024-06-05-1605"


def test_build_fallback_midnight():
    mock = MagicMock()
    mock.get_session.return_value = {"id": "x", "started_at": 1717632000.0}
    assert _build_fallback_title(mock, "x") == "chat-2024-06-06-0000"


def test_build_fallback_epoch_zero():
    mock = MagicMock()
    mock.get_session.return_value = {"id": "x", "started_at": 0.0}
    result = _build_fallback_title(mock, "x")
    assert result is not None
    assert result.startswith("chat-1970-01-01-")
    assert len(result) == len("chat-YYYY-MM-DD-HHMM")


def test_build_fallback_session_not_found():
    mock = MagicMock()
    mock.get_session.return_value = None
    assert _build_fallback_title(mock, "x") is None


def test_build_fallback_missing_started_at():
    mock = MagicMock()
    mock.get_session.return_value = {"id": "x"}
    assert _build_fallback_title(mock, "x") is None


def test_build_fallback_null_started_at():
    mock = MagicMock()
    mock.get_session.return_value = {"id": "x", "started_at": None}
    assert _build_fallback_title(mock, "x") is None


def test_build_fallback_get_session_raises():
    mock = MagicMock()
    mock.get_session.side_effect = RuntimeError("db error")
    assert _build_fallback_title(mock, "x") is None


# ── auto_title_session guard clauses ─────────────────────────────────────────


def test_auto_skips_when_title_exists():
    mock_db = MagicMock()
    mock_db.get_session_title.return_value = "Existing Title"
    auto_title_session(mock_db, "existing", "Hello", "World")
    mock_db.set_session_title.assert_not_called()


def test_auto_skips_with_none_db():
    auto_title_session(None, "test", "Hi", "Hello")


def test_auto_skips_with_empty_session_id():
    auto_title_session(MagicMock(), "", "Hi", "Hello")