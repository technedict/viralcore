#!/usr/bin/env python3
# handlers/admin_handlers.py

import os
import asyncio
import logging
from datetime import datetime
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
            [InlineKeyboardButton("🏦 Withdrawal Management", callback_data="admin_withdrawals_menu")],
            [InlineKeyboardButton("🚀 Boost Service", callback_data="admin_boost_menu")],
            [InlineKeyboardButton("⚙️ Service Management", callback_data="admin_services_menu")],
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

    elif data == "admin_withdrawals_menu":
        # Delegate to withdrawal handlers
        from handlers.admin_withdrawal_handlers import admin_withdrawals_menu_handler
        await admin_withdrawals_menu_handler(update, context)
        return
    
    elif data == "admin_services_menu":
        # Delegate to service handlers
        from handlers.admin_service_handlers import admin_services_menu_handler
        await admin_services_menu_handler(update, context)
        return

    # --- Individual Action Handlers ---
    elif data == "admin_broadcast":
        await _send_admin_prompt(
            update, context, "awaiting_broadcast",
            "✉️ *Broadcast*: Please send the message to broadcast to *all* users.",
            "admin_content_menu" # Back to content menu
        )
        logger.info(f"Admin {query.from_user.id} initiated broadcast.")

    elif data == "admin_view_users" or data.startswith("admin_users_page_"):
        # Handle pagination
        page = 1
        if data.startswith("admin_users_page_"):
            try:
                page = int(data.split("_")[-1])
            except (ValueError, IndexError):
                page = 1
        
        users = get_all_users()
        
        # Use pagination utility
        from utils.admin_pagination import admin_paginator, safe_send_message_or_file, AdminExporter
        
        message_text, keyboard = admin_paginator.paginate_users(users, page)
        
        # Send with automatic fallback to CSV if too long
        await safe_send_message_or_file(
            update=update,
            context=context,
            text=message_text,
            keyboard=keyboard,
            file_generator_func=AdminExporter.export_users_to_csv,
            filename_prefix="users_export"
        )

    elif data == "admin_view_payments" or data.startswith("admin_payments_page_"):
        # Handle pagination
        page = 1
        if data.startswith("admin_payments_page_"):
            try:
                page = int(data.split("_")[-1])
            except (ValueError, IndexError):
                page = 1
        
        payments = get_all_payments()
        
        # Use pagination utility
        from utils.admin_pagination import admin_paginator, safe_send_message_or_file, AdminExporter
        
        message_text, keyboard = admin_paginator.paginate_payments(payments, page)
        
        # Send with automatic fallback to CSV if too long
        await safe_send_message_or_file(
            update=update,
            context=context,
            text=message_text,
            keyboard=keyboard,
            file_generator_func=AdminExporter.export_payments_to_csv,
            filename_prefix="payments_export"
        )

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

    elif data == "admin_export_users":
        try:
            from utils.admin_pagination import AdminExporter
            
            # Generate CSV file
            csv_path = AdminExporter.export_users_to_csv()
            
            # Send as document
            with open(csv_path, 'rb') as csv_file:
                await query.message.reply_document(
                    document=csv_file,
                    filename=f"users_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    caption="📊 Complete users export with all data fields",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("↩️ Back to Users", callback_data="admin_view_users")
                    ]])
                )
            
            # Clean up temporary file
            os.unlink(csv_path)
            logger.info(f"Admin {query.from_user.id} exported users to CSV")
            
        except Exception as e:
            logger.error(f"Failed to export users: {e}")
            await query.message.reply_text(
                "❌ Failed to export users. Please try again later.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("↩️ Back to Users", callback_data="admin_view_users")
                ]])
            )

    elif data == "admin_export_payments":
        try:
            from utils.admin_pagination import AdminExporter
            
            # Generate CSV file
            csv_path = AdminExporter.export_payments_to_csv()
            
            # Send as document
            with open(csv_path, 'rb') as csv_file:
                await query.message.reply_document(
                    document=csv_file,
                    filename=f"payments_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    caption="💳 Complete payments export with all transaction details",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("↩️ Back to Payments", callback_data="admin_view_payments")
                    ]])
                )
            
            # Clean up temporary file
            os.unlink(csv_path)
            logger.info(f"Admin {query.from_user.id} exported payments to CSV")
            
        except Exception as e:
            logger.error(f"Failed to export payments: {e}")
            await query.message.reply_text(
                "❌ Failed to export payments. Please try again later.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("↩️ Back to Payments", callback_data="admin_view_payments")
                ]])
            )


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

    elif data.startswith("admin_set_service_"):
        provider_name = data.split("admin_set_service_")[1]
        await switch_boost_provider(update, context, provider_name)
        logger.info(f"Admin {query.from_user.id} attempted to switch boost provider to {provider_name}.")


async def switch_boost_provider(update: Update, context: ContextTypes.DEFAULT_TYPE, provider_name: str):
    """
    Handles the logic for switching the active boost service provider.
    Uses new messaging system and includes validation.
    """
    from utils.messaging import render_markdown_v2, safe_send, TEMPLATES
    from utils.logging import get_logger, correlation_context, generate_correlation_id
    from utils.boost_provider_utils import PROVIDERS
    
    logger = get_logger(__name__)
    correlation_id = generate_correlation_id()
    
    with correlation_context(correlation_id):
        # Validate provider exists
        if provider_name not in PROVIDERS:
            error_text = render_markdown_v2(
                "❌ Invalid provider: {provider_name}\\. Available providers: {available}",
                provider_name=provider_name,
                available=", ".join(PROVIDERS.keys())
            )
            
            await safe_send(
                update.callback_query._bot,
                chat_id=update.callback_query.message.chat_id,
                text=error_text,
                correlation_id=correlation_id
            )
            logger.warning(f"Admin {update.callback_query.from_user.id} attempted to switch to invalid provider: {provider_name}")
            return
        
        # Attempt provider switch with proper locking
        success = ProviderConfig.set_active_provider_name(provider_name)
        
        if success:
            await clear_bot_messages(update, context)
            keyboard = [[InlineKeyboardButton("↩️ Back", callback_data="admin_boost_menu")]]
            
            # Use template for consistent messaging
            text = render_markdown_v2(
                TEMPLATES['provider_switched'],
                provider_name=provider_name.title()
            )
            
            msg = await safe_send(
                update.callback_query._bot,
                chat_id=update.callback_query.message.chat_id,
                text=text,
                correlation_id=correlation_id,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            if msg:
                context.chat_data.setdefault("bot_messages", []).append(msg.message_id)
            
            logger.info(
                f"Admin {update.callback_query.from_user.id} successfully switched boost provider to {provider_name}",
                extra={'user_id': update.callback_query.from_user.id, 'provider_name': provider_name}
            )
        else:
            error_text = "❌ Failed to switch boost provider\\. Please try again later\\."
            
            await safe_send(
                update.callback_query._bot,
                chat_id=update.callback_query.message.chat_id,
                text=error_text,
                correlation_id=correlation_id
            )
            
            logger.error(
                f"Admin {update.callback_query.from_user.id} failed to switch boost provider to {provider_name}",
                extra={'user_id': update.callback_query.from_user.id, 'provider_name': provider_name}
            )