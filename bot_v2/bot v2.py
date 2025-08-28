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

# Configure logging
logging.basicConfig(filename=config.LOG_FILENAME, level=config.LOG_LEVEL, format='%(asctime)s - %(levelname)s - %(message)s', filemode='a')
logger = logging.getLogger(__name__)

load_dotenv()
BOT_API_KEY = os.getenv("BOT_API_KEY")
AI_API_KEY = os.getenv("AI_API_KEY")
ALLOWED_CHANNELS = os.getenv("ALLOWED_CHANNELS")
OVERRIDE_USERS = os.getenv("OVERRIDE_USERS")
ALLOWED_CHANNELS = json.loads(os.getenv("ALLOWED_CHANNELS"))
OVERRIDE_USERS = json.loads(os.getenv("OVERRIDE_USERS"))

with open("bot_v2/tools.json") as file:
    TOOLS = json.load(file)

claudeClient = AsyncAnthropic(
    api_key = os.getenv("ANTHROPIC_API_KEY")
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
    else:
        userConversations[userID] = [{"role": "user", "content": userMessage},
                                     {"role": "assistant", "content": botResponse}]
        
def append_user_context(userID: int, userMessage: str):
    if userID in userConversations:
        userConversations[userID].append({"role": "user", "content": userMessage})
    else:
        userConversations[userID] = [{"role": "user", "content": userMessage}]

        
def set_user_context(userID: int, userMessage: str, botResponse:str):
    userConversations[userID] = [{"role": "user", "content": userMessage},
                                     {"role": "assistant", "content": botResponse}]
    
def clear_user_context(userID: int):
    userConversations[userID] = []
    

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
                plainTranscript += f"{fragment.get("text")} "

            if len(plainTranscript) > 2000:
                plainTranscript = f"{plainTranscript[0:2000]} {plainTranscript[-2000:]}" #cut off at 2k characters otherwise wont fit in context

            messageToBot += f" The youtube link has a video with the following transcript: {plainTranscript}"
            logging.debug(f"The youtube link has a video with the following transcript: {plainTranscript}")
            return messageToBot # return message with video transcription appended
        
        else:
            logger.warning("Could not extract video ID from YouTube link")
            return messageToBot # return unmodified message if video id not found
    
    logger.info("No youtube links found in message")
    return messageToBot # return unmodified message if youtube link not found

async def process_attachments(messageToBot: str, message: discord.message):
    if not message.attachments:
        # no attachments found, return messsage without edits
        logger.info(F"No attachments found")
        return messageToBot
    
    for attachment in message.attachments:
        if "image" in attachment.content_type:
            logger.info(f"Found image attachments: {attachment.content_type}")
            # download attachment and store it in variable to process
            image_data = await attachment.read()
            image = Image.open(io.BytesIO(image_data))

            MDResult = moondream_model.caption(image, length="normal")
            imageCaption = MDResult.get("caption")
            messageToBot = messageToBot + f" (An attached image shows: {imageCaption})"
            logger.debug(f"Generated caption for image: {imageCaption}")

    return messageToBot

async def execute_tool(tool_name, tool_input):
    try:
        if hasattr(tools, tool_name):
            tool_function = getattr(tools, tool_name)
            result = tool_function(tool_input)
            logger.debug(f"Got result from tool: {result}")
            return result
        else:
            logger.warning("Requested function not found in tools.py")
            return "Requested tool not found"
    except Exception as e:
        logger.error(f"Error calling tool: {e}")
        return f"Error calling tool: {e}"

async def send_to_ai(conversationToBot: list, interaction: discord.Interaction) -> tuple[str, Optional[discord.Message]]:
    try:
        status_followup = None # Variable to hold followup if the bot message is updated to show tool call processing

        # Emulate do while loop, keep running while there are tool calls and quit out once done
        while True:
            claudeResponse = await claudeClient.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2048,
                # thinking={
                #     "type": "enabled",
                #     "budget_tokens": 1024
                # },
                system=[{"type": "text",
                        "text": config.SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"}}],
                messages=conversationToBot,
                tools=TOOLS
            )

            #print(claudeResponse)

            if claudeResponse.stop_reason == "tool_use":
                logger.info("Detected tool call(s)")
                status_followup = await interaction.followup.send("DenBot is processing tool calls...")
                conversationToBot.append({"role": "assistant", "content": claudeResponse.content})

                tool_content = []
                for content in claudeResponse.content:
                    logger.debug(f"Found content: {content.type}")
                    if content.type != "tool_use":
                        logger.debug(f"not tool, skipping")
                        continue
                    logger.info(f"Found tool: {content.name}")
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

async def preprocess_user_message(newUserMessage: discord.message) -> str:
    messageToBot = newUserMessage.content
    messageToBot = process_youtube(messageToBot, newUserMessage)

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
        add_user_context(interaction.user.id, newUserMessage.content, reply)
    else:
        set_user_context(interaction.user.id, newUserMessage.content, reply)

    return reply, status_message

@client.tree.context_menu(name="1) Ask DenBot")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.check(channel_check)
async def ask_denbot(interaction: discord.Interaction, message: discord.Message):
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
        await interaction.response.send_message("You do not have permission to use this.", ephemeral=True)
    else:
        # Handle other errors or re-raise
        raise error

@client.tree.context_menu(name="2) Continue conversation")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.check(channel_check)
async def continue_conversation(interaction: discord.Interaction, message: discord.Message):
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
        # Defer the response to prevent timeout during processing
        await interaction.response.defer(ephemeral=True)

        processedMessage = await preprocess_user_message(message)
        append_user_context(interaction.user.id, processedMessage)
        await interaction.followup.send(content="Added message to your conversation history", ephemeral=True)
    except Exception as e:
        logger.error(f"Error: {e}")

@add_to_convo.error
async def continue_conversation_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("You do not have permission to use this.", ephemeral=True)
    else:
        # Handle other errors or re-raise
        raise error
    
@client.tree.context_menu(name="4) Clear conversation history")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.check(channel_check)
async def clear_convo(interaction: discord.Interaction, message: discord.Message):
    clear_user_context(interaction.user.id)
    await interaction.response.send_message(content="Cleared your conversation history", ephemeral=True)

@clear_convo.error
async def continue_conversation_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("You do not have permission to use this.", ephemeral=True)
    else:
        # Handle other errors or re-raise
        raise error


client.run(BOT_API_KEY)
