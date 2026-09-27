"""Offline Telegram flow through the native loader, policy, router and store.

The SDK transport and agent conversation are doubles. Authorization, trigger
decisions, event conversion, batching, dispatch, session keys, transcript I/O,
reply formatting and delivery are the production implementations.
"""

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import os
from pathlib import Path
import socket
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import yaml


def _message(text, *, user=111, group=False, chat=None, thread=None, reply=False):
    chat_id = chat if chat is not None else (-100 if group else user)
    mentions = []
    for name in ("@wing_bot", "@other_bot"):
        if name in text:
            mentions.append(SimpleNamespace(type="mention", offset=text.index(name), length=len(name)))
    return SimpleNamespace(
        message_id=42, text=text, caption=None, entities=mentions,
        caption_entities=[], message_thread_id=thread,
        is_topic_message=thread is not None,
        chat=SimpleNamespace(id=chat_id, type="supergroup" if group else "private",
                             title="Test group" if group else None,
                             full_name="Test owner", is_forum=thread is not None),
        from_user=SimpleNamespace(id=user, full_name="Test owner", first_name="Owner"),
        reply_to_message=(SimpleNamespace(from_user=SimpleNamespace(id=999),
                                         message_id=10, text="previous reply", caption=None,
                                         photo=[], video=None, voice=None, audio=None, document=None)
                          if reply else None),
        date=datetime.now(timezone.utc),
    )


@pytest.fixture
def native_flow(monkeypatch, tmp_path):
    # This opt-out uses the supported config path; discovery and its policy
    # reader still execute, but missing optional SDKs must not be installed.
    home = Path(os.environ["WING_HOME"])
    config_path = home / "config.yaml"
    config_path.write_text(yaml.safe_dump({
        "security": {"allow_lazy_installs": False},
        "model": {"default": "gpt-4o-mini", "provider": "custom",
                  "base_url": "http://127.0.0.1:1/v1", "context_length": 128000},
        "platform_toolsets": {"telegram": []},
        "display": {"streaming": False, "tool_progress": "off", "interim_messages": False},
        "memory": {"memory_enabled": False, "user_profile_enabled": False},
        "group_sessions_per_user": False,
        "thread_sessions_per_user": False,
        "unauthorized_dm_behavior": "ignore",
        "session_reset": {"mode": "none"},
        "telegram": {
            "enabled": True, "allow_from": ["111"],
            "group_allow_from": ["111", "222"], "allowed_chats": ["-100"],
            "require_mention": True, "exclusive_bot_mentions": True,
            "guest_mode": False, "observe_unmentioned_group_messages": False,
            "free_response_chats": [], "mention_patterns": [],
        },
    }))

    def no_network(*_args, **_kwargs):
        raise AssertionError("offline message-flow test attempted a network connection")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket.socket, "connect_ex", no_network)
    monkeypatch.setattr(socket, "getaddrinfo", no_network)
    from gateway.config import Platform, load_gateway_config
    import gateway.run as gateway_run
    from plugins.platforms.telegram.adapter import TelegramAdapter

    def model_catalog(url, **_kwargs):
        assert url == "https://openrouter.ai/api/v1/models"
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"data": [{
            "id": "gpt-4o-mini", "context_length": 128000,
            "top_provider": {"max_completion_tokens": 16384},
        }]})

    monkeypatch.setattr("agent.model_metadata.requests.get", model_catalog)

    # The production module caches this profile path on import. In a test
    # file each case has a new home; keep the cached path in that same home.
    monkeypatch.setattr(gateway_run, "_wing_home", home)
    config = load_gateway_config()
    config.sessions_dir = home / "sessions"
    runner = gateway_run.GatewayRunner(config)
    adapter = TelegramAdapter(config.platforms[Platform.TELEGRAM])
    adapter.config.extra["group_sessions_per_user"] = config.group_sessions_per_user
    adapter.config.extra["thread_sessions_per_user"] = config.thread_sessions_per_user
    bot = SimpleNamespace(
        id=999, username="wing_bot",
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=9001)),
        send_chat_action=AsyncMock(return_value=True),
        set_my_commands=AsyncMock(return_value=True),
        set_message_reaction=AsyncMock(return_value=True),
    )
    adapter._bot = bot
    adapter.set_message_handler(runner._handle_message)
    adapter.set_session_store(runner.session_store)
    runner.adapters[Platform.TELEGRAM] = adapter

    calls = []

    async def conversation_reply(**kwargs):
        calls.append(deepcopy(kwargs))
        reply = f"Reply {len(calls)}"
        new_messages = [
            {"role": "user", "content": kwargs["message"]},
            {"role": "assistant", "content": reply},
        ]
        # The native agent persists its new turns before returning; the
        # router intentionally skips duplicate writes when SQLite is live.
        # Fulfil that boundary contract using the actual temporary store.
        # This double does not certify the signer-gated native agent path.
        for message in new_messages:
            flow.runner.session_store.append_to_transcript(kwargs["session_id"], message)
        return {"final_response": reply, "messages": list(kwargs["history"]) + new_messages,
                "history_offset": len(kwargs["history"]), "tools": [],
                "last_prompt_tokens": 0, "api_calls": 1, "failed": False}

    monkeypatch.setattr(runner, "_run_agent", conversation_reply)
    flow = SimpleNamespace(runner=runner, adapter=adapter, bot=bot, calls=calls,
                           config=config, home=home)
    yield flow
    if runner._session_db is not None:
        runner._session_db.close()


async def _dispatch(flow, message):
    update = SimpleNamespace(update_id=1001, message=message, effective_message=message)
    await flow.adapter._handle_text_message(update, SimpleNamespace())
    # Await native debounce and then native background delivery rather than
    # directly calling a trigger predicate or the runner with a fabricated event.
    for _ in range(6):
        tasks = list(flow.adapter._pending_text_batch_tasks.values())
        tasks.extend(flow.adapter._background_tasks)
        if not tasks:
            break
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=10)
    assert not flow.adapter._pending_text_batch_tasks
    assert not flow.adapter._background_tasks
    assert not flow.adapter._active_sessions


def _conversation_roles(messages):
    return [m["role"] for m in messages if m["role"] in {"user", "assistant"}]


def _delivered_replies(flow):
    # The router may also emit native session notices. Check the actual
    # conversation replies and their destinations without treating notices
    # as extra model replies.
    return [call.kwargs for call in flow.bot.send_message.await_args_list
            if str(call.kwargs.get("text", "")).startswith("Reply ")]


@pytest.mark.asyncio
async def test_dm_turn_uses_native_authorization_storage_and_delivery(native_flow):
    flow = native_flow
    await _dispatch(flow, _message("first private question"))
    await _dispatch(flow, _message("second private question"))
    assert len(flow.calls) == 2
    assert flow.calls[0]["session_key"] == flow.calls[1]["session_key"]
    assert flow.calls[0]["session_id"] == flow.calls[1]["session_id"]
    assert flow.calls[0]["history"] == []
    assert _conversation_roles(flow.calls[1]["history"]) == ["user", "assistant"]
    transcript = flow.runner.session_store.load_transcript(flow.calls[0]["session_id"])
    assert _conversation_roles(transcript) == ["user", "assistant", "user", "assistant"]
    replies = _delivered_replies(flow)
    assert [reply["text"] for reply in replies] == ["Reply 1", "Reply 2"]
    assert all(reply["chat_id"] == 111 for reply in replies)


@pytest.mark.asyncio
@pytest.mark.parametrize("message", [
    _message("private question", user=333),
    _message("@wing_bot group question", user=333, group=True),
    _message("group chatter", group=True),
    _message("@other_bot group question", group=True),
    _message("@wing_bot different group", group=True, chat=-200),
])
async def test_unselected_or_unapproved_messages_do_not_start_model_turn(native_flow, message):
    await _dispatch(native_flow, message)
    assert native_flow.calls == []
    native_flow.bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_group_shares_authorized_turns_but_dm_and_topics_keep_histories(native_flow):
    flow = native_flow
    await _dispatch(flow, _message("private question"))
    await _dispatch(flow, _message("@wing_bot group question", group=True))
    await _dispatch(flow, _message("group followup", user=222, group=True, reply=True))
    await _dispatch(flow, _message("@wing_bot topic one", group=True, thread=7))
    await _dispatch(flow, _message("@wing_bot topic two", group=True, thread=8))
    assert len(flow.calls) == 5
    dm, group, followup, topic_one, topic_two = flow.calls
    assert group["session_key"] == followup["session_key"]
    assert group["session_id"] == followup["session_id"]
    assert _conversation_roles(followup["history"]) == ["user", "assistant"]
    assert len({call["session_id"] for call in [dm, group, topic_one, topic_two]}) == 4
    assert all(call["history"] == [] for call in [dm, group, topic_one, topic_two])
    replies = _delivered_replies(flow)
    assert [reply["text"] for reply in replies] == [f"Reply {i}" for i in range(1, 6)]
    assert [reply.get("message_thread_id") for reply in replies] == [None, None, None, 7, 8]


@pytest.mark.asyncio
async def test_new_session_store_recovers_private_transcript(native_flow):
    from gateway.session import SessionStore

    flow = native_flow
    await _dispatch(flow, _message("remember this local turn"))
    first = flow.calls[0]
    reopened = SessionStore(flow.config.sessions_dir, flow.config)
    session = reopened.get_or_create_session(first["source"])
    assert session.session_id == first["session_id"]
    assert _conversation_roles(reopened.load_transcript(session.session_id)) == ["user", "assistant"]
