# utils/notifications.py

import logging
import aiosqlite
from telegram import Bot, InlineKeyboardMarkup # Import InlineKeyboardMarkup
from typing import Optional # Import Optional for type hinting

# Assuming DB_FILE is defined here or imported from db_utils
from utils.db_utils import DB_FILE, GROUPS_TWEETS_DB_FILE
# Assuming APIConfig is defined here or imported from config
from utils.config import APIConfig

logger = logging.getLogger(__name__)

# Initialize bot if not already initialized globally in the main app
# Consider if this 'bot' instance should be passed from your Application/main entry point
# or if it's truly standalone here. For simplicity and to match your original code,
# we'll keep it as is, but be mindful of multiple bot instances.
bot = Bot(token=APIConfig.TELEGRAM_BOT_TOKEN)


# Define the specific group ID you want to retrieve and notify
# This ID should exist in your GROUPS_TWEETS_DB_FILE
TARGET_NOTIFICATION_GROUP_ID_FROM_DB = -4855378356

async def get_group_id_from_db(target_group_id: int) -> Optional[int]:
    """
    Retrieves a specific group ID from the GROUPS_TWEETS_DB_FILE based on its ID.
    (This function is reused from our previous discussion)

    Args:
        target_group_id: The integer ID of the group to retrieve (e.g., -4985500791).

    Returns:
        The group_id (integer) if found, otherwise None.
    """
    try:
        async with aiosqlite.connect(GROUPS_TWEETS_DB_FILE) as db:
            query = "SELECT group_id FROM groups WHERE group_id = ?"
            async with db.execute(query, (target_group_id,)) as cursor:
                result = await cursor.fetchone()
                if result:
                    logger.info(f"Successfully retrieved group ID {result[0]} from {GROUPS_TWEETS_DB_FILE}.")
                    return result[0]
                else:
                    logger.warning(f"Group ID {target_group_id} not found in {GROUPS_TWEETS_DB_FILE}.")
                    return None
    except aiosqlite.Error as e:
        logger.error(f"Database error while trying to retrieve group ID {target_group_id} from {GROUPS_TWEETS_DB_FILE}: {e}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred while retrieving group ID {target_group_id}: {e}", exc_info=True)
        return None


async def notify_admin(
    user_id: int, # Keep if user_id is relevant to the message content/context
    message: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None
):
    """
    Sends a formatted message to a specific group whose ID is retrieved from the database.
    Can optionally include an inline keyboard markup.
    """
    try:
        # 1. Fetch the actual group chat ID from the database
        group_chat_id = await get_group_id_from_db(TARGET_NOTIFICATION_GROUP_ID_FROM_DB)

        if group_chat_id is None:
            logger.warning(f"[GroupNotify] Cannot send notification. Target group ID {TARGET_NOTIFICATION_GROUP_ID_FROM_DB} not found in {GROUPS_TWEETS_DB_FILE}.")
            return

        # 2. Send the message to the retrieved group chat ID
        try:
            await bot.send_message(
                chat_id=group_chat_id, # Use the ID fetched from the database
                text=message,
                parse_mode="MarkdownV2",
                reply_markup=reply_markup
            )
            logger.info(f"[GroupNotify] Successfully sent notification to group {group_chat_id} for user {user_id}.")
        except Exception as e:
            logger.error(f"[GroupNotify] Failed to send notification to group {group_chat_id} for user {user_id}: {e}")

    except Exception as e:
        logger.error(f"[GroupNotify] Unexpected error during group notification for user {user_id}: {e}", exc_info=True)
