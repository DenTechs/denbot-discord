import discord
from bot.logger import logger
from bot.client import DiscordClient
from bot.config import Config
import asyncio
from bot.llm_router import get_llm_response
from bot.client import PROMPT_FILES

async def generate_forum_reply(thread: discord.Thread) -> str:
    """Generate a reply for forum posts using the configured LLM with tool support."""
    starter_message = await thread.fetch_message(thread.id)

    content = f"Forum post title: {thread.name}\n\n{starter_message.content}"
    messages_history = [{"role": "user", "content": content}]

    logger.debug("Fetched starter message for thread '%s'", thread.name)

    return await get_llm_response(messages_history, PROMPT_FILES["forumsystemprompt.txt"])

def setup(discord_client: DiscordClient):
    @discord_client.event
    async def on_thread_create(thread: discord.Thread):
        """Handle new forum post creation."""
        if not Config.FORUM_REPLIES_ENABLED:
            logger.debug("Forum reply skipped: feature disabled")
            return

        if not isinstance(thread.parent, discord.ForumChannel):
            logger.debug("Forum reply skipped: thread '%s' parent is not a ForumChannel", thread.name)
            return

        if thread.parent_id not in Config.ALLOWED_FORUM_CHANNELS:
            logger.debug("Forum reply skipped: channel %s not in allowed forum channels", thread.parent_id)
            return

        logger.info(f"New forum post created: {thread.name} in {thread.parent.name}")

        # Fetch starter message with retry logic to handle Discord cache delays
        starter_message = thread.starter_message
        if starter_message is None:
            logger.warning("Starter message not found for thread '%s', waiting and fetching from history", thread.name)
            await asyncio.sleep(3)  # Give Discord's cache time to populate

            message_count = 0
            async for msg in thread.history(limit=1, oldest_first=True):
                starter_message = msg
                message_count += 1
                break

            if starter_message is None:
                logger.error("Failed to fetch starter message for thread '%s' even after retry (found %d messages)",
                            thread.name, message_count)
            else:
                logger.debug("Successfully fetched starter message for thread '%s' from history", thread.name)
        else:
            logger.debug("Starter message found directly for thread '%s'", thread.name)

        # Process the starter message with comprehensive error handling
        try:
            if starter_message and not starter_message.author.bot:
                logger.debug("Generating forum reply for thread '%s' (author: %s)",
                            thread.name, starter_message.author.name)

                reply = await generate_forum_reply(thread)

                logger.debug("Sending new reply to thread '%s'", thread.name)
                await thread.send(reply)

                logger.info("Forum reply sent to thread '%s' in %s", thread.name, thread.parent.name)

            elif starter_message and starter_message.author.bot:
                logger.debug("Forum reply skipped: starter message from bot '%s' in thread '%s'",
                            starter_message.author.name, thread.name)
            else:
                logger.error("Forum reply failed: starter_message is None after fetch attempt for thread '%s'",
                            thread.name)

        except discord.errors.Forbidden as e:
            logger.error("Permission denied sending reply to thread '%s': %s", thread.name, e)
        except discord.errors.HTTPException as e:
            logger.error("Discord API error sending reply to thread '%s': %s", thread.name, e, exc_info=True)
        except Exception as e:
            logger.error("Unexpected error sending reply to thread '%s': %s", thread.name, e, exc_info=True)