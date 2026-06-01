from __future__ import annotations

from collections import OrderedDict
from contextvars import ContextVar
from copy import deepcopy
from typing import Any

_MAX_CACHED_ASSISTANT_MESSAGES = 200

_last_openai_assistant_message: ContextVar[dict[str, Any] | None] = ContextVar(
    "last_openai_assistant_message",
    default=None,
)
_discord_assistant_messages: OrderedDict[int, dict[str, Any]] = OrderedDict()


def set_last_openai_assistant_message(message: dict[str, Any] | None) -> None:
    _last_openai_assistant_message.set(deepcopy(message) if message else None)


def pop_last_openai_assistant_message() -> dict[str, Any] | None:
    message = _last_openai_assistant_message.get()
    _last_openai_assistant_message.set(None)
    return deepcopy(message) if message else None


def store_discord_assistant_message(message_id: int, assistant_message: dict[str, Any]) -> None:
    _discord_assistant_messages[message_id] = deepcopy(assistant_message)
    _discord_assistant_messages.move_to_end(message_id)

    while len(_discord_assistant_messages) > _MAX_CACHED_ASSISTANT_MESSAGES:
        _discord_assistant_messages.popitem(last=False)


def get_discord_assistant_message(message_id: int) -> dict[str, Any] | None:
    message = _discord_assistant_messages.get(message_id)
    return deepcopy(message) if message else None
