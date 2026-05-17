import json


def format_user_message(username: str, message: str) -> str:
    """Format Discord user input as JSON for the LLM."""
    return json.dumps({"user": username, "message": message}, ensure_ascii=False)
