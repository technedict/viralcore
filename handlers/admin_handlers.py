#!/usr/bin/env python3
# handlers/admin_handlers.py

import os
import asyncio
import logging
from typing import List, Tuple, Optional, Dict, Any

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

# Assuming these imports are correctly resolved in your project structure
from utils.menu_utils import clear_bot_messages, clear_awaiting_flags
from utils.admin_db_utils import (
    get_all_users,
    get_all_payments,
    # Assuming these functions exist and are imported
    # add_payment, update_payment, delete_payment,
    # reset_purchase, reset_affiliate, promote_user, demote_user, delete_user
)
from utils.boost_utils import get_boost_service_balance
from utils.db_utils import get_user_metrics, get_user
from utils.config import APIConfig
from utils.boost_provider_utils import ProviderConfig
# Assuming these are available and correctly imported from ViralMonitor
from ViralMonitor.utils.db import get_all_reply_guys_ids, get_total_amount, get_username_by_userid


logger = logging.getLogger(__name__)

# --- Helper for common admin panel prompts ---
async def _send_admin_prompt(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    flag_name: str,
    text: str,
    back_callback_data: str = "admin_panel"
) -> None:
    """
    Helper function to set a user_data flag and send a prompt message with a 'Back' button.
    """
    context.user_data[flag_name] = True
    keyboard = [[InlineKeyboardButton("Back", callback_data=back_callback_data)]]
    await clear_bot_messages(update, context)
    msg = await update.callback_query.message.reply_text(
        text=text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    context.chat_data.setdefault("bot_messages", []).append(msg.message_id)


async def admin_panel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    CallbackQuery handler for the Admin Panel.
    Renders main menu options or sub-menus and sets flags for downstream message handling.
    """
    query = update.callback_query
    await query.answer()
    data = query.data

    # print(data)

    # Always clear flags when entering any admin menu to prevent stale states
    clear_awaiting_flags(context)

    if data == "admin_panel":
        text = "🛠️ *Admin Panel* 🛠️\nSelect a category:"
        keyboard = [
            [InlineKeyboardButton("👥 User Management", callback_data="admin_users_menu")],
            [InlineKeyboardButton("💳 Payment Management", callback_data="admin_payments_menu")],
            [InlineKeyboardButton("🚀 Boost Service", callback_data="admin_boost_menu")],
            [InlineKeyboardButton("📝 Reply Guys", callback_data="admin_reply_guys_menu")],
            [InlineKeyboardButton("📝 Content & Replies", callback_data="admin_content_menu")],
            [InlineKeyboardButton("↩️ Back to Main Menu", callback_data="main_menu")]
        ]

        panel_img = APIConfig.SLIDE_IMAGES.get("admin_panel")
        await clear_bot_messages(update, context)
        if panel_img and os.path.isfile(panel_img):
            msg = await query.message.reply_photo(
                photo=panel_img,
                caption=text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            msg = await query.message.reply_text(
                text=text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        context.chat_data.setdefault("bot_messages", []).append(msg.message_id)
        logger.info(f"Admin {query.from_user.id} accessed main admin panel.")

    elif data == "admin_users_menu":
        text = "👥 *User Management*\nSelect an action:"
        keyboard = [
            [InlineKeyboardButton("View All Users", callback_data="admin_view_users")],
            [InlineKeyboardButton("Promote to Admin", callback_data="admin_promote_user")],
            [InlineKeyboardButton("Demote from Admin", callback_data="admin_demote_user")],
            [InlineKeyboardButton("Delete User", callback_data="admin_delete_user")],
            [InlineKeyboardButton("↩️ Back to Admin Panel", callback_data="admin_panel")]
        ]
        await clear_bot_messages(update, context)
        msg = await query.message.reply_text(
            text=text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        context.chat_data.setdefault("bot_messages", []).append(msg.message_id)

    elif data == "admin_payments_menu":
        text = "💳 *Payment Management*\nSelect an action:"
        keyboard = [
            [InlineKeyboardButton("View All Payments", callback_data="admin_view_payments")],
            [InlineKeyboardButton("Add Payment", callback_data="admin_add_payment")],
            [InlineKeyboardButton("Add/Remove Posts", callback_data="admin_add_posts")],
            [InlineKeyboardButton("Update Payment", callback_data="admin_update_payment")],
            [InlineKeyboardButton("Delete Payment", callback_data="admin_delete_payment")],
            [InlineKeyboardButton("Reset Purchases", callback_data="admin_reset_purchase")],
            [InlineKeyboardButton("Reset Affiliate Balance", callback_data="admin_reset_affiliate")],
            [InlineKeyboardButton("↩️ Back to Admin Panel", callback_data="admin_panel")]
        ]
        await clear_bot_messages(update, context)
        msg = await query.message.reply_text(
            text=text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        context.chat_data.setdefault("bot_messages", []).append(msg.message_id)

    elif data == "admin_boost_menu":
        text = "🚀 *Boost Service Management*\nSelect an action:"
        keyboard = [
            [InlineKeyboardButton("View Boost Service Balance", callback_data="admin_view_boost_balance")],
            [InlineKeyboardButton("Switch Boost Service", callback_data="admin_switch_boost_panel")],
            [InlineKeyboardButton("↩️ Back to Admin Panel", callback_data="admin_panel")]
        ]
        await clear_bot_messages(update, context)
        msg = await query.message.reply_text(
            text=text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        context.chat_data.setdefault("bot_messages", []).append(msg.message_id)

    
    elif data == "admin_reply_guys_menu":
        text = "📝 * Replies Management*\nSelect an action:"
        keyboard = [
            [InlineKeyboardButton("View Reply Guys", callback_data="admin_view_reply_guys")],
            [InlineKeyboardButton("Add/Remove Bonus", callback_data="admin_add_bonus")],
            [InlineKeyboardButton("Add/Remove Replies", callback_data="admin_add_replies")],
            [InlineKeyboardButton("Promote to Reply Guy", callback_data="admin_promote_reply_guy")],
            [InlineKeyboardButton("↩️ Back to Admin Panel", callback_data="admin_panel")]
        ]
        await clear_bot_messages(update, context)
        msg = await query.message.reply_text(
            text=text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        context.chat_data.setdefault("bot_messages", []).append(msg.message_id)

    elif data == "admin_content_menu":
        text = "📝 *Content & Replies Management*\nSelect an action:"
        keyboard = [
            [InlineKeyboardButton("Broadcast Message", callback_data="admin_broadcast")],
            [InlineKeyboardButton("Add Custom Plan", callback_data="admin_add_custom_plan")],
            [InlineKeyboardButton("↩️ Back to Admin Panel", callback_data="admin_panel")]
        ]
        await clear_bot_messages(update, context)
        msg = await query.message.reply_text(
            text=text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        context.chat_data.setdefault("bot_messages", []).append(msg.message_id)

    # --- Individual Action Handlers ---
    elif data == "admin_broadcast":
        await _send_admin_prompt(
            update, context, "awaiting_broadcast",
            "✉️ *Broadcast*: Please send the message to broadcast to *all* users.",
            "admin_content_menu" # Back to content menu
        )
        logger.info(f"Admin {query.from_user.id} initiated broadcast.")

    elif data == "admin_view_users":
        users = get_all_users()
        if users:
            users = sorted(users, key=lambda u: u[1].lower() if u[1] else "") # Handle potential None username
            header = "<b>All Users:</b>\n\n"
            # Adjusted column widths for better fit
            table_header = "<pre>   ID   |  Username  | Admin | Aff.Bal | X Posts| TG Posts</pre>\n"
            table_divider = "<pre>--------|------------|-------|---------|--------|---------</pre>\n"
            rows = []
            for u in users:
                user_id = u[0]
                username_raw = u[1] if u[1] else "N/A" # Use "N/A" for missing usernames
                username_display = username_raw.title()
                is_admin = "Yes" if u[4] else "No"
                total_x_posts, total_tg_posts, affiliate_balance = get_user_metrics(user_id) # Ensure this returns valid numbers
                affi_balance_str = f"${affiliate_balance:.2f}" if affiliate_balance is not None else "$0.00"
                total_x_posts_str = str(total_x_posts) if total_x_posts is not None else "0"
                total_tg_posts_str = str(total_tg_posts) if total_tg_posts is not None else "0"

                # Truncate username if too long to fit in 10 chars
                username_formatted = (username_display[:9] + '…') if len(username_display) > 10 else username_display
                row = f"<pre>{user_id:<6} | {username_formatted:<10} | {is_admin:<5} | {affi_balance_str:<7} | {total_x_posts_str:<5} | {total_tg_posts_str:<5}</pre>\n"
                rows.append(row)
            text = header + table_header + table_divider + "".join(rows)
        else:
            text = "No users found."
        keyboard = [[InlineKeyboardButton("↩️ Back", callback_data="admin_users_menu")]] # Back to users menu
        await clear_bot_messages(update, context)
        msg = await query.message.reply_text(
            text=text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        context.chat_data.setdefault("bot_messages", []).append(msg.message_id)

    elif data == "admin_view_payments":
        payments = get_all_payments()
        if payments:
            header = "<b>All Payments:</b>\n\n"
            # Payment ID (6), User ID (6), TG Handle (10), X Username (10), Tier (4), B.Posts (6), R.Posts (6), Cost (7)
            table_header = "<pre>PayID | UserID | TG Handle | X User | Tier |B.Psts|R.Psts| Cost | Date |</pre>\n"
            table_divider ="<pre>------|--------|-----------|--------|------|------|------|--------|------</pre>\n"
            rows = []
            payment_display_data = [] # To store (username.lower(), row) for sorting
            for p in payments:
                payment_id = p[0]
                user_id = p[1]
                x_username = p[8] if p[8] else "N/A"
                tier = p[2] if p[2] else "N/A"
                bpost = p[9] if p[9] is not None else 0
                rpost = p[10] if p[10] is not None else 0
                total_cost = p[4] if p[4] is not None else 0.00
                date = p[7] if p[7] else "N/A"
                tg_reactions = p[3] if tier == "tgt" else "Not TG Tier"

                user_record = get_user(user_id)
                username_tg = user_record[1] if user_record and user_record[1] else "N/A"
                username_tg_display = (username_tg.title()[:9] + '…') if len(username_tg) > 9 else username_tg.title()

                x_username_display = (x_username[:7] + '…') if len(x_username) > 7 else x_username
                tier_display = (tier[:3] + '…') if len(tier) > 3 else tier

                row = (
                    f"<pre> {payment_id:<3} | {user_id:<6} | {username_tg_display:<9} | {x_username_display:<6} | {tier_display:<3} | {bpost:<3} | {rpost:<3} | ${total_cost:<5.2f} | {date:<6}</pre>\n"
                )
                payment_display_data.append((username_tg.lower(), row)) # Store for sorting

            # Sort rows by the lowercase TG username
            sorted_rows = [r for _, r in sorted(payment_display_data, key=lambda x: x[0])]
            text = header + table_header + table_divider + "".join(sorted_rows)
        else:
            text = "No payments found."
        keyboard = [[InlineKeyboardButton("↩️ Back", callback_data="admin_payments_menu")]] # Back to payments menu
        await clear_bot_messages(update, context)
        msg = await query.message.reply_text(
            text=text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        context.chat_data.setdefault("bot_messages", []).append(msg.message_id)

    elif data == "admin_view_boost_balance":
        balance_info = await get_boost_service_balance()
        provider_name = ProviderConfig.get_active_provider_name().title()
        if balance_info and balance_info.get('balance') is not None:
            balance_str = f"{float(balance_info['balance']):.2f} {balance_info.get('currency', 'Units')}"
            text = f"💰 *Current Boost Service Balance ({provider_name})*: {balance_str}"
        else:
            text = f"❌ Could not retrieve balance for {provider_name}. It might be zero, or an error occurred."
        keyboard = [[InlineKeyboardButton("↩️ Back", callback_data="admin_boost_menu")]] # Back to boost menu
        await clear_bot_messages(update, context)
        msg = await query.message.reply_text(
            text=text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        context.chat_data.setdefault("bot_messages", []).append(msg.message_id)

    elif data == "admin_view_reply_guys":
        users = get_all_reply_guys_ids()
        if users:
            header = "<b>All Reply Guys:</b>\n\n"
            table_header = "<pre>   ID   |  Username  | Amount </pre>\n"
            table_divider = "<pre>--------|------------|--------</pre>\n"
            rows = []
            for user_id in users:
                amount = get_total_amount(user_id) # Ensure this returns a float/int
                username = get_username_by_userid(user_id)
                username_display = (username.title()[:9] + '…') if username and len(username) > 9 else (username.title() if username else "N/A")
                amount_str = f"₦{amount:.2f}" if amount is not None else "₦0.00"

                row = f"<pre>{user_id:<6} | {username_display:<10} | {amount_str:<6} </pre>\n"
                rows.append(row)
            text = header + table_header + table_divider + "".join(rows)
        else:
            text = "No Reply Guys found."
        # FIX: Change callback_data to go back to reply_guys_menu
        keyboard = [[InlineKeyboardButton("↩️ Back", callback_data="admin_reply_guys_menu")]] # <--- CHANGED THIS LINE
        await clear_bot_messages(update, context)
        msg = await query.message.reply_text(
            text=text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        context.chat_data.setdefault("bot_messages", []).append(msg.message_id)

    elif data == "admin_switch_boost_panel":
        keyboard = [
            [InlineKeyboardButton("PlugSMM", callback_data="admin_set_service_plugsmms")],
            [InlineKeyboardButton("SMMFlare", callback_data="admin_set_service_smmflare")],
            [InlineKeyboardButton("SMMStone", callback_data="admin_set_service_smmstone")],
            [InlineKeyboardButton("↩️ Back", callback_data="admin_boost_menu")] # Back to boost menu
        ]
        text = "🔄 *Select Boost Panel*"
        await clear_bot_messages(update, context)
        msg = await query.message.reply_text(
            text=text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        context.chat_data.setdefault("bot_messages", []).append(msg.message_id)

    elif data.startswith("admin_set_service_"):
        provider_name = data.split("admin_set_service_")[1]
        await switch_boost_provider(update, context, provider_name)
        logger.info(f"Admin {query.from_user.id} attempted to switch boost provider to {provider_name}.")


    # --- Prompts for actions requiring user input ---
    elif data == "admin_add_payment":
        await _send_admin_prompt(
            update, context, "awaiting_add_payment",
            "➕ *Add Payment*\nSend details as: `UserID, XUsername, Tier(tgt for telegram plans), No. of comments(0 if plan isn't TG), Posts, TotalCost,`",
            "admin_payments_menu" # Back to payments menu
        )
        logger.info(f"Admin {query.from_user.id} initiated 'add payment'.")

    elif data == "admin_add_posts":
        await _send_admin_prompt(
            update, context, "awaiting_admin_add_posts",
            "➕/➖ *Add or Remove Posts*\nSend: `PaymentID, ΔPosts` (use negative Δ to remove)",
            "admin_content_menu" # Back to content menu
        )
        logger.info(f"Admin {query.from_user.id} initiated 'add/remove posts'.")

    elif data == "admin_add_custom_plan":
        await _send_admin_prompt(
            update, context, "awaiting_add_custom_plan",
            "📋 *Add Custom Plan*\nFormat: `UserID, Likes, Retweets, Comments, Views`",
            "admin_content_menu" # Back to content menu
        )
        logger.info(f"Admin {query.from_user.id} initiated 'add custom plan'.")

    # --- Prompts for actions requiring user input ---
    elif data == "admin_add_replies" or data == "admin_add_bonus":
        if data == "admin_add_replies":
            awaiting = "awaiting_admin_add_replies"
        else:
            awaiting = "awaiting_admin_add_bonus"
        await _send_admin_prompt(
            update, context, awaiting,
            "➕ *Add Payment*\nSend details as: `UserID, TG Username, Amount, Day of the Week`",
            "admin_reply_guys_menu" # Back to payments menu
        )
        logger.info(f"Admin {query.from_user.id} initiated 'add payment'.")

    elif data == "admin_update_payment":
        await _send_admin_prompt(
            update, context, "awaiting_update_payment",
            "✏️ *Update Payment*\nSend: `PaymentID, UserID, Tier, NewTotalCost`",
            "admin_payments_menu" # Back to payments menu
        )
        logger.info(f"Admin {query.from_user.id} initiated 'update payment'.")

    elif data == "admin_reset_purchase":
        await _send_admin_prompt(
            update, context, "awaiting_reset_purchase",
            "🔄 *Reset Purchases*\nSend: `UserID`",
            "admin_payments_menu" # Back to payments menu
        )
        logger.info(f"Admin {query.from_user.id} initiated 'reset purchases'.")

    elif data == "admin_reset_affiliate":
        await _send_admin_prompt(
            update, context, "awaiting_reset_affiliate",
            "🔄 *Reset Affiliate Balance*\nSend: `UserID`",
            "admin_payments_menu" # Back to payments menu
        )
        logger.info(f"Admin {query.from_user.id} initiated 'reset affiliate balance'.")

    elif data == "admin_promote_user":
        await _send_admin_prompt(
            update, context, "awaiting_promotion",
            "⬆️ *Promote to Admin*\nSend: `UserID`",
            "admin_users_menu" # Back to users menu
        )
        logger.info(f"Admin {query.from_user.id} initiated 'promote user'.")

    elif data == "admin_promote_reply_guy":
        await _send_admin_prompt(
            update, context, "awaiting_reply_promotion",
            "⬆️ *Promote to Reply Guy*\nSend: `UserID`",
            "admin_reply_guys_menu" # Back to users menu
        )
        logger.info(f"Admin {query.from_user.id} initiated 'promote reply guy'.")

    elif data == "admin_demote_user":
        await _send_admin_prompt(
            update, context, "awaiting_demotion",
            "⬇️ *Demote from Admin*\nSend: `UserID`",
            "admin_users_menu" # Back to users menu
        )
        logger.info(f"Admin {query.from_user.id} initiated 'demote user'.")

    elif data == "admin_delete_payment":
        await _send_admin_prompt(
            update, context, "awaiting_delete_payment",
            "❌ *Delete Payment*\nSend: `PaymentID`",
            "admin_payments_menu" # Back to payments menu
        )
        logger.info(f"Admin {query.from_user.id} initiated 'delete payment'.")

    elif data == "admin_delete_user":
        await _send_admin_prompt(
            update, context, "awaiting_delete_user",
            "❌ *Delete User*\nSend: `UserID`",
            "admin_users_menu" # Back to users menu
        )
        logger.info(f"Admin {query.from_user.id} initiated 'delete user'.")


async def switch_boost_provider(update: Update, context: ContextTypes.DEFAULT_TYPE, provider_name: str):
    """
    Handles the logic for switching the active boost service provider.
    """
    success = ProviderConfig.set_active_provider_name(provider_name)
    if success:
        await clear_bot_messages(update, context)
        keyboard = [[InlineKeyboardButton("↩️ Back", callback_data="admin_boost_menu")]] # Back to boost menu
        text = f"✅ Boost provider switched to: *{provider_name.title()}*"
        msg = await update.callback_query.message.reply_text(
            text=text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        context.chat_data.setdefault("bot_messages", []).append(msg.message_id)
        logger.info(f"Admin {update.callback_query.from_user.id} successfully switched boost provider to {provider_name}.")
    else:
        await update.callback_query.message.reply_text(
            text="❌ Failed to switch boost provider. Please try again later.",
            parse_mode="Markdown"
        )
        logger.error(f"Admin {update.callback_query.from_user.id} failed to switch boost provider to {provider_name}.")