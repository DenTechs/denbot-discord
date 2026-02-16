from bot.client import DiscordClient
import discord
from bot.config import Config
from bot.logger import logger
import bot.client as bot_client
from bot.llm_router import get_llm_response

async def gather_reply_chain(message: discord.Message, bot_user_id: int, max_depth: int = 20) -> list[dict]:
    """
    Walk up the reply chain and gather messages into a conversation list.

    Args:
        message: The starting message (most recent)
        bot_user_id: The bot's user ID to determine assistant vs user role
        max_depth: Maximum number of messages to fetch in the chain

    Returns:
        List of message dicts with 'role' and 'content' keys, ordered oldest first
    """
    chain = []
    current_msg = message
    depth = 0

    while current_msg and depth < max_depth:
        # Strip bot mention from content
        content = current_msg.content.replace(f"<@{bot_user_id}>", "").strip()

        if content:  # Only add non-empty messages
            role = "assistant" if current_msg.author.id == bot_user_id else "user"
            chain.append({"role": role, "content": content})

        # Try to fetch the parent message in the reply chain
        if current_msg.reference and current_msg.reference.message_id:
            try:
                current_msg = await current_msg.channel.fetch_message(current_msg.reference.message_id)
                depth += 1
            except discord.NotFound:
                logger.warning("Referenced message %s not found in chain", current_msg.reference.message_id)
                break
        else:
            break

    # Reverse to get chronological order (oldest first)
    chain.reverse()

    # Merge consecutive messages with the same role (Claude API requirement)
    merged = []
    for msg in chain:
        if merged and merged[-1]["role"] == msg["role"]:
            merged[-1]["content"] += "\n\n" + msg["content"]
        else:
            merged.append(msg)

    return merged

def setup(discord_client: DiscordClient):
    @discord_client.event
    async def on_message(message: discord.Message):
        """Handle messages that @mention the bot, with reply context if present."""
        if message.author.bot:
            return

        if Config.REGEX_REPLIES_ENABLED:
            # Check for auto-reply regex matches
            logger.debug("Checking auto-reply patterns. Pattern count: %d, Message content: '%s'", len(bot_client.AUTO_REPLY_COMPILED), message.content)
            for pattern in bot_client.AUTO_REPLY_COMPILED:
                logger.debug("Testing pattern '%s' against message", pattern.pattern)
                if pattern.search(message.content):
                    logger.info("Auto-reply triggered: regex '%s' matched message from %s: %s", pattern.pattern, message.author.name, message.content)
                    messages = [{"role": "user", "content": message.content}]
                    system_prompt = bot_client.PROMPT_FILES["faqsystemprompt.txt"]
                    async with message.channel.typing():
                        reply = await get_llm_response(messages, system_prompt, channel=message.channel)
                    await message.reply(reply)
                    return

        if not discord_client.user or discord_client.user not in message.mentions:
            return

        has_allowed_role = False
        if message.guild:
            member = message.guild.get_member(message.author.id)
            if member:
                member_role_ids = [role.id for role in member.roles]
                logger.debug("on_message role check for user %s: member_role_ids=%s (types: %s), allowed_roles=%s (types: %s)",
                            message.author.name, member_role_ids, [type(r).__name__ for r in member_role_ids],
                            Config.ALLOWED_ROLES, [type(r).__name__ for r in Config.ALLOWED_ROLES])
                if any(role.id in Config.ALLOWED_ROLES for role in member.roles):
                    has_allowed_role = True
                    logger.debug("on_message: user %s has allowed role", message.author.name)
                else:
                    logger.debug("on_message: no matching roles for user %s. Member roles: %s, Allowed roles: %s",
                                message.author.name, member_role_ids, Config.ALLOWED_ROLES)
            else:
                logger.debug("on_message: could not get member object for user %s (id=%s)", message.author.name, message.author.id)

        if not has_allowed_role and message.channel.id not in Config.ALLOWED_CHANNELS and message.channel.id not in Config.ALLOWED_FORUM_CHANNELS:
            # Check if it's a thread inside an allowed forum channel
            if isinstance(message.channel, discord.Thread) and message.channel.parent_id in Config.ALLOWED_FORUM_CHANNELS:
                pass
            elif message.author.id not in Config.OVERRIDE_USERS:
                logger.debug("Mention ignored: user %s lacks permissions in channel %s", message.author.name, message.channel.id)
                return

        # Gather the full reply chain as a conversation
        messages = await gather_reply_chain(message, discord_client.user.id)

        # Ensure conversation starts with user role (Claude API requirement)
        if messages and messages[0]["role"] != "user":
            messages = messages[1:]  # Skip leading assistant messages

        # Fallback if chain is empty
        if not messages:
            mention_content = message.content.replace(f"<@{discord_client.user.id}>", "").strip()
            messages = [{"role": "user", "content": mention_content}]

        logger.info(f"User {message.author.name} mentioned bot. Conversation chain has {len(messages)} messages")
        logger.debug(f"Conversation chain: {messages}")

        system_prompt = bot_client.PROMPT_FILES["faqsystemprompt.txt"]

        async with message.channel.typing():
            reply = await get_llm_response(messages, system_prompt, channel=message.channel)
        await message.reply(reply)