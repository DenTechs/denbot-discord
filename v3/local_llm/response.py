import discord
from bot.logger import logger
from typing import Optional, Any
from bot.config import Config
from openai import AsyncOpenAI
from claude import tools
import json

# Initialize OpenAI-compatible client
openaiClient = AsyncOpenAI(
    api_key=Config.OPENAI_API_KEY,
    base_url=Config.OPENAI_BASE_URL
)

# Load tools from OpenAI-format tools.json
try:
    with open("local_llm/tools.json") as file:
        TOOLS = json.load(file)
    logger.info("Loaded local_llm/tools.json with %d tool definitions", len(TOOLS))
except Exception as e:
    logger.error("Failed to load local_llm/tools.json: %s", e)
    raise

async def execute_tool(tool_name, tool_input):
    """
    Execute a tool by calling the corresponding function from claude.tools module.
    This reuses the same tool implementations regardless of provider.
    """
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


async def generate_openai_response(
    messages: list,
    system_prompt: str,
    channel: Optional[discord.abc.Messageable] = None
) -> str:
    """
    Generic function to generate a response from OpenAI-compatible LLM with tool support.

    Args:
        messages: List of message dicts with 'role' and 'content' keys
        system_prompt: The system prompt to use
        channel: Optional Discord channel (for future typing indicators)

    Returns:
        The response text from the LLM
    """
    # Prepend system message to conversation (OpenAI format)
    conversation: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}] + messages.copy()

    try:
        while True:
            logger.debug("Calling OpenAI API: model=%s, conversation_length=%d",
                        Config.OPENAI_MODEL_NAME, len(conversation))

            response = await openaiClient.chat.completions.create(
                model=Config.OPENAI_MODEL_NAME,
                max_tokens=Config.MAX_TOKENS,
                messages=conversation,  # type: ignore[arg-type]
                tools=TOOLS  # type: ignore[arg-type]
            )

            message = response.choices[0].message
            finish_reason = response.choices[0].finish_reason

            if finish_reason == "tool_calls" and message.tool_calls:
                logger.info("Detected tool call(s): %d tools", len(message.tool_calls))

                # Add assistant message with tool calls to conversation
                assistant_msg = {
                    "role": "assistant",
                    "content": message.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,  # type: ignore[union-attr]
                                "arguments": tc.function.arguments  # type: ignore[union-attr]
                            }
                        }
                        for tc in message.tool_calls
                    ]
                }
                conversation.append(assistant_msg)

                # Execute each tool and collect results
                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name  # type: ignore[union-attr]
                    tool_args = json.loads(tool_call.function.arguments)  # type: ignore[union-attr]

                    logger.info(f"Executing tool: {tool_name} with args: {tool_args}")

                    tool_result = await execute_tool(tool_name, tool_args)

                    # Add tool result to conversation (OpenAI format)
                    conversation.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": str(tool_result)
                    })

            else:
                # No tool calls, return final response
                final_text = message.content or ""
                logger.info(f"Generated: \n{final_text}")
                return final_text

    except Exception as e:
        logger.error(f"Error in generate_openai_response: {e}", exc_info=True)
        return f"Failed to generate text: {str(e)}"
