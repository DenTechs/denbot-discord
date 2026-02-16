"""GitHub prompt auto-refresh module.

Periodically fetches prompt files from GitHub and updates PROMPT_FILES
and AUTO_REPLY_COMPILED when changes are detected.
"""

import asyncio
import re
from typing import Optional
import aiohttp
from discord.ext import tasks
from bot.config import Config
from bot.logger import logger


# Module-level state
_client_module = None
_update_lock = asyncio.Lock()
_etags = {}  # filename -> ETag for conditional requests


def _compile_regex_patterns(content: str) -> list:
    """Compile regex patterns from autoreplyregex.txt content.

    Replicates the logic from create_client().
    """
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    return [re.compile(pattern, re.IGNORECASE) for pattern in lines]


async def _fetch_file_from_github(session: aiohttp.ClientSession, filename: str) -> tuple[Optional[str], bool]:
    """Fetch a single file from GitHub using Contents API.

    Args:
        session: aiohttp session for making requests
        filename: Name of the file to fetch

    Returns:
        Tuple of (content, changed) where:
        - content is the file content (or None if unchanged/error)
        - changed is True if the file was modified, False if 304 Not Modified
    """
    url = f"https://api.github.com/repos/{Config.GITHUB_REPO}/contents/v3/prompts/{filename}"
    params = {"ref": Config.GITHUB_BRANCH}
    headers = {
        "Accept": "application/vnd.github.raw+json",  # Get raw content directly
        "Authorization": f"Bearer {Config.GITHUB_TOKEN}",
    }

    # Add ETag for conditional request if we have one
    if filename in _etags:
        headers["If-None-Match"] = _etags[filename]

    try:
        async with session.get(url, params=params, headers=headers) as response:
            if response.status == 304:
                # File unchanged
                logger.debug("GitHub file unchanged (304): %s", filename)
                return None, False

            if response.status == 200:
                content = await response.text()
                # Store ETag for next request
                if "ETag" in response.headers:
                    _etags[filename] = response.headers["ETag"]
                return content, True

            logger.error("GitHub API error for %s: HTTP %d", filename, response.status)
            return None, False

    except Exception as e:
        logger.error("Failed to fetch %s from GitHub: %s", filename, e)
        return None, False


async def _check_and_update_prompts():
    """Main update logic - compares content and applies changes."""
    if not _client_module:
        logger.warning("Client module not initialized, skipping prompt update")
        return

    logger.debug("Checking GitHub for prompt updates...")

    async with aiohttp.ClientSession() as session:
        updates = {}
        regex_changed = False

        # Fetch all prompt files
        for filename in _client_module.PROMPT_FILES.keys():
            content, changed = await _fetch_file_from_github(session, filename)
            if changed and content is not None:
                updates[filename] = content
                if filename == "autoreplyregex.txt":
                    regex_changed = True

        # Apply updates under lock
        if updates:
            async with _update_lock:
                for filename, content in updates.items():
                    _client_module.PROMPT_FILES[filename] = content
                    logger.info("Prompt file updated from GitHub: %s", filename)

                # Recompile regex if autoreplyregex.txt changed
                if regex_changed:
                    _client_module.AUTO_REPLY_COMPILED = _compile_regex_patterns(
                        updates["autoreplyregex.txt"]
                    )
                    logger.info("Recompiled %d auto-reply regex patterns",
                              len(_client_module.AUTO_REPLY_COMPILED))


@tasks.loop(seconds=Config.PROMPT_POLL_INTERVAL)
async def prompt_refresh_task():
    """Background task that periodically checks for prompt updates."""
    await _check_and_update_prompts()


@prompt_refresh_task.before_loop
async def before_prompt_refresh():
    """Wait for the bot to be ready before starting the refresh loop."""
    logger.debug("Waiting for bot to be ready before starting prompt refresh...")


def start_prompt_refresh(client_module):
    """Initialize and start the prompt refresh background task.

    Args:
        client_module: Reference to bot.client module for accessing globals
    """
    global _client_module
    _client_module = client_module

    if not Config.GITHUB_TOKEN or not Config.GITHUB_REPO:
        logger.warning("GITHUB_TOKEN or GITHUB_REPO not configured, prompt auto-refresh disabled")
        return

    prompt_refresh_task.start()
    logger.info("Prompt refresh task started (polling every %ds)", Config.PROMPT_POLL_INTERVAL)


def stop_prompt_refresh():
    """Gracefully stop the prompt refresh task."""
    if prompt_refresh_task.is_running():
        prompt_refresh_task.cancel()
        logger.info("Prompt refresh task stopped")
