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
    channel: Optional[discord.abc.Messageable] = None
) -> str:
    """
    Route LLM requests to the appropriate provider based on LLM_PROVIDER config.

    Args:
        messages: List of message dicts with 'role' and 'content' keys
        system_prompt: The system prompt to use
        channel: Optional Discord channel for typing indicators

    Returns:
        The response text from the LLM

    Raises:
        ValueError: If LLM_PROVIDER is not recognized
    """
    provider = Config.LLM_PROVIDER.lower()
    logger.debug(f"Routing LLM request to provider: {provider}")

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
