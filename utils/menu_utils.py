#!/usr/bin/env python3
# utils/menu_utils.py

import os
from telegram import InlineKeyboardButton, Update
from telegram.ext import ContextTypes
import re

# -------------------------------
# Bot‐message cleanup
# -------------------------------
async def clear_bot_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Delete any messages we previously sent (tracked in context.chat_data['bot_messages']).
    """
    chat_id = update.effective_chat.id
    msg_ids = context.chat_data.get("bot_messages", [])
    for m_id in msg_ids:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=m_id)
        except Exception:
            pass
    context.chat_data["bot_messages"] = []


def clear_awaiting_flags(context: ContextTypes.DEFAULT_TYPE):
    """
    Remove any user_data keys that start with 'awaiting_' or are one-off state flags.
    """
    for key in list(context.user_data.keys()):
        if key.startswith("awaiting_") or key in ("custom_quantity_order", "pending_tweet"):
            context.user_data.pop(key, None)


# -------------------------------
# Main Menu Text & Keyboard
# -------------------------------
def get_main_menu_text() -> str:
    """
    Returns the caption for the main menu.
    Note: Special characters are escaped for MarkdownV2 parse mode.
    """
    return (
        "👋 Welcome to Viral Core bot \\- Your gateway to organic marketing that matters\\!\n\n"
        "Join the free channel for free X growth tips and updates: https://t\\.me/ViralCore\\_TG\n\n"
        "Use the buttons below to:\n"
        "• 📢 Select a service\n"
        "• 💳 Purchase more posts\n"
        "• 🤝 View your affiliate program\n"
        "• 🛠️ View your balance\n"
    )


def main_menu_keyboard(is_admin=False) -> list:
    keyboard = [
        [InlineKeyboardButton("🆕 Service Menu", callback_data="service_menu")],
        [InlineKeyboardButton("🤝 Affiliate Program", callback_data="affiliate_menu")],
        [InlineKeyboardButton("💰 My Balance", callback_data="my_balance_menu")],
        [InlineKeyboardButton("💵 Task 2 Earn", callback_data="task_to_earn_menu")],
        [InlineKeyboardButton("🛠️ Support", callback_data="support_menu")]
    ]
    if is_admin:
        keyboard.append([InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_panel")])
    return keyboard

def escape_md(text: str) -> str:
    """
    Helper function to escape MarkdownV2 special characters.
    DEPRECATED: Use utils.messaging.escape_markdown_v2() instead.
    """
    from utils.messaging import escape_markdown_v2
    return escape_markdown_v2(text)
