import requests
import os
import logging
from thefuzz import fuzz
import json
from thefuzz import process
from anthropic import Anthropic
from typing import Any
from datetime import datetime
import re
from bot.logger import logger
from bot.config import Config
from youtube_transcript_api import YouTubeTranscriptApi

def youtube_context(input):
    """
    Fetches the title and transcript of a YouTube video.
    Returns the video title plus the beginning and end of the transcript.
    """
    try:
        url = input.get("url", "")

        # Extract video ID (same patterns as bot_v2.py)
        youtu_be_pattern = r'youtu\.be/([a-zA-Z0-9_-]{11})'
        youtube_com_pattern = r'youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})'
        match = re.search(youtu_be_pattern, url) or re.search(youtube_com_pattern, url)

        if not match:
            return "Could not extract video ID from URL."

        video_id = match.group(1)
        logger.info(f"Fetching YouTube transcript for video ID: {video_id}")

        # Fetch video title via YouTube oEmbed (no API key required)
        title = "YouTube Video"
        try:
            oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
            oembed_response = requests.get(oembed_url, timeout=5)
            if oembed_response.ok:
                title = oembed_response.json().get("title", title)
            logger.info(f"Found video title: {title}")
        except Exception as e:
            logger.warning(f"Could not fetch video title: {e}")

        # Fetch transcript
        ytt_api = YouTubeTranscriptApi()
        fetched = ytt_api.fetch(video_id).to_raw_data()
        transcript = " ".join(fragment.get("text", "") for fragment in fetched)

        # Apply configurable char limit: half from start, half from end
        max_chars = Config.YOUTUBE_TRANSCRIPT_MAX_CHARS
        if len(transcript) > max_chars:
            half = max_chars // 2
            transcript = f"{transcript[:half]} [...] {transcript[-half:]}"

        return f"Title: {title}\n\nTranscript:\n{transcript}"

    except Exception as e:
        logger.error(f"Error fetching YouTube transcript: {e}")
        return f"Error fetching YouTube transcript: {str(e)}"

def website_summary(input):
    """
    Fetches and summarizes website content using Claude API with web fetch tool enabled.
    Returns a concise summary of the website's main content, title, and key points.
    """
    try:
        url = input.get("url")
        logger.info(f"Fetching website summary for URL: {url}")

        # Initialize Claude client for web fetch
        client = Anthropic(api_key=Config.ANTHROPIC_API_KEY)

        # Define the web fetch tool
        web_fetch_tool: dict[str, Any] = {
            "type": "web_fetch_20250910",
            "name": "web_fetch",
            "max_uses": 3,  # Limit fetches per request
            "citations": {
                "enabled": False
            },
            "max_content_tokens": 10000  # Limit content size
        }

        # Create a message with web fetch enabled
        current_date = datetime.now().strftime("%B %d, %Y")
        response = client.messages.create(
            model=Config.SUBAGENT_MODEL_NAME,
            max_tokens=Config.WEB_SEARCH_MAX_TOKENS,
            system=f"You are a helpful AI assistant. Current date: {current_date}",
            tools=[web_fetch_tool],  # type: ignore[arg-type]
            messages=[{
                "role": "user",
                "content": f"Please fetch the content from {url} and provide a concise summary including: 1) The page title, 2) Main topic/purpose, 3) Key points or highlights, 4) Any important information. Keep the summary brief but informative."
            }],
            extra_headers={
                "anthropic-beta": "web-fetch-2025-09-10"
            }
        )

        # Extract the text response
        result_text = ""
        for content_block in response.content:
            if content_block.type == "text":
                result_text += content_block.text

        logger.info(f"Website summary completed successfully")
        logger.debug(f"Website summary result: {result_text}")

        return result_text if result_text else "Unable to fetch or summarize the website content."

    except Exception as e:
        logger.error(f"Error fetching website summary: {e}")
        return f"Error fetching website summary: {str(e)}"

def wolfram(search_query):
    query_string = search_query.get("search_query")

    url = f"https://www.wolframalpha.com/api/v1/llm-api?"
    url += f"input={query_string}"
    url += f"&appid={Config.WOLFRAM_APPID}"
    url += f"&maxchars={Config.WOLFRAM_MAX_CHARS}"
    logger.debug(f"Using url to query wolfram: {url}")

    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml"
    }
    response = requests.get(url, headers=headers)
    logger.debug(f"response from wolfram: {response.text}")
    return response.text

# custom fuzzy sort scored for 3dmark lookup
def custom_fuzzy_scorer(query, choice):
    # Step 1: Extract VRAM from query
    vram_pattern = r'\b(\d+)\s*gb\b'
    vram_match = re.search(vram_pattern, query.lower())
    query_vram = vram_match.group(1) if vram_match else None

    # Step 2: Clean query (remove VRAM tokens)
    clean_query = re.sub(vram_pattern, '', query, flags=re.IGNORECASE).strip()

    # Step 3: Calculate base score with cleaned query
    base_score = fuzz.token_set_ratio(clean_query, choice)

    if base_score == 100:
        if clean_query.lower() in choice.lower():
            word_count = len(choice.split())
            score = 100 - (word_count - 4) * 0.5

            # Tiebreaker: prefer standard naming patterns
            choice_lower = choice.lower()
            if 'geforce' in choice_lower and not any(x in choice_lower for x in ['(', ')', 'notebook', 'mobile', 'ti', 'super']):
                score += 0.1  # Small bonus for clean GeForce naming
            elif '(' in choice_lower or ')' in choice_lower:
                score -= 0.1  # Small penalty for parenthetical versions

            # VRAM tiebreaker: match VRAM specifications
            if query_vram:
                choice_vram_match = re.search(r'\b(\d+)\s*gb\b', choice_lower)
                if choice_vram_match:
                    choice_vram = choice_vram_match.group(1)
                    if choice_vram != query_vram:
                        score -= 5  # Penalize explicit mismatch
                    else:
                        score += 2  # Bonus for explicit match

            return score
        else:
            query_tokens = len(clean_query.split())
            choice_tokens = len(choice.split())
            return max(0, base_score - (choice_tokens - query_tokens))
    return base_score

def threedmark_gpu_performance_lookup(input):
    try:
        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01"
        }

        with open("claude/gpu_id_list.json", "r") as file:
            gpu_id_list = json.load(file)

        name_to_id = {gpu.get("name"): gpu.get("id") for gpu in gpu_id_list}
        gpu_name_list = [gpu.get("name") for gpu in gpu_id_list]

        best_match = process.extractOne(input.get("gpu_model"), gpu_name_list, scorer=custom_fuzzy_scorer)

        if best_match is None:
            return "Error: GPU model not found in database"

        gpu_name, score = best_match[0], best_match[1]
        gpu_id = name_to_id[gpu_name]

        gpu_performance_query = f"https://www.3dmark.com/proxycon/ajax/medianscore?test=spy%20P&gpuId={gpu_id}&country=&scoreType=graphicsScore"
        reponse_perf = requests.get(gpu_performance_query, headers=headers)
        json_data_perf = reponse_perf.json()
        logger.info(f"Got response back for {gpu_name} from 3dmark: {json_data_perf}")
        gpu_performance = round(json_data_perf.get("median"))

        return f"{gpu_name} median performance score is: {gpu_performance}"
    except Exception as e:
        logger.error(f"Error getting gpu performance: {e}")
        return f"Error getting gpu performance: {e}"

def web_research(input):
    """
    Performs web research using Claude API with web search tool enabled.
    Returns formatted search results to the main conversation.
    """
    try:
        search_query = input.get("search_query")
        logger.info(f"Performing web research for query: {search_query}")

        # Initialize Claude client for web search with beta header
        client = Anthropic(
            api_key=Config.ANTHROPIC_API_KEY,
            default_headers={"anthropic-beta": "web-search-2025-03-05"}
        )

        # Define the web search tool
        web_search_tool: dict[str, Any] = {
            "type": "web_search_20250305",
            "name": "web_search"
        }

        # Create a message with web search enabled
        current_date = datetime.now().strftime("%B %d, %Y")
        response = client.messages.create(
            model=Config.SUBAGENT_MODEL_NAME,
            max_tokens=Config.WEB_SEARCH_MAX_TOKENS,
            system=f"You are a helpful AI assistant. Current date: {current_date}",
            tools=[web_search_tool],  # type: ignore[arg-type]
            messages=[{
                "role": "user",
                "content": f"Search the web and provide a concise summary of the most relevant and current information about: {search_query}"
            }]
        )

        # Extract the text response
        result_text = ""
        for content_block in response.content:
            if content_block.type == "text":
                result_text += content_block.text

        logger.info(f"Web research completed successfully")
        logger.debug(f"Web research result: {result_text}")

        return result_text if result_text else "No results found for the search query."

    except Exception as e:
        logger.error(f"Error performing web research: {e}")
        return f"Error performing web research: {str(e)}"
