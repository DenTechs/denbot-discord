# DenBot Discord Bot

A Discord bot that uses AI to respond to messages, process YouTube links, analyze images, and provide tools like Wolfram Alpha and GPU performance lookups. Immitates an exagerated version of DenTech's personality.

## Features

- AI-powered responses using Anthropic Claude
- YouTube transcript processing
- Image recognition and captioning with Moondream
- Reddit post reading with image recognition
- Tool integration (Wolfram Alpha, 3DMark GPU lookup)
- Conversation history management
- Channel and user permission controls

## Setup

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Copy `bot_v2/example.env` to `bot_v2/.env` and fill in your API keys
4. Run the bot: `python bot_v2/bot\ v2.py`

## Configuration

Required environment variables in `.env`:

- `BOT_API_KEY`: Discord bot token
- `ANTHROPIC_API_KEY`: Anthropic API key
- `ALLOWED_CHANNELS`: JSON list of allowed channel IDs
- `OVERRIDE_USERS`: JSON list of user IDs that can override restrictions
- `WOLFRAM_APPID`: Wolfram Alpha API key
- `MOONDREAM_API_KEY`: Moondream API key

## Usage

Right-click on messages in Discord and use the context menu options:

1. Ask DenBot - Start a new conversation
2. Continue conversation - Continue existing chat
3. Add to conversation history - Add message to history without responding
4. Clear conversation history - Reset conversation

The bot processes YouTube links by fetching transcripts and images by generating captions.

## Requirements

- Only tested with Python 3.12
- Dependencies listed in requirements.txt
