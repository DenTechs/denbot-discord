from bot.client import DiscordClient
import discord
from bot.config import Config
from bot.logger import logger
import bot.client as bot_client
from bot.llm_router import get_llm_response

async def gather_reply_chain(message: discord.Message, bot_user_id: int, max_depth: int = 20) -> list[dict]:
    """Walk up the reply chain and return conversation list ordered oldest first."""
    chain = []
    current_msg = message
    depth = 0

    while current_msg and depth < max_depth:
        content = current_msg.content.replace(f"<@{bot_user_id}>", "").strip()

        if content:
            role = "assistant" if current_msg.author.id == bot_user_id else "user"
            chain.append({"role": role, "content": content})

        if current_msg.reference and current_msg.reference.message_id:
            try:
                current_msg = await current_msg.channel.fetch_message(current_msg.reference.message_id)
                depth += 1
            except discord.NotFound:
                logger.warning("Referenced message %s not found in chain", current_msg.reference.message_id)
                break
        else:
            break

    chain.reverse()

    # Merge consecutive messages with the same role (Claude API requirement)
    merged = []
    for msg in chain:
        if merged and merged[-1]["role"] == msg["role"]:
            merged[-1]["content"] += "\n\n" + msg["content"]
        else:
            merged.append(msg)

    return merged


async def send_llm_reply(message: discord.Message, messages: list[dict], system_prompt: str):
    """Get LLM response and reply to the message."""
    async with message.channel.typing():
        reply = await get_llm_response(messages, system_prompt, channel=message.channel, discord_message=message)
    await message.reply(reply)


async def handle_regex_replies(message: discord.Message) -> bool:
    """Check regex patterns and reply via LLM if matched. Returns True if handled."""
    if not Config.REGEX_REPLIES_ENABLED:
        return False

    for pattern in bot_client.AUTO_REPLY_COMPILED:
        if pattern.search(message.content):
            logger.info("Auto-reply triggered: regex '%s' matched message from %s", pattern.pattern, message.author.name)
            messages = [{"role": "user", "content": message.content}]
            await send_llm_reply(message, messages, bot_client.PROMPT_FILES["mainsystemprompt.txt"])
            return True

    return False


def has_permission(message: discord.Message) -> bool:
    """Check if the user has permission to interact with the bot."""
    if message.guild:
        member = message.guild.get_member(message.author.id)
        if member and any(role.id in Config.ALLOWED_ROLES for role in member.roles):
            return True

    if message.guild and message.guild.id in Config.AUTHORIZED_SERVERS:
        return True

    if message.channel.id in Config.ALLOWED_CHANNELS or message.channel.id in Config.ALLOWED_FORUM_CHANNELS:
        return True

    if isinstance(message.channel, discord.Thread) and message.channel.parent_id in Config.ALLOWED_FORUM_CHANNELS:
        return True

    if message.author.id in Config.OVERRIDE_USERS:
        return True

    logger.debug("Mention ignored: user %s lacks permissions in channel %s", message.author.name, message.channel.id)
    return False


def setup(discord_client: DiscordClient):
    @discord_client.event
    async def on_message(message: discord.Message):
        """Handle messages that @mention the bot, with reply context if present."""
        if message.author.bot:
            return

        if await handle_regex_replies(message):
            return

        if not discord_client.user or discord_client.user not in message.mentions:
            return

        if not has_permission(message):
            return

        messages = await gather_reply_chain(message, discord_client.user.id)

        if messages and messages[0]["role"] != "user":
            messages = messages[1:]

        if not messages:
            content = message.content.replace(f"<@{discord_client.user.id}>", "").strip()
            messages = [{"role": "user", "content": content}]

        logger.info("User %s mentioned bot. Chain: %d messages", message.author.name, len(messages))
        logger.debug("Conversation chain: %s", messages)

        await send_llm_reply(message, messages, bot_client.PROMPT_FILES["mainsystemprompt.txt"])
