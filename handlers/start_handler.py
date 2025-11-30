#!/usr/bin/env python3
# handlers/start_handler.py

import logging
from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from utils.db_utils import create_user, get_user
from utils.menu_utils import get_main_menu_text, main_menu_keyboard
from utils.config import APIConfig

logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle the /start command:
    - Register the user (with optional referral code)
    - Send the main menu as a photo with inline keyboard
    """
    # Only allow in private chats
    if update.effective_chat.type != "private":
        await update.message.reply_text(
            "The /start command can only be used in a private chat with the bot."
        )
        return

    # Parse optional referral code: /start ref_<user_id>
    parts = update.message.text.split()
    referrer = None
    if len(parts) > 1 and parts[1].startswith("ref_"):
        try:
            referrer = int(parts[1][4:])
            logger.info(f"Referral link detected: user attempting to register with referrer {referrer}")
        except ValueError:
            logger.warning(f"Invalid referral code format: {parts[1]}")
            referrer = None

    user_id = update.effective_user.id
    username = update.effective_user.username or ""
    
    # Create the user record (handles referral registration with validation)
    user_created = create_user(user_id, username, referrer)
    
    if user_created and referrer:
        logger.info(f"New user {user_id} ({username}) successfully referred by {referrer}")

    # Fetch to see if this user is admin
    user_record = get_user(user_id)
    is_admin = bool(user_record and user_record['is_admin'])

    # Send main menu photo + keyboard
    msg = await update.message.reply_photo(
        photo=APIConfig.MAIN_MENU_IMAGE,
        caption=get_main_menu_text(),
        reply_markup=InlineKeyboardMarkup(main_menu_keyboard(is_admin))
    )

    # Track this message so we can delete it later if needed
    context.chat_data.setdefault("bot_messages", []).append(msg.message_id)
