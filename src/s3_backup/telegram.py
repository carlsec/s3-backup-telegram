import os
import requests
from src.s3_backup.logging_setup import get_logger


def send_telegram_message(text: str) -> bool:
    """
    Send a message via Telegram Bot API.

    Reads TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from env vars.
    Returns True on success (2xx response), False on any error.
    Never raises; logs failures and returns False.
    """
    logger = get_logger()

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        logger.warning("Telegram credentials not configured; skipping notification")
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code >= 200 and response.status_code < 300:
            logger.info("Telegram notification sent successfully")
            return True
        else:
            logger.error(
                f"Telegram API returned {response.status_code}: {response.text}"
            )
            return False
    except requests.RequestException as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return False
