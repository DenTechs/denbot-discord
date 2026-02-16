import os
from dotenv import load_dotenv
import json

load_dotenv()

class Config:
    BOT_API_KEY:str = os.getenv("BOT_API_KEY") or ""

    # LLM Provider Selection
    LLM_PROVIDER:str = os.getenv("LLM_PROVIDER", "anthropic")  # "anthropic" or "openai"

    # Anthropic (Claude) Configuration
    ANTHROPIC_API_KEY:str = os.getenv("ANTHROPIC_API_KEY") or ""
    MODEL_NAME:str = os.getenv("MODEL_NAME") or ""
    SUBAGENT_MODEL_NAME:str = os.getenv("SUBAGENT_MODEL_NAME") or ""
    MAX_TOKENS:int = int(os.getenv("MAX_TOKENS") or 0)
    WEB_SEARCH_MAX_TOKENS:int = int(os.getenv("WEB_SEARCH_MAX_TOKENS") or 0)

    # Wolfram Alpha Configuration
    WOLFRAM_APPID:str = os.getenv("WOLFRAM_APPID") or ""
    WOLFRAM_MAX_CHARS:int = int(os.getenv("WOLFRAM_MAX_CHARS") or 8000)

    # OpenAI-Compatible Configuration (for local LLMs)
    OPENAI_API_KEY:str = os.getenv("OPENAI_API_KEY", "not-needed")
    OPENAI_BASE_URL:str = os.getenv("OPENAI_BASE_URL", "http://localhost:1234/v1")
    OPENAI_MODEL_NAME:str = os.getenv("OPENAI_MODEL_NAME", "local-model")

    # Discord Permissions
    ALLOWED_CHANNELS:list = json.loads(os.getenv("ALLOWED_CHANNELS") or "[]")
    ALLOWED_ROLES:list = json.loads(os.getenv("ALLOWED_ROLES") or "[]")
    OVERRIDE_USERS:list = json.loads(os.getenv("OVERRIDE_USERS") or "[]")
    ALLOWED_FORUM_CHANNELS:list = json.loads(os.getenv("ALLOWED_FORUM_CHANNELS") or "[]")

    # Feature Flags
    FORUM_REPLIES_ENABLED:bool = os.getenv("FORUM_REPLIES_ENABLED", "").lower() in ("true", "1", "yes")
    REGEX_REPLIES_ENABLED:bool = os.getenv("REGEX_REPLIES_ENABLED", "").lower() in ("true", "1", "yes")

    # GitHub Integration
    GITHUB_TOKEN:str = os.getenv("GITHUB_TOKEN") or ""
    GITHUB_REPO:str = os.getenv("GITHUB_REPO") or ""
    GITHUB_BRANCH:str = os.getenv("GITHUB_BRANCH") or "main"
    PROMPT_POLL_INTERVAL:int = int(os.getenv("PROMPT_POLL_INTERVAL") or 300)

    # Logging
    LOGGING_LEVEL:str = os.getenv("LOGGING_LEVEL") or "INFO"