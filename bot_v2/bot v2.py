from typing import Optional
import os
import asyncio
import re
import logging
from anthropic import AsyncAnthropic
import discord
from discord import app_commands
from youtube_transcript_api import YouTubeTranscriptApi
from dotenv import load_dotenv
import config
import json
import time
import tools
import moondream as md
from PIL import Image
import io
import html
import requests
from datetime import datetime

# Configure logging
logging.basicConfig(filename=config.LOG_FILENAME, level=config.LOG_LEVEL, format='%(asctime)s - %(levelname)s - %(message)s', filemode='a')
logger = logging.getLogger(__name__)

load_dotenv()
BOT_API_KEY = os.getenv("BOT_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ALLOWED_CHANNELS = json.loads(os.getenv("ALLOWED_CHANNELS"))
OVERRIDE_USERS = json.loads(os.getenv("OVERRIDE_USERS"))

with open("bot_v2/tools.json") as file:
    TOOLS = json.load(file)

claudeClient = AsyncAnthropic(
    api_key = ANTHROPIC_API_KEY
)

# Initialize moondream image recgocnition
moondream_model = md.vl(api_key=os.getenv("MOONDREAM_API_KEY"))

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
    if userID in userConversations:
        return userConversations.get(userID)
    else:
        return []
    
def add_user_context(userID: int, userMessage: str, botResponse:str):
    if userID in userConversations:
        userConversations[userID].append({"role": "user", "content": userMessage})
        userConversations[userID].append({"role": "assistant", "content": botResponse})
        # Trim conversation if it exceeds the limit
        userConversations[userID] = trim_conversation(userConversations[userID])
    else:
        userConversations[userID] = [{"role": "user", "content": userMessage},
                                     {"role": "assistant", "content": botResponse}]
        
def append_user_context(userID: int, userMessage: str):
    if userID in userConversations:
        userConversations[userID].append({"role": "user", "content": userMessage})
        # Trim conversation if it exceeds the limit
        userConversations[userID] = trim_conversation(userConversations[userID])
    else:
        userConversations[userID] = [{"role": "user", "content": userMessage}]

        
def set_user_context(userID: int, userMessage: str, botResponse:str):
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
    if len(conversation) <= config.MAX_CONVERSATION_LENGTH:
        return conversation
    
    # Calculate how many messages to keep
    messages_to_keep = config.MAX_CONVERSATION_LENGTH
    
    # Start from the end and work backwards to keep recent messages
    trimmed = conversation[-messages_to_keep:]
    
    logger.info(f"Trimmed conversation from {len(conversation)} to {len(trimmed)} messages")
    return trimmed

def process_youtube(messageToBot: str, message: discord.message):
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

async def process_reddit(messageToBot: str, message: discord.message) -> str:
    text = message.content
    pattern = r'https?://(?:www\.)?(?:reddit|rxddit)\.com[^\s]*'

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
            
            # Check for image and process with moondream if available
            image_description = ""
            preview = post.get("preview")
            if preview and preview.get("images"):
                try:
                    # Look for image with width 640
                    images = preview.get("images", [])
                    if images and images[0].get("resolutions"):
                        resolutions = images[0].get("resolutions", [])
                        image_url = None
                        
                        # Find resolution with width 640
                        for resolution in resolutions:
                            if resolution.get("width") == 640:
                                image_url = resolution.get("url")
                                break
                        
                        # If no 640 width found, use the first available resolution
                        if not image_url and resolutions:
                            image_url = resolutions[0].get("url")
                            
                        if image_url:
                            # Unescape HTML entities in the URL
                            image_url = html.unescape(image_url)
                            logger.info(f"Found Reddit image URL: {image_url}")
                            
                            # Download and process the image with moondream
                            image_response = requests.get(image_url, headers=headers)
                            if image_response.status_code == 200:
                                image = Image.open(io.BytesIO(image_response.content))
                                MDResult = moondream_model.caption(image, length="normal")
                                image_caption = MDResult.get("caption", "Unable to generate caption")
                                image_description = f"\nImage: {image_caption}"
                                logger.info(f"Generated caption for Reddit image: {image_caption}")
                            else:
                                logger.warning(f"Failed to download Reddit image: {image_response.status_code}")
                except Exception as e:
                    logger.error(f"Error processing Reddit image: {e}")
                    image_description = "\nImage: Unable to process image"
            
            messageToBot += reddit_info + image_description + "\n"
            
        except Exception as e:
            logger.error(f"Error processing Reddit link {link}: {e}")
            messageToBot += f" A reddit link was found but could not be processed.\n"
    
    return messageToBot
        

async def process_attachments(messageToBot: str, message: discord.message):
    if not message.attachments:
        # no attachments found, return messsage without edits
        logger.info(F"No attachments found")
        return messageToBot
    
    for attachment in message.attachments:
        try:
            if "image" in attachment.content_type:
                logger.info(f"Found image attachment: {attachment.filename} ({attachment.content_type})")
                # download attachment and store it in variable to process
                image_data = await attachment.read()
                image = Image.open(io.BytesIO(image_data))

                MDResult = moondream_model.caption(image, length="normal")
                imageCaption = MDResult.get("caption")
                messageToBot = messageToBot + f" (An attached image shows: {imageCaption})"
                logger.info(f"Generated caption for image {attachment.filename}: {imageCaption}")
            else:
                logger.info(f"Skipping non-image attachment: {attachment.filename} ({attachment.content_type})")
        except Exception as e:
            logger.error(f"Error processing attachment {attachment.filename}: {e}")
            messageToBot = messageToBot + f" (An attached image could not be processed: {attachment.filename})"

    return messageToBot

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
                model=config.MODEL_NAME,
                max_tokens=4096,
                thinking={
                    "type": "enabled",
                    "budget_tokens": 2048
                },
                system=[{"type": "text",
                        "text": config.SYSTEM_PROMPT.format(current_date=datetime.now().strftime("%B %d, %Y")),
                        "cache_control": {"type": "ephemeral"}}],
                messages=conversationToBot,
                tools=TOOLS
            )

            #print(claudeResponse)

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
                    status_followup = await interaction.followup.send(status_message)
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
                for content in claudeResponse.content:
                    if content.type == "text":
                        final_text = content.text
                logger.info(f"Generated: \n{final_text}")         
                return final_text, status_followup
            
    except Exception as e:
        logger.error(f"Error: {e}")
        return f"Failed to generate text", None

async def preprocess_user_message(newUserMessage: discord.message) -> str:
    messageToBot = newUserMessage.content
    messageToBot = process_youtube(messageToBot, newUserMessage)
    messageToBot = await process_reddit(messageToBot, newUserMessage)

    messageToBot = await process_attachments(messageToBot, newUserMessage)

    return messageToBot

    
async def handle_chat_request(interaction: discord.Interaction, newUserMessage: discord.message, continueConversation = False) -> tuple[str, Optional[discord.Message]]:
    logger.info(f"Received message '{newUserMessage.content}'")

    latestMessageToBot = await preprocess_user_message(newUserMessage)

    if continueConversation:
        conversationToBot = get_user_context(interaction.user.id)
        logger.info(f"Continuing conversation with {len(conversationToBot)} messages")
    else:
        conversationToBot = []
        logger.info("Starting new conversation")

    # conversationToBot.insert(0, {"role": "system", "content": config.SYSTEM_PROMPT})
    conversationToBot.append({"role": "user", "content": latestMessageToBot})

    logger.debug(f"sending the following conversation to bot:\n{conversationToBot}")
    reply, status_message = await send_to_ai(conversationToBot, interaction)

    if continueConversation:
        add_user_context(interaction.user.id, latestMessageToBot, reply)
        logger.info(f"Added processed message to conversation history for user {interaction.user.id}")
    else:
        set_user_context(interaction.user.id, latestMessageToBot, reply)
        logger.info(f"Set new conversation history for user {interaction.user.id}")
    
    # Log if the processed message differs from original (indicates attachment processing occurred)
    if latestMessageToBot != newUserMessage.content:
        logger.info(f"Processed message differs from original - attachments were processed and stored")

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
        # Handle other errors or re-raise
        raise error

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
        # Handle other errors or re-raise
        raise error   
    
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
        # Handle other errors or re-raise
        raise error
    
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
        # Handle other errors or re-raise
        raise error


client.run(BOT_API_KEY)
