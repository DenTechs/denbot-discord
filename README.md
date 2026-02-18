# DenBot Discord Bot

A Discord bot that uses AI to respond to messages with multi-LLM provider support (Claude or OpenAI-compatible), analyze images, and provide tools like Wolfram Alpha, GPU performance lookups, and web search. Imitates an exaggerated version of DenTech's personality.

## Features

- **Multi-LLM Provider Support**: Choose between Anthropic Claude or OpenAI-compatible local LLMs (LM Studio, Ollama, vLLM, etc.)
- **AI-Powered Responses**: Context-aware conversation using Discord reply chains for history
- **Image Processing**: Analyze and describe images via Claude API (when using Anthropic provider)
- **Tool Integration**:
  - Wolfram Alpha for computational queries
  - 3DMark GPU performance lookup with fuzzy matching
  - Web search capabilities
  - Website content summarization
- **Auto-Reply Features**:
  - Forum channel auto-replies for new posts
  - Regex-triggered automatic responses
- **Permission System**:
  - Role-based access control
  - Channel-specific permissions
  - User override capabilities
  - Forum channel whitelist
  - Server/guild-wide access control
- **GitHub Integration**: Automatic system prompt synchronization from GitHub repositories

## Setup

1. Copy `docker-compose.yml` to a folder
2. Copy `.env.example` to `.env` in the same folder as the yml and configure:
   - Set `LLM_PROVIDER` to either `anthropic` (Claude) or `openai` (for local LLMs)
   - Fill in the appropriate API keys and settings for your chosen provider
   - Configure Discord permissions and channels
3. Run the bot: `docker compose up -d`

## Configuration

Environment variables in `v3/.env`:

### Required Variables

- `BOT_API_KEY`: Discord bot token
- `LLM_PROVIDER`: LLM provider to use (`anthropic` or `openai`)
- `ALLOWED_CHANNELS`: JSON array of channel IDs where bot responds to @mentions (e.g., `["123456789"]`)
- `WOLFRAM_APPID`: Wolfram Alpha API key for computational queries

**When `LLM_PROVIDER=anthropic`:**
- `ANTHROPIC_API_KEY`: Anthropic API key
- `MODEL_NAME`: Claude model to use (e.g., `claude-haiku-4-5`)
- `SUBAGENT_MODEL_NAME`: Model for subagent tasks (e.g., `claude-haiku-4-5`)

**When `LLM_PROVIDER=openai`:**
- `OPENAI_BASE_URL`: Base URL for OpenAI-compatible API (e.g., `http://localhost:1234/v1`)
- `OPENAI_MODEL_NAME`: Model identifier for your local LLM
- `OPENAI_API_KEY`: API key (often `not-needed` for local servers)

### Optional Variables

**Permissions:**
- `ALLOWED_ROLES`: JSON array of role IDs that can use the bot anywhere
- `OVERRIDE_USERS`: JSON array of user IDs that bypass all restrictions
- `ALLOWED_FORUM_CHANNELS`: JSON array of forum channel IDs for auto-replies
- `AUTHORIZED_SERVERS`: JSON array of server/guild IDs where all members can use the bot

**Feature Flags:**
- `FORUM_REPLIES_ENABLED`: Enable auto-replies in forum channels (`true`/`false`, default: `false`)
- `REGEX_REPLIES_ENABLED`: Enable regex-triggered auto-replies (`true`/`false`, default: `false`)

**GitHub Integration:**
- `GITHUB_TOKEN`: GitHub personal access token for prompt syncing
- `GITHUB_REPO`: Repository in format `owner/repo`
- `GITHUB_BRANCH`: Branch to sync from (default: `main`)
- `PROMPT_POLL_INTERVAL`: Update check interval in seconds (default: `300`)

**Response Configuration:**
- `MAX_TOKENS`: Maximum tokens for responses (default: `1024`)
- `WEB_SEARCH_MAX_TOKENS`: Max tokens for web search results (Anthropic only, default: `1024`)

**Image Processing:**
- `IMAGE_MAX_DIMENSIONS`: Maximum image width/height in pixels (default: `800`)
- `IMAGE_MAX_FILE_SIZE_MB`: Maximum image file size in MB (default: `20`)

**Other:**
- `WOLFRAM_MAX_CHARS`: Maximum characters from Wolfram Alpha (default: `1024`)
- `LOGGING_LEVEL`: Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`, default: `INFO`)

## Usage

### Interaction Methods

**Context Menu:**
- Right-click any message → Apps → **Ask DenBot**: Opens a modal to provide additional context, then the bot responds

**@Mentions:**
- Mention the bot in allowed channels to start a conversation
- The bot uses Discord reply chains to track conversation history

**Forum Auto-Replies:**
- When `FORUM_REPLIES_ENABLED=true`, the bot automatically replies to new posts in `ALLOWED_FORUM_CHANNELS`

**Regex Auto-Replies:**
- When `REGEX_REPLIES_ENABLED=true`, the bot responds to messages matching configured patterns in `v3/regexreplies.json`

**Image Analysis:**
- Attach images to your messages (when using `LLM_PROVIDER=anthropic`)
- The bot will analyze and describe images using Claude's vision capabilities

## Requirements

**Python Version:**
- Python 3.12 (recommended and tested)

**Dependencies:**
- `discord.py ~=2.4.0` - Discord API wrapper
- `anthropic ~=0.40.0` - Anthropic Claude API client
- `openai >=1.0.0` - OpenAI-compatible API client
- `python-dotenv ~=1.0.0` - Environment variable management
- `requests ~=2.32.0` - HTTP library
- `thefuzz[speedup] ~=0.22.0` - Fuzzy string matching (for GPU lookup)
- `aiohttp ~=3.11.0` - Async HTTP client
- `Pillow ~=11.0.0` - Image processing

Install all dependencies with: `pip install -r v3/requirements.txt`
