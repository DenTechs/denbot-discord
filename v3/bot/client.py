from bot.config import Config
import logging
from bot.logger import logger
import discord
import re

class DiscordClient(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        # A CommandTree is a special type that holds all the application command
        # state required to make it work. This is a separate class because it
        # allows all the extra state to be opt-in.
        # Whenever you want to work with application commands, your tree is used
        # to store and work with them.
        # Note: When using commands.Bot instead of discord.Client, the bot will
        # maintain its own tree instead.
        self.tree = discord.app_commands.CommandTree(self)

    # In this basic example, we just synchronize the app commands to one guild.
    # Instead of specifying a guild to every command, we copy over our global commands instead.
    # By doing so, we don't have to wait up to an hour until they are shown to the end-user.
    async def setup_hook(self):
        # Sync commands globally for user installs to work in DMs
        # DO NOT SYNC THE SAME COMMAND GLOBALLY AND COPIED TO A GUILD
        await self.tree.sync()

        # Start GitHub prompt refresh task
        from bot import github_prompts
        import bot.client as client_module
        github_prompts.start_prompt_refresh(client_module)

intents = discord.Intents.default()
intents.message_content = True
discord_client = DiscordClient(intents=intents)

PROMPT_FILES = {
    "forumsystemprompt.txt": "",
    "mainsystemprompt.txt": "",
    "autoreplyregex.txt": "",
}

AUTO_REPLY_COMPILED = []

@discord_client.event
async def on_ready():
    logger.info("Bot ready as %s (guilds: %d)", discord_client.user, len(discord_client.guilds))

def create_client():
    from bot.handlers import commands, forums, messages

    # Load prompts from disk at startup
    for filename in PROMPT_FILES:
        try:
            with open(f"prompts/{filename}", "r") as file:
                PROMPT_FILES[filename] = file.read()
            logger.info("Loaded %s", filename)
        except Exception as e:
            logger.error("Failed to load %s: %s", filename, e)
            raise

    """Compile regex patterns from autoreplyregex.txt content."""
    global AUTO_REPLY_COMPILED
    lines = [line.strip() for line in PROMPT_FILES["autoreplyregex.txt"].splitlines() if line.strip()]
    AUTO_REPLY_COMPILED = [re.compile(pattern, re.IGNORECASE) for pattern in lines]
    logger.debug("Compiled %d auto-reply regex patterns", len(AUTO_REPLY_COMPILED))

    commands.setup(discord_client)
    forums.setup(discord_client)
    messages.setup(discord_client)

    logger.info("Created Client")
    discord_client.run(Config.BOT_API_KEY)