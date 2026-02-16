import logging
from bot.client import create_client
from bot.logger import logger, setup_logger

if __name__ == "__main__":
    setup_logger()
    logger.info("Starting bot...")
    create_client()