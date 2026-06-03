from datetime import datetime


CURRENT_DATE_TOKEN = "{current_date}"


def render_system_prompt(system_prompt: str, now: datetime | None = None) -> str:
    """Replace runtime placeholders in a system prompt."""
    current_date = (now or datetime.now()).strftime("%B %d, %Y")
    return system_prompt.replace(CURRENT_DATE_TOKEN, current_date)
