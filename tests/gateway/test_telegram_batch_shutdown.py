"""Offline contracts for Telegram batch ownership and adapter shutdown.

These tests import the real adapter and run real asyncio tasks. Telegram and
model services are never contacted; handle_message is the delivery boundary.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import MessageEvent, MessageType
from gateway.session import SessionSource
from plugins.platforms.telegram.adapter import TelegramAdapter


def _adapter():
    adapter = TelegramAdapter(PlatformConfig(enabled=True, token="offline-test-token"))
    adapter.handle_message = AsyncMock()
    adapter._set_status_indicator = AsyncMock()
    adapter._text_batch_delay_seconds = 60
    adapter._TEXT_BATCH_FAST_DELAY_S = 60
    adapter._media_batch_delay_seconds = 60
    adapter.MEDIA_GROUP_WAIT_SECONDS = 60
    return adapter


def _event(text="queued message", message_type=MessageType.TEXT):
    return MessageEvent(
        text=text,
        message_type=message_type,
        source=SessionSource(platform=Platform.TELEGRAM, chat_id="123", chat_type="dm"),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["text", "photo", "album"])
async def test_disconnect_finishes_all_buffered_ingress_tasks(kind):
    """Returning from disconnect must leave no timer able to dispatch a turn."""
    adapter = _adapter()
    if kind == "text":
        adapter._enqueue_text_event(_event())
        tasks = adapter._pending_text_batch_tasks
        pending = adapter._pending_text_batches
    elif kind == "photo":
        adapter._enqueue_photo_event("photo", _event(message_type=MessageType.PHOTO))
        tasks = adapter._pending_photo_batch_tasks
        pending = adapter._pending_photo_batches
    else:
        await adapter._queue_media_group_event("album", _event(message_type=MessageType.PHOTO))
        tasks = adapter._media_group_tasks
        pending = adapter._media_group_events
    owned_tasks = list(tasks.values())
    try:
        await asyncio.sleep(0)  # enter the real debounce coroutine
        await adapter.disconnect()
        assert not tasks
        assert not pending
        assert all(task.done() for task in owned_tasks)
        adapter.handle_message.assert_not_awaited()
    finally:
        for task in owned_tasks:
            task.cancel()
        await asyncio.gather(*owned_tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_cancelled_album_timer_cannot_unregister_its_replacement():
    """Debouncing preserves ownership so disconnect can still drain the timer."""
    adapter = _adapter()
    await adapter._queue_media_group_event("album", _event("first"))
    prior = adapter._media_group_tasks["album"]
    await asyncio.sleep(0)
    await adapter._queue_media_group_event("album", _event("second"))
    replacement = adapter._media_group_tasks["album"]
    try:
        await asyncio.gather(prior, return_exceptions=True)
        assert adapter._media_group_tasks.get("album") is replacement
        assert adapter._media_group_events["album"].text == "first\n\nsecond"
        await adapter.disconnect()
        assert replacement.done()
        adapter.handle_message.assert_not_awaited()
    finally:
        replacement.cancel()
        await asyncio.gather(replacement, return_exceptions=True)


@pytest.mark.asyncio
async def test_disconnect_clears_all_batch_types_together():
    """Mixed input bursts have one shutdown barrier, not per-type leftovers."""
    adapter = _adapter()
    adapter._enqueue_text_event(_event())
    adapter._enqueue_photo_event("photo", _event(message_type=MessageType.PHOTO))
    await adapter._queue_media_group_event("album", _event(message_type=MessageType.PHOTO))
    task_maps = (
        adapter._pending_text_batch_tasks,
        adapter._pending_photo_batch_tasks,
        adapter._media_group_tasks,
    )
    tasks = [task for task_map in task_maps for task in task_map.values()]
    try:
        await asyncio.sleep(0)
        await adapter.disconnect()
        assert all(not task_map for task_map in task_maps)
        assert all(task.done() for task in tasks)
        assert not adapter._pending_text_batches
        assert not adapter._pending_photo_batches
        assert not adapter._media_group_events
        adapter.handle_message.assert_not_awaited()
        # Repeated shutdown should remain harmless.
        await adapter.disconnect()
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_disconnect_drains_updates_queued_while_application_stops():
    """An update already owned by the SDK can finish during app.stop()."""
    adapter = _adapter()
    late_tasks = []

    async def stop_application():
        adapter._enqueue_text_event(_event("last queued SDK update"))
        late_tasks.extend(adapter._pending_text_batch_tasks.values())
        await asyncio.sleep(0)

    adapter._app = SimpleNamespace(
        updater=SimpleNamespace(running=False),
        running=True,
        stop=stop_application,
        shutdown=AsyncMock(),
    )
    try:
        await adapter.disconnect()
        assert len(late_tasks) == 1
        assert late_tasks[0].done()
        assert not adapter._pending_text_batches
        assert not adapter._pending_text_batch_tasks
        adapter.handle_message.assert_not_awaited()
    finally:
        for task in late_tasks:
            task.cancel()
        await asyncio.gather(*late_tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_shutdown_from_a_dispatch_does_not_cancel_or_await_itself():
    """A shutdown requested inside delivery must not create a self-await cycle."""
    adapter = _adapter()
    adapter._text_batch_delay_seconds = 0

    async def shutdown_from_delivery(event):
        await adapter.disconnect()

    adapter.handle_message = AsyncMock(side_effect=shutdown_from_delivery)
    adapter._enqueue_text_event(_event())
    task = next(iter(adapter._pending_text_batch_tasks.values()))
    await asyncio.wait_for(task, timeout=2)
    assert not task.cancelled()
    assert not adapter._pending_text_batch_tasks
    adapter.handle_message.assert_awaited_once()
