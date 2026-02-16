from typing import Optional
import os
import asyncio
import re
import logging
from anthropic import AsyncAnthropic
import discord
from discord import app_commands
from youtube_transcript_api._api import YouTubeTranscriptApi
from dotenv import load_dotenv
import base64
import json
import time
import tools
from PIL import Image
import io
import html
import requests
from datetime import datetime

# Load Environment Keys
load_dotenv()
BOT_API_KEY:str = os.getenv("BOT_API_KEY") or ""
ANTHROPIC_API_KEY:str = os.getenv("ANTHROPIC_API_KEY") or ""
ALLOWED_CHANNELS:list = json.loads(os.getenv("ALLOWED_CHANNELS") or "[]")
OVERRIDE_USERS:list = json.loads(os.getenv("OVERRIDE_USERS") or "[]")
WOLFRAM_APPID:str = os.getenv("WOLFRAM_APPID") or ""
IMAGE_MAX_SIZE:int = int(os.getenv("IMAGE_MAX_SIZE") or 800)
MAX_TOKENS:int = int(os.getenv("MAX_TOKENS") or 0)
MODEL_NAME:str = os.getenv("MODEL_NAME") or ""
SUBAGENT_MODEL_NAME:str = os.getenv("SUBAGENT_MODEL_NAME") or ""
WOLFRAM_MAX_CHARS:int = int(os.getenv("WOLFRAM_MAX_CHARS") or 0)
WEB_SEARCH_MAX_TOKENS:int = int(os.getenv("WEB_SEARCH_MAX_TOKENS") or 0)
MAX_CONVERSATION_LENGTH:int = int(os.getenv("MAX_CONVERSATION_LENGTH") or 0)
LOG_LEVEL:str = os.getenv("LOG_LEVEL") or ""
SYSTEM_PROMPT:str = os.getenv("SYSTEM_PROMPT") or ""

# Configure logging to stdout for Docker
logging.basicConfig(level=LOG_LEVEL, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

with open("tools.json") as file:
    TOOLS = json.load(file)

claudeClient = AsyncAnthropic(
    api_key = ANTHROPIC_API_KEY
)

ytt_api = YouTubeTranscriptApi()

userConversations = {}

class MyClient(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        # A CommandTree is a special type that holds all the application command
        # state required to make it work. This is a separate class because it
        # allows all the extra state to be opt-in.
        # Whenever you want to work with application commands, your tree is used
        # to store and work with them.
        # Note: When using commands.Bot instead of discord.Client, the bot will
        # maintain its own tree instead.
        self.tree = app_commands.CommandTree(self)

    # In this basic example, we just synchronize the app commands to one guild.
    # Instead of specifying a guild to every command, we copy over our global commands instead.
    # By doing so, we don't have to wait up to an hour until they are shown to the end-user.
    async def setup_hook(self):
        # Sync commands globally for user installs to work in DMs
        # DO NOT SYNC THE SAME COMMAND GLOBALLY AND COPIED TO A GUILD
        await self.tree.sync()

intents = discord.Intents.default()
client = MyClient(intents=intents)

def channel_check(interaction: discord.Interaction) -> bool:
    if interaction.channel_id in ALLOWED_CHANNELS or interaction.user.id in OVERRIDE_USERS:
        return True
    else:
        return False
    
def get_user_context(userID: int) -> list:
    """Get a copy of the user's conversation history."""
    if userID in userConversations:
        return userConversations[userID].copy()
    else:
        return []
    
def add_user_context(userID: int, userMessage: list | str, botResponse: str):
    """Add user message and bot response to conversation history.
    userMessage can be a string or list of content blocks (for images)."""
    if userID in userConversations:
        userConversations[userID].append({"role": "user", "content": userMessage})
        userConversations[userID].append({"role": "assistant", "content": botResponse})
        # Trim conversation if it exceeds the limit
        userConversations[userID] = trim_conversation(userConversations[userID])
    else:
        userConversations[userID] = [{"role": "user", "content": userMessage},
                                     {"role": "assistant", "content": botResponse}]
        
def append_user_context(userID: int, userMessage: list | str):
    """Append user message to conversation history.
    userMessage can be a string or list of content blocks (for images)."""
    if userID in userConversations:
        userConversations[userID].append({"role": "user", "content": userMessage})
        # Trim conversation if it exceeds the limit
        userConversations[userID] = trim_conversation(userConversations[userID])
    else:
        userConversations[userID] = [{"role": "user", "content": userMessage}]

        
def set_user_context(userID: int, userMessage: list | str, botResponse: str):
    """Set new conversation history with user message and bot response.
    userMessage can be a string or list of content blocks (for images)."""
    conversation = [{"role": "user", "content": userMessage},
                   {"role": "assistant", "content": botResponse}]
    # Apply trimming even for new conversations (shouldn't be needed but for consistency)
    userConversations[userID] = trim_conversation(conversation)
    
def clear_user_context(userID: int):
    userConversations[userID] = []

def trim_conversation(conversation: list) -> list:
    """
    Trim conversation to stay within MAX_CONVERSATION_LENGTH limit.
    Keeps the most recent messages and maintains user-assistant pairs.
    """
    if len(conversation) <= MAX_CONVERSATION_LENGTH:
        return conversation
    
    # Calculate how many messages to keep
    messages_to_keep = MAX_CONVERSATION_LENGTH
    
    # Start from the end and work backwards to keep recent messages
    trimmed = conversation[-messages_to_keep:]
    
    logger.info(f"Trimmed conversation from {len(conversation)} to {len(trimmed)} messages")
    return trimmed

async def process_youtube(messageToBot: str, message: discord.Message):
    # searches received message for youtube link, if found appends the transcript to the end of the message
    # returns message regardless of if its been modified

    if "youtu.be" in message.content or "youtube.com" in message.content:
        logger.info("Found youtube link")
        
        # Regex patterns for different YouTube URL formats
        # Pattern for youtu.be/VIDEO_ID
        youtu_be_pattern = r'youtu\.be/([a-zA-Z0-9_-]{11})'
        # Pattern for youtube.com/watch?v=VIDEO_ID
        youtube_com_pattern = r'youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})'
        
        # Search for video ID in the message content
        match = re.search(youtu_be_pattern, message.content)
        if not match:
            match = re.search(youtube_com_pattern, message.content)
        
        if match:
            videoID = match.group(1)
            logger.info(f"Extracted video ID: {videoID}")

            FetchedTranscript = ytt_api.fetch(videoID).to_raw_data()
            plainTranscript = ""
            for fragment in FetchedTranscript:
                plainTranscript += f"""{fragment.get("text")} """

            if len(plainTranscript) > 2000:
                plainTranscript = f"{plainTranscript[0:2000]} {plainTranscript[-2000:]}" #cut off at 4k characters otherwise wont fit in context

            messageToBot += f" The youtube link has a video with the following transcript: {plainTranscript}"
            logger.debug(f"The youtube link has a video with the following transcript: {plainTranscript}")
            return messageToBot # return message with video transcription appended
        
        else:
            logger.warning("Could not extract video ID from YouTube link")
            return messageToBot # return unmodified message if video id not found
    
    logger.info("No youtube links found in message")
    return messageToBot # return unmodified message if youtube link not found

async def process_reddit(messageToBot: str, message: discord.Message) -> tuple[str, list]:
    """Process Reddit links and return text info plus image blocks for Claude API."""
    text = message.content
    pattern = r'https?://(?:www\.)?(?:reddit|rxddit)\.com[^\s]*'
    image_blocks = []

    matches = re.findall(pattern, text)
    for link in matches:
        try:
            logger.info(f"Processing Reddit link: {link}")
            link = link.replace("rxddit.com", "reddit.com")
            if not link.endswith("/"):
                link += "/"
            link += ".json"
            unescaped_link = html.unescape(link)

            headers = {'User-Agent': 'Mozilla/5.0'}
            page = requests.get(unescaped_link, headers=headers)
            page_json = page.json()
            
            # Safely extract post data with null checks
            post_data = page_json[0].get("data", {}).get("children", [])
            if not post_data:
                logger.warning("No post data found in Reddit JSON")
                continue
                
            post = post_data[0].get("data", {})
            subreddit = post.get("subreddit_name_prefixed", "unknown subreddit")
            logger.info(f"Subreddit: {subreddit}")
            title = post.get("title", "No title")
            logger.info(f"Title: {title}")
            body_text = post.get("selftext", "")
            logger.info(f"Text: {body_text}")
            
            # Build the basic Reddit post info
            reddit_info = f" A reddit link leads to a post from the {subreddit} subreddit.\nTitle: {title}"
            if body_text:
                reddit_info += f"\nText: {body_text}"
            
            # Check for image and process for Claude API
            preview = post.get("preview")
            if preview and preview.get("images"):
                try:
                    images = preview.get("images", [])
                    if images and images[0].get("resolutions"):
                        resolutions = images[0].get("resolutions", [])
                        image_url = None
                        
                        # Find resolution with width 640 or closest
                        for resolution in resolutions:
                            if resolution.get("width") == 640:
                                image_url = resolution.get("url")
                                break
                        
                        if not image_url and resolutions:
                            image_url = resolutions[-1].get("url")  # Use highest resolution available
                            
                        if image_url:
                            image_url = html.unescape(image_url)
                            logger.info(f"Found Reddit image URL: {image_url}")
                            
                            image_response = requests.get(image_url, headers=headers)
                            if image_response.status_code == 200:
                                image_block = await process_image_for_claude(image_response.content)
                                if image_block:
                                    image_blocks.append(image_block)
                                    reddit_info += "\n(Reddit post image attached)"
                                    logger.info(f"Processed Reddit image for Claude API")
                            else:
                                logger.warning(f"Failed to download Reddit image: {image_response.status_code}")
                except Exception as e:
                    logger.error(f"Error processing Reddit image: {e}")
            
            messageToBot += reddit_info + "\n"
            
        except Exception as e:
            logger.error(f"Error processing Reddit link {link}: {e}")
            messageToBot += f" A reddit link was found but could not be processed.\n"
    
    return messageToBot, image_blocks
        

async def process_image_for_claude(image_data: bytes) -> dict | None:
    """Process image data and return a Claude API image block.
    Resizes image to fit within IMAGE_MAX_SIZE and converts to base64."""
    try:
        image = Image.open(io.BytesIO(image_data))
        
        # Convert to RGB if necessary (handles RGBA, P mode, etc.)
        if image.mode in ('RGBA', 'P', 'LA'):
            # Create white background for transparency
            background = Image.new('RGB', image.size, (255, 255, 255))
            if image.mode == 'P':
                image = image.convert('RGBA')
            background.paste(image, mask=image.split()[-1] if image.mode in ('RGBA', 'LA') else None)
            image = background
        elif image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Resize if larger than IMAGE_MAX_SIZE
        width, height = image.size
        if width > IMAGE_MAX_SIZE or height > IMAGE_MAX_SIZE:
            if width > height:
                new_width = IMAGE_MAX_SIZE
                new_height = int(height * (IMAGE_MAX_SIZE / width))
            else:
                new_height = IMAGE_MAX_SIZE
                new_width = int(width * (IMAGE_MAX_SIZE / height))
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            logger.info(f"Resized image from {width}x{height} to {new_width}x{new_height}")
        
        # Convert to base64
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG', quality=85)
        base64_data = base64.b64encode(buffer.getvalue()).decode('utf-8')
        
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": base64_data
            }
        }
    except Exception as e:
        logger.error(f"Error processing image for Claude: {e}")
        return None


async def process_attachments(message: discord.Message) -> list:
    """Process message attachments and return list of image blocks for Claude API."""
    image_blocks = []
    
    if not message.attachments:
        logger.info("No attachments found")
        return image_blocks
    
    for attachment in message.attachments:
        try:
            if attachment.content_type is not None and "image" in attachment.content_type:
                logger.info(f"Found image attachment: {attachment.filename} ({attachment.content_type})")
                image_data = await attachment.read()
                image_block = await process_image_for_claude(image_data)
                if image_block:
                    image_blocks.append(image_block)
                    logger.info(f"Processed image {attachment.filename} for Claude API")
            else:
                logger.info(f"Skipping non-image attachment: {attachment.filename} ({attachment.content_type})")
        except Exception as e:
            logger.error(f"Error processing attachment {attachment.filename}: {e}")

    return image_blocks

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
            logger.info(f"Got result from tool: {result}")
            return result
        else:
            logger.warning(f"Requested function '{tool_name}' not found in tools.py")
            return f"Requested tool '{tool_name}' not found"
    except Exception as e:
        logger.error(f"Error calling tool '{tool_name}': {e}")
        return f"Error calling tool '{tool_name}': {e}"

async def send_to_ai(conversationToBot: list, interaction: discord.Interaction) -> tuple[str, Optional[discord.Message]]:
    try:
        status_followup = None # Variable to hold followup if the bot message is updated to show tool call processing

        # Emulate do while loop, keep running while there are tool calls and quit out once done
        while True:
            claudeResponse = await claudeClient.messages.create(
                model=MODEL_NAME,
                max_tokens=4096,
                thinking={
                    "type": "enabled",
                    "budget_tokens": 2048
                },
                system=[{"type": "text",
                        "text": SYSTEM_PROMPT.format(current_date=datetime.now().strftime("%B %d, %Y")),
                        "cache_control": {"type": "ephemeral"}}],
                messages=conversationToBot,
                tools=TOOLS
            )

            if claudeResponse.stop_reason == "tool_use":
                logger.info("Detected tool call(s)")
                
                # Collect tool names for dynamic message
                tool_names = []
                for content in claudeResponse.content:
                    if content.type == "tool_use":
                        tool_names.append(content.name)
                
                # Create dynamic status message
                if len(tool_names) == 1:
                    status_message = f"DenBot is using {tool_names[0]}..."
                else:
                    status_message = f"DenBot is using {len(tool_names)} tools: {', '.join(tool_names)}..."
                
                # Send or update status message
                if status_followup is None:
                    status_followup = await interaction.followup.send(status_message, wait=True)
                else:
                    await status_followup.edit(content=status_message)
                
                conversationToBot.append({"role": "assistant", "content": claudeResponse.content})

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
                    
                conversationToBot.append({"role": "user",
                                          "content": tool_content})
                
            else:
                # No tool calls, send final message
                final_text = ""
                for content in claudeResponse.content:
                    if content.type == "text":
                        final_text = content.text
                logger.info(f"Generated: \n{final_text}")         
                return final_text, status_followup
            
    except Exception as e:
        logger.error(f"Error in send_to_ai: {e}", exc_info=True)
        return f"Failed to generate text: {str(e)}", None

async def preprocess_user_message(newUserMessage: discord.Message) -> list:
    """Process user message and return list of content blocks for Claude API.
    Returns a list containing text block and any image blocks from attachments."""
    content_blocks = []
    image_blocks = []
    
    # Build text content
    messageText = f"<username>{newUserMessage.author.display_name}</username><message>"
    messageText += newUserMessage.content
    messageText = await process_youtube(messageText, newUserMessage)
    
    # Process Reddit (returns text and image blocks)
    messageText, reddit_images = await process_reddit(messageText, newUserMessage)
    image_blocks.extend(reddit_images)
    
    # Process attachments (returns image blocks)
    attachment_images = await process_attachments(newUserMessage)
    image_blocks.extend(attachment_images)
    
    messageText += "</message>"
    
    # Add text block first
    content_blocks.append({"type": "text", "text": messageText})
    
    # Add image blocks
    content_blocks.extend(image_blocks)
    
    return content_blocks

    
async def handle_chat_request(interaction: discord.Interaction, newUserMessage: discord.Message, continueConversation = False) -> tuple[str, Optional[discord.Message]]:
    logger.info(f"Received message '{newUserMessage.content}'")

    latestMessageContent = await preprocess_user_message(newUserMessage)

    if continueConversation:
        conversationToBot = get_user_context(interaction.user.id)
        logger.info(f"Continuing conversation with {len(conversationToBot)} messages")
    else:
        conversationToBot = []
        logger.info("Starting new conversation")

    conversationToBot.append({"role": "user", "content": latestMessageContent})

    logger.debug(f"sending the following conversation to bot:\n{conversationToBot}")
    reply, status_message = await send_to_ai(conversationToBot, interaction)

    if continueConversation:
        add_user_context(interaction.user.id, latestMessageContent, reply)
        logger.info(f"Added processed message to conversation history for user {interaction.user.id}")
    else:
        set_user_context(interaction.user.id, latestMessageContent, reply)
        logger.info(f"Set new conversation history for user {interaction.user.id}")
    
    # Log if images were included in the message
    if len(latestMessageContent) > 1:
        logger.info(f"Message included {len(latestMessageContent) - 1} image(s)")

    return reply, status_message

@client.tree.context_menu(name="1) Ask DenBot")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.check(channel_check)
async def ask_denbot(interaction: discord.Interaction, message: discord.Message):
    logger.info(f"User {interaction.user.name} used ask denbot")
    # Defer the response to prevent timeout during processing
    await interaction.response.defer()

    reply, status_message = await handle_chat_request(interaction=interaction, newUserMessage=message, continueConversation=False)

    if status_message:
        await status_message.edit(content=reply)
    else:
        await interaction.followup.send(reply)
    

@ask_denbot.error
async def ask_denbot_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        logger.info(f"User {interaction.user.name} tried to ask denbot but did not have permission.")
        await interaction.response.send_message("You do not have permission to use this.", ephemeral=True)
    else:
        logger.error(f"Error in ask_denbot: {error}", exc_info=True)
        try:
            await interaction.followup.send("An error occurred while processing your request.", ephemeral=True)
        except:
            pass

@client.tree.context_menu(name="2) Continue conversation")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.check(channel_check)
async def continue_conversation(interaction: discord.Interaction, message: discord.Message):
    logger.info(f"User {interaction.user.name} used continue conversation")
    # Defer the response to prevent timeout during processing
    await interaction.response.defer()

    reply, status_message = await handle_chat_request(interaction=interaction, newUserMessage=message, continueConversation=True)

    if status_message:
        await status_message.edit(content=reply)
    else:
        await interaction.followup.send(reply)

@continue_conversation.error
async def continue_conversation_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        logger.info(f"User {interaction.user.name} tried to continue their conversation history but did not have permission.")
        await interaction.response.send_message("You do not have permission to use this.", ephemeral=True)
    else:
        logger.error(f"Error in continue_conversation: {error}", exc_info=True)
        try:
            await interaction.followup.send("An error occurred while processing your request.", ephemeral=True)
        except:
            pass   
    
@client.tree.context_menu(name="3) Add to conversation history")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.check(channel_check)
async def add_to_convo(interaction: discord.Interaction, message: discord.Message):
    try:
        logger.info(f"User {interaction.user.name} used add to conversation history")
        # Defer the response to prevent timeout during processing
        await interaction.response.defer(ephemeral=True)

        processedMessage = await preprocess_user_message(message)
        append_user_context(interaction.user.id, processedMessage)
        logger.info(f"Added message to conversation history")
        await interaction.followup.send(content="Added message to your conversation history", ephemeral=True)
    except Exception as e:
        logger.error(f"Error: {e}")

@add_to_convo.error
async def add_to_convo_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        logger.info(f"User {interaction.user.name} tried to add to their conversation history but did not have permission.")
        await interaction.response.send_message("You do not have permission to use this.", ephemeral=True)
    else:
        logger.error(f"Error in add_to_convo: {error}", exc_info=True)
        try:
            await interaction.followup.send("An error occurred while processing your request.", ephemeral=True)
        except:
            pass
    
@client.tree.context_menu(name="4) Clear conversation history")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.check(channel_check)
async def clear_convo(interaction: discord.Interaction, message: discord.Message):
    logger.info(f"User {interaction.user.name} used clear conversation history")
    clear_user_context(interaction.user.id)
    await interaction.response.send_message(content="Cleared your conversation history", ephemeral=True)

@clear_convo.error
async def clear_convo_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        logger.info(f"User {interaction.user.name} tried to clear their conversation history but did not have permission.")
        await interaction.response.send_message("You do not have permission to use this.", ephemeral=True)
    else:
        logger.error(f"Error in clear_convo: {error}", exc_info=True)
        try:
            await interaction.followup.send("An error occurred while processing your request.", ephemeral=True)
        except:
            pass


client.run(BOT_API_KEY)
