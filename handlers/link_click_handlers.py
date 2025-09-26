#!/usr/bin/env python3
# handlers/link_click_handlers.py

import sqlite3
import asyncio
import logging
from telegram import Update, ChatPermissions
from telegram.ext import ContextTypes
from utils.db_utils import TWEETS_DB_FILE, GROUPS_TWEETS_DB_FILE
from utils.link_utils import get_click_count, disable_bitly_link
from handlers.raid_balance_handlers import is_raid_active

logger = logging.getLogger(__name__)

async def handle_link_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    After posting a Bitly link in a raid, track its click count.
    Once the target number of clicks is reached:
      - stop the raid
      - unlock the group
      - delete the raid message
      - if 'views' flag is True: delete the tweet record & disable the Bitly link
      - else: clear the assignment so a views‐group can pick it up
    """
    chat = update.effective_chat
    msg_id = update.message.message_id

    # Load the raid record for this group
    conn = sqlite3.connect(TWEETS_DB_FILE)
    c = conn.cursor()
    c.execute(
        "SELECT id, click_count, target_comments, views FROM tweets WHERE group_id=?",
        (chat.id,)
    )
    row = c.fetchone()
    conn.close()
    if not row:
        return

    tweet_db_id, old_clicks, target_comments, views_flag = row

    async def _checker():
        while is_raid_active.get(chat.id):
            await asyncio.sleep(2)
            current = get_click_count(update.message.text)
            if current is None:
                logger.error("Bitly click count failed")
                break

            # Update in DB
            conn2 = sqlite3.connect(TWEETS_DB_FILE)
            c2 = conn2.cursor()
            c2.execute(
                "UPDATE tweets SET click_count=? WHERE id=?",
                (current, tweet_db_id)
            )
            conn2.commit()

            if current >= target_comments:
                # Stop raid
                is_raid_active.pop(chat.id, None)

                # Unlock
                await context.bot.set_chat_permissions(
                    chat_id=chat.id,
                    permissions=ChatPermissions(can_send_messages=True)
                )
                await context.bot.send_message(
                    chat_id=chat.id,
                    text="👍 Click target reached! Raid complete."
                )
                # Delete the link message
                try:
                    await context.bot.delete_message(chat_id=chat.id, message_id=msg_id)
                except Exception:
                    pass

                # Finalize DB record
                if views_flag:
                    conn3 = sqlite3.connect(TWEETS_DB_FILE)
                    c3 = conn3.cursor()
                    c3.execute("DELETE FROM tweets WHERE id=?", (tweet_db_id,))
                    conn3.commit()
                    conn3.close()
                    disable_bitly_link(update.message.text)
                else:
                    conn3 = sqlite3.connect(TWEETS_DB_FILE)
                    c3 = conn3.cursor()
                    c3.execute("UPDATE tweets SET group_id=NULL WHERE id=?", (tweet_db_id,))
                    conn3.commit()
                    conn3.close()

                break

            conn2.close()

    context.application.create_task(_checker())
