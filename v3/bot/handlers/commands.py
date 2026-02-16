import logging
from bot.logger import logger
from bot.checks import channel_check
from bot.client import DiscordClient
import discord
from bot.llm_router import get_llm_response
import bot.client as bot_client

def setup(discord_client: DiscordClient):

    async def handle_ask_denbot(interaction: discord.Interaction, newUserMessage: discord.Message, additional_context: str = "") -> str:
        content = newUserMessage.content
        if additional_context:
            content = f"Additional context: {additional_context}\n\n{content}"
        messages = [{"role": "user", "content": content}]
        system_prompt =  bot_client.PROMPT_FILES["faqsystemprompt.txt"]
        return await get_llm_response(messages, system_prompt)

    class AskFAQModal(discord.ui.Modal, title="Ask FAQ"):
        """Modal for Ask FAQ with optional additional context."""

        additional_context = discord.ui.TextInput(
            label="Additional Context",
            placeholder="Provide any extra context or clarification (optional)...",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=1000
        )

        def __init__(self, message: discord.Message):
            super().__init__()
            self.target_message = message

        async def on_submit(self, interaction: discord.Interaction):
            logger.info(f"""FAQ modal submitted by user {interaction.user.name} with message: ({self.target_message.content}) and additional context: ({self.additional_context.value})""")
            await interaction.response.defer(thinking=True)

            reply = await handle_ask_denbot(
                interaction,
                self.target_message,
                self.additional_context.value
            )

            await interaction.followup.send(reply)

    @discord_client.tree.context_menu(name="Ask DenBot")
    @discord.app_commands.allowed_installs(guilds=True, users=True)
    @discord.app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @discord.app_commands.check(channel_check)
    async def ask_BubblesBot(interaction: discord.Interaction, message: discord.Message):
        logger.info(f"User {interaction.user.name} used Ask DenBot")
        await interaction.response.send_modal(AskFAQModal(message))

    @ask_BubblesBot.error
    async def ask_BubblesBot_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
        if isinstance(error, discord.app_commands.CheckFailure):
            logger.warning("Permission denied for user %s in channel %s (Ask DenBot)", interaction.user.name, interaction.channel_id)
            if interaction.response.is_done():
                await interaction.followup.send("You don't have permission to use this command here.", ephemeral=True)
            else:
                await interaction.response.send_message("You don't have permission to use this command here.", ephemeral=True)
        else:
            logger.error(f"Unexpected error in Ask FAQ: {error}", exc_info=True)
            if interaction.response.is_done():
                await interaction.followup.send("Something went wrong. Please try again later.", ephemeral=True)
            else:
                await interaction.response.send_message("Something went wrong. Please try again later.", ephemeral=True)
