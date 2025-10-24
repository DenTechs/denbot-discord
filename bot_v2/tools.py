import config
import requests
import os
import logging
from thefuzz import fuzz
import json
from thefuzz import process
from anthropic import Anthropic
from datetime import datetime

# Configure logging
logging.basicConfig(filename=config.LOG_FILENAME, level=config.LOG_LEVEL, format='%(asctime)s - %(levelname)s - %(message)s', filemode='a')
logger = logging.getLogger(__name__)

def wolfram(search_query):
    query_string = search_query.get("search_query")

    WOLFRAM_APPID = os.getenv("WOLFRAM_APPID")
    url = f"https://www.wolframalpha.com/api/v1/llm-api?"
    url += f"input={query_string}"
    url += f"&appid={WOLFRAM_APPID}"
    url += f"&maxchars={config.WOLFRAM_MAX_CHARS}"
    logger.debug(f"Using url to query wolfram: {url}")

    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml"
    }
    response = requests.get(url, headers=headers)
    logger.debug(f"response from wolfram: {response.text}")
    return response.text

# custom fuzzy sort scored for 3dmark lookup
def custom_fuzzy_scorer(query, choice):
    base_score = fuzz.token_set_ratio(query, choice)
    if base_score == 100:
        if query.lower() in choice.lower():
            word_count = len(choice.split())
            score = 100 - (word_count - 4) * 0.5
           
            # Tiebreaker: prefer standard naming patterns
            choice_lower = choice.lower()
            if 'geforce' in choice_lower and not any(x in choice_lower for x in ['(', ')', 'notebook', 'mobile', 'ti', 'super']):
                score += 0.1  # Small bonus for clean GeForce naming
            elif '(' in choice_lower or ')' in choice_lower:
                score -= 0.1  # Small penalty for parenthetical versions
               
            return score
        else:
            query_tokens = len(query.split())
            choice_tokens = len(choice.split())
            return max(0, base_score - (choice_tokens - query_tokens))
    return base_score

def threedmark_gpu_performance_lookup(input):
    try:
        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01"
        }

        with open("bot_v2/gpu_id_list.json", "r") as file:
            gpu_id_list = json.load(file)

        name_to_id = {gpu.get("name"): gpu.get("id") for gpu in gpu_id_list}
        gpu_name_list = [gpu.get("name") for gpu in gpu_id_list]

        best_match = process.extractOne(input.get("gpu_model"), gpu_name_list, scorer=custom_fuzzy_scorer)

        gpu_name, score = best_match
        gpu_id = name_to_id[gpu_name]

        # gpu_id_query = f"""https://www.3dmark.com/proxycon/ajax/search/gpuname?term={input.get("gpu_model")}"""
        # response = requests.get(gpu_id_query, headers=headers)
        # json_data_id = response.json()
        # gpu_id = json_data_id[0].get("id")
        # gpu_name = json_data_id[0].get("label")

        gpu_performance_query = f"https://www.3dmark.com/proxycon/ajax/medianscore?test=spy%20P&gpuId={gpu_id}&country=&scoreType=graphicsScore"
        reponse_perf = requests.get(gpu_performance_query, headers=headers)
        json_data_perf = reponse_perf.json()
        logger.info(f"Got response back from 3dmark: {json_data_perf}")
        gpu_performance = round(json_data_perf.get("median"))

        return f"{gpu_name} median performance score is: {gpu_performance} and the name lookup accuracy score is {score}"
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
        ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
        client = Anthropic(
            api_key=ANTHROPIC_API_KEY,
            default_headers={"anthropic-beta": "web-search-2025-03-05"}
        )

        # Define the web search tool
        web_search_tool = {
            "type": "web_search_20250305",
            "name": "web_search"
        }

        # Create a message with web search enabled
        current_date = datetime.now().strftime("%B %d, %Y")
        response = client.messages.create(
            model=config.SUBAGENT_MODEL_NAME,
            max_tokens=config.WEB_SEARCH_MAX_TOKENS,
            system=f"You are a helpful AI sub-agent providing information to a master agent. Current date: {current_date}",
            tools=[web_search_tool],
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

def website_summary(input):
    """
    Fetches and summarizes website content using Claude API with web fetch tool enabled.
    Returns a concise summary of the website's main content, title, and key points.
    """
    try:
        url = input.get("url")
        logger.info(f"Fetching website summary for URL: {url}")

        # Initialize Claude client for web fetch with beta header
        ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
        client = Anthropic(
            api_key=ANTHROPIC_API_KEY,
            default_headers={"anthropic-beta": "web-fetch-2025-09-10"}
        )

        # Define the web fetch tool
        web_fetch_tool = {
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
            model=config.SUBAGENT_MODEL_NAME,
            max_tokens=config.WEB_SEARCH_MAX_TOKENS,
            system=f"You are a helpful AI sub-agent providing information to a master agent. Current date: {current_date}",
            tools=[web_fetch_tool],
            messages=[{
                "role": "user",
                "content": f"Please fetch the content from {url} and provide a concise summary including: 1) The page title, 2) Main topic/purpose, 3) Key points or highlights, 4) Any important information. Keep the summary brief but informative."
            }]
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

def code_execution(input):
    """
    Executes code using Claude's code execution tool in a secure sandbox environment.
    Supports Python, JavaScript, bash commands, file operations, and data analysis.
    Returns execution results including output, errors, and any generated files.
    """
    try:
        code = input.get("code", "")
        language = input.get("language", "python")  # Default to python if not specified
        logger.info(f"Executing {language} code: {code[:100]}...")

        # Initialize Claude client for code execution with beta header
        ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
        client = Anthropic(
            api_key=ANTHROPIC_API_KEY,
            default_headers={"anthropic-beta": "code-execution-2025-08-25"}
        )

        # Define the code execution tool
        code_execution_tool = {
            "type": "code_execution_20250825",
            "name": "code_execution"
        }

        # Create a message with code execution enabled
        current_date = datetime.now().strftime("%B %d, %Y")
        
        # Format the request based on language
        if language.lower() in ["python", "py"]:
            prompt = f"Execute this Python code and provide the results:\n\n```python\n{code}\n```"
        elif language.lower() in ["javascript", "js", "node"]:
            prompt = f"Execute this JavaScript code and provide the results:\n\n```javascript\n{code}\n```"
        elif language.lower() in ["bash", "shell", "sh"]:
            prompt = f"Execute this bash command and provide the results:\n\n```bash\n{code}\n```"
        else:
            prompt = f"Execute this {language} code and provide the results:\n\n```\n{code}\n```"

        response = client.messages.create(
            model=config.SUBAGENT_MODEL_NAME,
            max_tokens=config.CODE_EXECUTION_MAX_TOKENS,
            system=f"You are a helpful AI sub-agent with code execution capabilities providing information to a master agent. Current date: {current_date}",
            tools=[code_execution_tool],
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )

        # Extract the text response and any tool results
        result_text = ""
        execution_output = ""
        
        for content_block in response.content:
            if content_block.type == "text":
                result_text += content_block.text
            elif hasattr(content_block, 'type') and content_block.type in ["bash_code_execution_tool_result", "text_editor_code_execution_tool_result"]:
                # Extract execution results
                if hasattr(content_block, 'content'):
                    if hasattr(content_block.content, 'stdout'):
                        execution_output += f"Output: {content_block.content.stdout}\n"
                    if hasattr(content_block.content, 'stderr') and content_block.content.stderr:
                        execution_output += f"Errors: {content_block.content.stderr}\n"

        # Combine results
        final_result = result_text
        if execution_output:
            final_result += f"\n\nExecution Details:\n{execution_output}"

        logger.info(f"Code execution completed successfully")
        logger.debug(f"Code execution result: {final_result}")

        return final_result if final_result else "Code executed but no output was generated."

    except Exception as e:
        logger.error(f"Error executing code: {e}")
        return f"Error executing code: {str(e)}"
