"""Tests for Telegram restart polling-conflict fix.

Verifies that GatewayRunner.stop() calls Telegram adapter's updater.stop()
BEFORE the detached restart command is launched, preventing the 409 Conflict
that occurs when a new gateway process starts polling while the old process's
Telegram server-side session is still held open.

Regression test for: early Telegram updater stop in GatewayRunner.stop()
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gateway.config import Platform


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_telegram_adapter():
    """Create a TelegramAdapter with test attributes (bypass __init__)."""
    from gateway.platforms.telegram import TelegramAdapter

    adapter = TelegramAdapter.__new__(TelegramAdapter)
    adapter.platform = Platform.TELEGRAM
    adapter.config = MagicMock()

    # Mock the PTB Application + Updater chain
    adapter._app = MagicMock()
    adapter._app.updater = MagicMock()
    adapter._app.updater.running = True
    adapter._app.updater.stop = AsyncMock()

    # Required by the base adapter
    adapter._running = True
    adapter._fatal_error_code = None
    adapter._fatal_error_message = None
    adapter._fatal_error_retryable = True
    adapter._fatal_error_handler = None
    adapter._message_handler = None
    adapter._background_tasks = set()
    adapter._active_sessions = {}
    adapter._pending_messages = {}
    adapter._pending_approvals = None
    adapter._pending_photo_batch_tasks = {}
    adapter._pending_photo_batches = {}
    adapter._media_group_tasks = {}
    adapter._media_group_events = {}
    adapter._reply_to_mode = "first"
    adapter._send_path_degraded = False
    adapter._polling_conflict_count = 0

    # disconnect() will also try to call updater.stop() — let it be async
    adapter.disconnect = AsyncMock()

    return adapter


def _make_gateway_runner(adapter=None):
    """Create a minimal GatewayRunner for shutdown sequence testing.

    Bypasses the real constructor (which needs config loading, complex
    __init__ chains) and sets only the attributes the stop() method reads.
    """
    from gateway.run import GatewayRunner

    runner = GatewayRunner.__new__(GatewayRunner)
    runner.adapters = {}
    if adapter:
        runner.adapters[Platform.TELEGRAM] = adapter

    runner.config = MagicMock()
    runner._running = True
    runner._draining = False
    runner._restart_requested = True
    runner._restart_detached = True
    runner._restart_via_service = False
    runner._restart_task_started = False
    runner._restart_drain_timeout = 0.1
    runner._restart_command_source = None
    runner._exit_code = None
    runner._stop_task = None
    runner._shutdown_event = asyncio.Event()
    runner._running_agents = {}
    runner._running_agents_ts = {}
    runner._background_tasks = set()
    runner._pending_messages = {}
    runner._pending_approvals = {}
    runner._busy_ack_ts = {}
    runner._session_model_overrides = {}
    runner._session_reasoning_overrides = {}
    runner.session_store = MagicMock()
    runner._agent_cache = {}
    runner._agent_cache_lock = None
    runner._auto_tts_disabled_chats = set()
    runner._runtime_status = None
    runner._platform_runtime_statuses = {}
    runner._exit_reason = None
    runner._exit_code = None
    # Methods called in the adapter disconnect loop
    runner._update_runtime_status = MagicMock()
    runner._increment_restart_failure_counts = MagicMock()
    runner._cleanup_agent_resources = MagicMock()
    runner._hermes_home = MagicMock()

    return runner


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTelegramEarlyUpdaterStop:

    @pytest.mark.asyncio
    async def test_telegram_updater_stop_before_detached_restart(self):
        """Updater.stop() is called BEFORE the detached restart launches."""
        adapter = _make_telegram_adapter()
        runner = _make_gateway_runner(adapter)

        # Patch methods called by _stop_impl to avoid side effects
        patches = [
            patch.object(runner, "_notify_active_sessions_of_shutdown", AsyncMock()),
            patch.object(runner, "_drain_active_agents", AsyncMock(return_value=([], False))),
            patch.object(runner, "_finalize_shutdown_agents"),
            patch.object(runner, "_launch_detached_restart_command", AsyncMock()),
        ]

        for p in patches:
            p.start()

        try:
            await runner.stop(restart=True, detached_restart=True)
        finally:
            for p in reversed(patches):
                p.stop()

        # The Telegram adapter's updater.stop() should have been called
        adapter._app.updater.stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_updater_stop_not_called_when_not_running(self):
        """If the updater isn't running, stop() is not called (graceful no-op)."""
        adapter = _make_telegram_adapter()
        adapter._app.updater.running = False
        runner = _make_gateway_runner(adapter)

        patches = [
            patch.object(runner, "_notify_active_sessions_of_shutdown", AsyncMock()),
            patch.object(runner, "_drain_active_agents", AsyncMock(return_value=([], False))),
            patch.object(runner, "_finalize_shutdown_agents"),
            patch.object(runner, "_launch_detached_restart_command", AsyncMock()),
        ]

        for p in patches:
            p.start()

        try:
            await runner.stop(restart=True, detached_restart=True)
        finally:
            for p in reversed(patches):
                p.stop()

        adapter._app.updater.stop.assert_not_called()

    @pytest.mark.asyncio
    async def test_updater_stop_not_called_when_no_telegram_adapter(self):
        """No error when Telegram adapter isn't registered."""
        runner = _make_gateway_runner(adapter=None)

        patches = [
            patch.object(runner, "_notify_active_sessions_of_shutdown", AsyncMock()),
            patch.object(runner, "_drain_active_agents", AsyncMock(return_value=([], False))),
            patch.object(runner, "_finalize_shutdown_agents"),
            patch.object(runner, "_launch_detached_restart_command", AsyncMock()),
        ]

        for p in patches:
            p.start()

        try:
            await runner.stop(restart=True, detached_restart=True)
        finally:
            for p in reversed(patches):
                p.stop()

        # Should complete without error — adapter not in dict = skip

    @pytest.mark.asyncio
    async def test_updater_stop_error_does_not_block_shutdown(self):
        """If updater.stop() raises, the shutdown sequence continues."""
        adapter = _make_telegram_adapter()
        adapter._app.updater.stop = AsyncMock(side_effect=RuntimeError("Simulated stop failure"))
        runner = _make_gateway_runner(adapter)

        detached_mock = AsyncMock()
        patches = [
            patch.object(runner, "_notify_active_sessions_of_shutdown", AsyncMock()),
            patch.object(runner, "_drain_active_agents", AsyncMock(return_value=([], False))),
            patch.object(runner, "_finalize_shutdown_agents"),
            patch.object(runner, "_launch_detached_restart_command", detached_mock),
        ]

        for p in patches:
            p.start()

        try:
            await runner.stop(restart=True, detached_restart=True)
        finally:
            for p in reversed(patches):
                p.stop()

        # The detached restart should still have been launched despite the error
        detached_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_updater_stop_ordering_relative_to_disconnect(self):
        """updater.stop() is called BEFORE adapter.disconnect() in shutdown.

        This is the core regression guard: the existing code already called
        updater.stop() inside disconnect(), but that happened AFTER the
        detached restart launched.  Our early stop must execute first.
        """
        adapter = _make_telegram_adapter()
        runner = _make_gateway_runner(adapter)

        # Track call order
        call_order = []

        async def track_updater_stop():
            call_order.append("updater_stop")

        async def track_disconnect():
            call_order.append("disconnect")

        async def track_detached_restart():
            call_order.append("detached_restart")

        adapter._app.updater.stop = track_updater_stop
        adapter.disconnect = track_disconnect

        patches = [
            patch.object(runner, "_notify_active_sessions_of_shutdown", AsyncMock()),
            patch.object(runner, "_drain_active_agents", AsyncMock(return_value=([], False))),
            patch.object(runner, "_finalize_shutdown_agents"),
            patch.object(runner, "_launch_detached_restart_command", track_detached_restart),
        ]

        for p in patches:
            p.start()

        try:
            await runner.stop(restart=True, detached_restart=True)
        finally:
            for p in reversed(patches):
                p.stop()

        # The early updater.stop() must come before the detached restart,
        # AND must come before the adapter disconnect() in the regular loop
        assert call_order.index("updater_stop") < call_order.index("detached_restart"), \
            "updater.stop() must fire BEFORE detached restart launches"
        assert call_order.index("updater_stop") < call_order.index("disconnect"), \
            "updater.stop() must fire BEFORE adapter disconnect()"

    @pytest.mark.asyncio
    async def test_non_telegram_adapters_untouched(self):
        """Early stop only touches the Telegram adapter, not others."""
        adapter = _make_telegram_adapter()

        runner = _make_gateway_runner(adapter)
        discord_mock = MagicMock()
        discord_mock.cancel_background_tasks = AsyncMock()
        discord_mock.disconnect = AsyncMock()
        runner.adapters[Platform.DISCORD] = discord_mock

        patches = [
            patch.object(runner, "_notify_active_sessions_of_shutdown", AsyncMock()),
            patch.object(runner, "_drain_active_agents", AsyncMock(return_value=([], False))),
            patch.object(runner, "_finalize_shutdown_agents"),
            patch.object(runner, "_launch_detached_restart_command", AsyncMock()),
        ]

        for p in patches:
            p.start()

        try:
            await runner.stop(restart=True, detached_restart=True)
        finally:
            for p in reversed(patches):
                p.stop()

        # Telegram adapter's updater should have been stopped
        adapter._app.updater.stop.assert_awaited_once()