import json
from datetime import datetime, timezone
from typing import Any, Optional

import discord

from bot.config import Config
from bot.logger import logger

try:
    from hindsight_client import Hindsight
except ImportError:
    Hindsight = None


MEMORY_PREAMBLE = (
    "Relevant memories from past conversations follow. Prioritize recent memories "
    "when they conflict. Use only memories that are directly useful for this reply; "
    "ignore the rest."
)

_client = None


def is_enabled() -> bool:
    return Config.HINDSIGHT_ENABLED and Hindsight is not None


def _get_client():
    global _client
    if not Config.HINDSIGHT_ENABLED:
        return None
    if Hindsight is None:
        logger.warning("Hindsight memory is enabled but hindsight-client is not installed")
        return None
    if _client is None:
        _client = Hindsight(
            base_url=Config.HINDSIGHT_API_URL,
            api_key=Config.HINDSIGHT_API_KEY,
        )
    return _client


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(str(block.get("text", "")))
                elif block.get("type"):
                    parts.append(f"[{block.get('type')} content]")
            else:
                parts.append(str(block))
        return "\n".join(part for part in parts if part)
    return str(content)


def messages_to_text(messages: list[dict[str, Any]]) -> str:
    lines = []
    for message in messages:
        role = message.get("role", "unknown")
        content = _content_to_text(message.get("content", ""))
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


def get_recall_query(messages: list[dict[str, Any]]) -> str:
    if not messages:
        return ""
    last_user = next((msg for msg in reversed(messages) if msg.get("role") == "user"), messages[-1])
    query = _content_to_text(last_user.get("content", ""))
    if len(query) > 1200:
        return query[-1200:]
    return query


def build_discord_context(discord_message: Optional[discord.Message]) -> dict[str, Any]:
    if discord_message is None:
        return {}

    guild = discord_message.guild
    return {
        "discord_user_id": str(discord_message.author.id),
        "discord_user_name": discord_message.author.display_name,
        "discord_guild_id": str(guild.id) if guild else None,
        "discord_guild_name": guild.name if guild else None,
        "discord_channel_id": str(discord_message.channel.id),
        "discord_message_id": str(discord_message.id),
        "discord_created_at": discord_message.created_at.isoformat(),
    }


def _memory_text(memory: Any) -> str:
    if isinstance(memory, dict):
        text = memory.get("text") or memory.get("content") or memory.get("memory")
        memory_type = memory.get("type")
    else:
        text = getattr(memory, "text", None) or getattr(memory, "content", None) or getattr(memory, "memory", None)
        memory_type = getattr(memory, "type", None)

    if not text:
        return ""
    if memory_type:
        return f"[{memory_type}] {text}"
    return str(text)


def format_recall_result(result: Any) -> str:
    if result is None:
        return ""

    results = None
    if isinstance(result, dict):
        results = result.get("results") or result.get("memories")
    else:
        results = getattr(result, "results", None) or getattr(result, "memories", None)

    if results:
        memories = [_memory_text(memory) for memory in results]
        return "\n".join(memory for memory in memories if memory)

    text = getattr(result, "text", None) if not isinstance(result, dict) else result.get("text")
    if text:
        return str(text)

    if isinstance(result, str):
        return result

    return str(result)


async def recall(query: str, max_tokens: Optional[int] = None) -> str:
    if not Config.HINDSIGHT_RECALL_ENABLED:
        return ""

    client = _get_client()
    if client is None:
        return ""

    clean_query = (query or "").strip()
    if not clean_query:
        return ""

    kwargs = {
        "bank_id": Config.HINDSIGHT_BANK_ID,
        "query": clean_query,
    }

    try:
        try:
            result = await client.arecall(
                **kwargs,
                budget=Config.HINDSIGHT_RECALL_BUDGET,
                max_tokens=max_tokens,
            )
        except TypeError:
            try:
                result = await client.arecall(**kwargs, budget=Config.HINDSIGHT_RECALL_BUDGET)
            except TypeError:
                result = await client.arecall(**kwargs)
        formatted = format_recall_result(result)
        if formatted:
            logger.info("Hindsight recalled memory context (%d chars)", len(formatted))
        return formatted
    except Exception as e:
        logger.error("Hindsight recall failed: %s", e, exc_info=True)
        return ""


async def reflect(query: str) -> str:
    client = _get_client()
    if client is None:
        return "Hindsight memory is not configured."

    clean_query = (query or "").strip()
    if not clean_query:
        return "Error: query is required."

    try:
        try:
            result = await client.areflect(
                bank_id=Config.HINDSIGHT_BANK_ID,
                query=clean_query,
                budget=Config.HINDSIGHT_RECALL_BUDGET,
            )
        except TypeError:
            result = await client.areflect(bank_id=Config.HINDSIGHT_BANK_ID, query=clean_query)
        return format_recall_result(result) or str(result)
    except Exception as e:
        logger.error("Hindsight reflect failed: %s", e, exc_info=True)
        return f"Error reflecting on Hindsight memory: {e}"


async def retain(content: str, context: str = "", metadata: Optional[dict[str, Any]] = None) -> str:
    if not Config.HINDSIGHT_RETAIN_ENABLED:
        return "Hindsight retain is disabled."

    client = _get_client()
    if client is None:
        return "Hindsight memory is not configured."

    clean_content = (content or "").strip()
    if not clean_content:
        return "Error: content is required."

    clean_metadata = {k: str(v) for k, v in (metadata or {}).items() if v is not None}
    retain_context = context.strip() if context else ""
    if clean_metadata:
        metadata_text = json.dumps(clean_metadata, ensure_ascii=False)
        retain_context = f"{retain_context}\nmetadata: {metadata_text}".strip()

    try:
        kwargs = {
            "bank_id": Config.HINDSIGHT_BANK_ID,
            "content": clean_content,
            "timestamp": datetime.now(timezone.utc),
        }
        if retain_context:
            kwargs["context"] = retain_context
        if clean_metadata:
            kwargs["metadata"] = clean_metadata

        try:
            await client.aretain(**kwargs)
        except TypeError:
            kwargs.pop("metadata", None)
            try:
                await client.aretain(**kwargs)
            except TypeError:
                kwargs.pop("timestamp", None)
                await client.aretain(**kwargs)

        logger.info("Retained Hindsight memory (%d chars)", len(clean_content))
        return "Stored in Hindsight memory."
    except Exception as e:
        logger.error("Hindsight retain failed: %s", e, exc_info=True)
        return f"Error storing Hindsight memory: {e}"


def build_memory_prompt(memories: str) -> str:
    clean_memories = (memories or "").strip()
    if not clean_memories:
        return ""
    return f"{MEMORY_PREAMBLE}\n\n{clean_memories}"
