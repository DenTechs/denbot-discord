import config
import requests
import os
import json
import logging

# Configure logging
logging.basicConfig(filename=config.LOG_FILENAME, level=config.LOG_LEVEL, format='%(asctime)s - %(levelname)s - %(message)s', filemode='a')
logger = logging.getLogger(__name__)

def test_function(boolean):
    return "blue is the best color"

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

def threedmark_gpu_performance_lookup(gpu_model):
    try:
        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01"
        }

        gpu_id_query = f"""https://www.3dmark.com/proxycon/ajax/search/gpuname?term={gpu_model.get("gpu_model")}"""
        response = requests.get(gpu_id_query, headers=headers)
        json_data_id = response.json()
        gpu_id = json_data_id[0].get("id")
        gpu_name = json_data_id[0].get("label")

        gpu_performance_query = f"https://www.3dmark.com/proxycon/ajax/medianscore?test=spy%20P&gpuId={gpu_id}&country=&scoreType=graphicsScore"
        reponse_perf = requests.get(gpu_performance_query, headers=headers)
        json_data_perf = reponse_perf.json()
        gpu_performance = round(json_data_perf.get("median"))

        return f"{gpu_name} median performance score is: {gpu_performance}"
    except Exception as e:
        logger.error(f"Error getting gpu performance: {e}")
        return f"Error getting gpu performance: {e}"
