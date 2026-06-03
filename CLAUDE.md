# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DenBot is a Discord bot supporting multiple LLM providers (Anthropic Claude and OpenAI-compatible local LLMs). The active version is in `v3/`. The `bot_v2/` directory is a legacy version.

## Commands

### Running the Bot

```bash
# Local development (from v3/)
cd v3
python main.py

# Docker
docker compose up -d
```

### Installing Dependencies

```bash
cd v3
pip install -r requirements.txt
```

### Building Docker Image

```bash
cd v3
docker build -t dentechs/denbot-discord:latest .
```

### Running Tests

No automated test runner. Tests are run manually:

```bash
python testing/test_fuzzy.py
```

## Architecture

### Entry Point & Startup Flow

`v3/main.py` → `bot/client.py::create_client()`:
1. Loads prompt files from `v3/prompts/` (`mainsystemprompt.txt`, `forumsystemprompt.txt`, `autoreplyregex.txt`)
2. Registers three event handlers: `commands.setup()`, `forums.setup()`, `messages.setup()`
3. Starts background task for GitHub prompt sync (`github_prompts.py`)
4. Runs the Discord client

### LLM Routing

`bot/llm_router.py` inspects `LLM_PROVIDER` env var and dispatches to either:
- `claude/response.py` — Anthropic client with tool-use loop
- `local_llm/response.py` — OpenAI-compatible client

Both providers share the same tool implementations in `claude/tools.py`.

### Tool System

Tools are defined in two formats:
- `claude/tools.json` — Anthropic tool schema format
- `local_llm/tools.json` — OpenAI function calling format

Implementations live in `claude/tools.py`:
- `wolfram` — WolframAlpha queries
- `threedmark_gpu_performance_lookup` — Fuzzy-matched GPU benchmark lookup against `claude/gpu_id_list.json`
- `web_research` — Web search
- `website_summary` — Fetch and summarize a URL
- `youtube_context` — YouTube transcript fetching

### Discord Interaction Handlers

| Handler | Trigger | File |
|---|---|---|
| Context menu "Ask DenBot" | Right-click any message | `bot/handlers/commands.py` |
| @Mentions | Bot mentioned in allowed channel | `bot/handlers/messages.py` |
| Forum auto-reply | New thread in whitelisted forum | `bot/handlers/forums.py` |
| Regex auto-reply | Message matches pattern in `autoreplyregex.txt` | `bot/handlers/messages.py` |

The messages handler preserves conversation context by traversing Discord reply chains.

### Permissions

`bot/checks.py` validates access by checking allowed channels, roles, override users, and authorized servers — all configured via environment variables.

### Configuration

All configuration is loaded from environment variables in `bot/config.py`. See `.env.example` for the full list. Key variables:
- `DISCORD_BOT_TOKEN` — Bot authentication
- `LLM_PROVIDER` — `anthropic` or `openai`
- `ANTHROPIC_API_KEY` / `OPENAI_BASE_URL` — Provider credentials/endpoint
- `ALLOWED_CHANNEL_IDS`, `ALLOWED_ROLE_IDS`, `OVERRIDE_USER_IDS` — Permission control
- `FORUM_REPLY_ENABLED`, `FORUM_CHANNEL_IDS` — Forum auto-reply settings

### GitHub Prompt Sync

`bot/github_prompts.py` runs as a background task, polling GitHub every 300s (configurable via `GITHUB_PROMPT_REFRESH_INTERVAL`) and updating prompt files in-place using ETag-based conditional requests to minimize bandwidth.
