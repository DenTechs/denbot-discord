import config
import requests
import os
import logging
from thefuzz import fuzz
import json
from thefuzz import process

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
