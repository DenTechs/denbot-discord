import discord
from bot.logger import logger
from typing import Optional
from bot.config import Config
from anthropic import AsyncAnthropic
from claude import tools
import json

claudeClient = AsyncAnthropic(
    api_key = Config.ANTHROPIC_API_KEY
)

try:
    with open("claude/tools.json") as file:
        TOOLS = json.load(file)
    logger.info("Loaded tools.json with %d tool definitions", len(TOOLS))
except Exception as e:
    logger.error("Failed to load tools.json: %s", e)
    raise

async def execute_tool(tool_name, tool_input):
    try:
        # Validate tool_name
        if not tool_name or not isinstance(tool_name, str):
            logger.error(f"Invalid tool name: {tool_name}")
            return "Invalid tool name provided"
        
        # Validate tool_input
        if tool_input is None:
            logger.error(f"Tool input is None for tool: {tool_name}")
            return f"No input provided for tool: {tool_name}"
        
        if hasattr(tools, tool_name):
            tool_function = getattr(tools, tool_name)
            result = tool_function(tool_input)
            result_str = str(result)
            logger.info("Tool '%s' returned result (%d chars)", tool_name, len(result_str))
            logger.debug("Full tool result for '%s': %s", tool_name, result_str)
            return result
        else:
            logger.warning(f"Requested function '{tool_name}' not found in tools.py")
            return f"Requested tool '{tool_name}' not found"
    except Exception as e:
        logger.error(f"Error calling tool '{tool_name}': {e}")
        return f"Error calling tool '{tool_name}': {e}"


async def generate_claude_response(
    messages: list,
    system_prompt: str,
    channel: Optional[discord.abc.Messageable] = None
) -> str:
    """
    Generic function to generate a response from Claude with tool support.

    Args:
        messages: List of message dicts with 'role' and 'content' keys
        system_prompt: The system prompt to use

    Returns:
        Tuple of (response_text, status_message)
    """
    conversation: list = messages.copy()
    try:
        while True:
            logger.debug("Calling Claude API: model=%s, conversation_length=%d", Config.MODEL_NAME, len(conversation))

            claudeResponse = await claudeClient.messages.create(
                    model=Config.MODEL_NAME,
                    max_tokens=Config.MAX_TOKENS,
                    system=[{"type": "text",
                            "text": system_prompt,
                            "cache_control": {"type": "ephemeral"}}],
                    messages=conversation,
                    tools=TOOLS
                )

            if claudeResponse.stop_reason == "tool_use":
                logger.info("Detected tool call(s)")

                conversation.append({"role": "assistant", "content": claudeResponse.content})

                tool_content = []
                for content in claudeResponse.content:
                    logger.debug(f"Found content: {content.type}")
                    if content.type != "tool_use":
                        logger.debug(f"not tool, skipping")
                        continue
                    logger.info(f"Found tool: {content.name} with input: {content.input}")

                    tool_result = await execute_tool(content.name, content.input)
                    tool_content.append({"type": "tool_result",
                                         "tool_use_id": content.id,
                                         "content": tool_result})

                conversation.append({"role": "user", "content": tool_content})

            else:
                # No tool calls, return final response
                final_text = ""
                for content in claudeResponse.content:
                    if content.type == "text":
                        final_text = content.text
                logger.info(f"Generated: \n{final_text}")
                return final_text
    except Exception as e:
        logger.error(f"Error in generate_claude_response: {e}", exc_info=True)
        return f"Failed to generate text: {str(e)}"