"""
Helper utilities for BridgeOS.
Bot slot detection, invitation code generation/validation, invite link building.
"""
import os
import re
import random
import logging

import models.manager as manager_model

logger = logging.getLogger(__name__)

# Bot slot number → Telegram bot username
BOT_USERNAMES = {
    1: "FarmTranslateBot",
    2: "BridgeOS_2bot",
    3: "BridgeOS_3bot",
    4: "BridgeOS_4bot",
    5: "BridgeOS_5bot",
}


def get_bot_slot() -> int:
    """
    Get the current bot's slot number from the BOT_ID environment variable.
    BOT_ID is expected to be 'bot1' through 'bot5'.
    Returns integer 1-5.
    """
    bot_id = os.environ.get("BOT_ID", "bot1")
    try:
        return int(bot_id.replace("bot", ""))
    except ValueError:
        logger.warning(f"Invalid BOT_ID '{bot_id}', defaulting to slot 1")
        return 1


def get_bot_username_for_slot(slot: int) -> str:
    """Get Telegram bot username for a given slot number (1-5)."""
    return BOT_USERNAMES.get(slot, BOT_USERNAMES[1])


def get_invite_link(bot_username: str, code: str) -> str:
    """Build a Telegram deep-link invitation URL."""
    return f"https://t.me/{bot_username}?start=invite_{code}"


def get_current_bot_invite_link(code: str) -> tuple[str, str]:
    """
    Get current bot's username and invitation link.
    Returns (bot_username, invite_link).
    """
    slot = get_bot_slot()
    username = get_bot_username_for_slot(slot)
    link = get_invite_link(username, code)
    return username, link


def validate_invitation_code(code: str) -> bool:
    """
    Validate invitation code format.
    Expected: BRIDGE-##### (5 digits).
    """
    if not code or not isinstance(code, str):
        return False
    return bool(re.match(r"^BRIDGE-\d{5}$", code))


def generate_invitation_code(max_attempts: int = 1000) -> str:
    """
    Generate a unique invitation code in format BRIDGE-#####.
    Checks against existing active manager codes in the database.

    Raises:
        RuntimeError: If unable to generate unique code after max_attempts.
    """
    for _ in range(max_attempts):
        code = f"BRIDGE-{random.randint(10000, 99999)}"
        if not manager_model.code_exists(code):
            return code

    raise RuntimeError(
        f"Unable to generate unique invitation code after {max_attempts} attempts. "
        "Consider expanding the code range."
    )


def get_bot_token_for_slot(slot: int) -> str | None:
    """Get the Telegram bot token for a given slot from environment variables."""
    return os.environ.get(f"TELEGRAM_TOKEN_BOT{slot}")
