import logging
from bot.config import Config

# Create and configure the logger once
logger = logging.getLogger("DenBot")

def setup_logger():
    logger.setLevel(Config.LOGGING_LEVEL)

    # Prevent propagation to root logger to avoid duplicate messages
    logger.propagate = False

    # Only add handler if none exist
    if not logger.handlers:
        # Console handler
        handler = logging.StreamHandler()
        handler.setLevel(Config.LOGGING_LEVEL)

        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)

        logger.addHandler(handler)
    return logger