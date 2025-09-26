#!/usr/bin/env python3
# handlers/track_groups_handler.py

import sqlite3
import logging
from telegram import Update
from telegram.ext import ContextTypes, ChatMemberHandler
from utils.db_utils import GROUPS_TWEETS_DB_FILE

logger = logging.getLogger(__name__)

async def track_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Tracks when the bot is added to or removed from a group.
    - On join (member/administrator), inserts the group into the groups DB.
    - On leave, removes the group from the groups DB.
    """
    chat = update.effective_chat
    new_status = update.my_chat_member.new_chat_member.status

    conn = sqlite3.connect(GROUPS_TWEETS_DB_FILE)
    c = conn.cursor()

    if new_status in ("member", "administrator"):
        # Bot was added to the group
        try:
            c.execute(
                "INSERT OR IGNORE INTO groups (group_id, group_name) VALUES (?, ?)",
                (chat.id, chat.title or "")
            )
            conn.commit()
            logger.info(f"Added group to DB: {chat.title} ({chat.id})")
        except Exception as e:
            logger.error(f"Failed to add group {chat.id}: {e}")

    elif new_status == "left":
        # Bot was removed from the group
        try:
            c.execute(
                "DELETE FROM groups WHERE group_id = ?",
                (chat.id,)
            )
            conn.commit()
            logger.info(f"Removed group from DB: ID {chat.id}")
        except Exception as e:
            logger.error(f"Failed to remove group {chat.id}: {e}")

    conn.close()

# When registering in main_bot.py:
# application.add_handler(
#     ChatMemberHandler(track_groups, ChatMemberHandler.MY_CHAT_MEMBER)
# )
