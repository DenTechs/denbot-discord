"""
LLM Router - Routes requests to appropriate LLM provider based on configuration.
"""
from bot.config import Config
from bot.logger import logger
from typing import Optional
import discord


async def get_llm_response(
    messages: list,
    system_prompt: str,
    channel: Optional[discord.abc.Messageable] = None,
    discord_message: Optional[discord.Message] = None
) -> str:
    """
    Route LLM requests to the appropriate provider based on LLM_PROVIDER config.

    Args:
        messages: List of message dicts with 'role' and 'content' keys
        system_prompt: The system prompt to use
        channel: Optional Discord channel for typing indicators
        discord_message: Optional Discord message for processing attachments (images)

    Returns:
        The response text from the LLM

    Raises:
        ValueError: If LLM_PROVIDER is not recognized
    """
    provider = Config.LLM_PROVIDER.lower()
    logger.debug(f"Routing LLM request to provider: {provider}")

    # Process images for Claude provider only
    if provider == "anthropic" and discord_message and discord_message.attachments:
        from bot.image_utils import is_image_attachment, process_discord_attachment

        # Filter for image attachments
        image_attachments = [att for att in discord_message.attachments if is_image_attachment(att)]

        if image_attachments:
            logger.info(f"Processing {len(image_attachments)} image(s) for Claude")

            # Transform the last user message to multimodal format
            if messages and messages[-1]["role"] == "user":
                last_message = messages[-1]
                text_content = last_message["content"]

                # Build content array: text first, then images
                content_blocks = [{"type": "text", "text": text_content}]

                # Process each image attachment
                for attachment in image_attachments:
                    image_block = await process_discord_attachment(
                        attachment,
                        Config.IMAGE_MAX_DIMENSIONS
                    )
                    if image_block:
                        content_blocks.append(image_block)
                        logger.debug(f"Added image: {attachment.filename}")
                    else:
                        logger.warning(f"Failed to process image: {attachment.filename}")

                # Replace string content with content array
                messages[-1]["content"] = content_blocks

    if provider == "anthropic":
        from claude.response import generate_claude_response
        return await generate_claude_response(messages, system_prompt, channel)

    elif provider == "openai":
        from local_llm.response import generate_openai_response
        return await generate_openai_response(messages, system_prompt, channel)

    else:
        error_msg = f"Unknown LLM_PROVIDER: {Config.LLM_PROVIDER}. Must be 'anthropic' or 'openai'"
        logger.error(error_msg)
        raise ValueError(error_msg)
