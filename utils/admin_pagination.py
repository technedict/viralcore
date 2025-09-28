#!/usr/bin/env python3
# utils/admin_pagination.py
# Admin pagination and export utilities

import os
import csv
import tempfile
import logging
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from telegram.error import BadRequest

from utils.menu_utils import clear_bot_messages
from utils.db_utils import get_user, get_user_metrics
from utils.admin_db_utils import get_all_users, get_all_payments

logger = logging.getLogger(__name__)

# Telegram message limits
TELEGRAM_MAX_MESSAGE_LENGTH = 4096
SAFE_MESSAGE_LENGTH = 3500  # Leave some buffer for formatting
DEFAULT_PAGE_SIZE = 20

class AdminPaginator:
    """Handles pagination for admin data views."""
    
    def __init__(self, page_size: int = DEFAULT_PAGE_SIZE):
        self.page_size = page_size
    
    def paginate_users(self, users: List[Any], page: int = 1) -> Tuple[str, InlineKeyboardMarkup]:
        """
        Paginate users list and return formatted message with navigation.
        
        Args:
            users: List of user records
            page: Current page number (1-based)
        
        Returns:
            Tuple of (message_text, keyboard_markup)
        """
        if not users:
            return "No users found.", InlineKeyboardMarkup([[
                InlineKeyboardButton("↩️ Back", callback_data="admin_users_menu")
            ]])
        
        # Sort users by username
        users = sorted(users, key=lambda u: u[1].lower() if u[1] else "")
        
        total_users = len(users)
        total_pages = (total_users + self.page_size - 1) // self.page_size
        page = max(1, min(page, total_pages))  # Clamp page to valid range
        
        start_idx = (page - 1) * self.page_size
        end_idx = min(start_idx + self.page_size, total_users)
        page_users = users[start_idx:end_idx]
        
        # Build message
        header = f"<b>Users (Page {page}/{total_pages}, {total_users} total):</b>\n\n"
        table_header = "<pre>   ID   |  Username  | Admin | Aff.Bal | X Psts| TG Psts</pre>\n"
        table_divider = "<pre>--------|------------|-------|---------|-------|--------</pre>\n"
        
        rows = []
        for u in page_users:
            user_id = u[0]
            username_raw = u[1] if u[1] else "N/A"
            username_display = username_raw.title()
            is_admin = "Yes" if len(u) > 4 and u[4] else "No"
            
            try:
                total_x_posts, total_tg_posts, affiliate_balance = get_user_metrics(user_id)
                affi_balance_str = f"${affiliate_balance:.2f}" if affiliate_balance is not None else "$0.00"
                total_x_posts_str = str(total_x_posts) if total_x_posts is not None else "0"
                total_tg_posts_str = str(total_tg_posts) if total_tg_posts is not None else "0"
            except Exception as e:
                logger.error(f"Error getting metrics for user {user_id}: {e}")
                affi_balance_str = "$0.00"
                total_x_posts_str = "0"
                total_tg_posts_str = "0"
            
            # Truncate username if too long
            username_formatted = (username_display[:9] + '…') if len(username_display) > 10 else username_display
            row = f"<pre>{user_id:<6} | {username_formatted:<10} | {is_admin:<5} | {affi_balance_str:<7} | {total_x_posts_str:<5} | {total_tg_posts_str:<5}</pre>\n"
            rows.append(row)
        
        message_text = header + table_header + table_divider + "".join(rows)
        
        # Build navigation keyboard
        keyboard = []
        nav_row = []
        
        if page > 1:
            nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"admin_users_page_{page-1}"))
        if page < total_pages:
            nav_row.append(InlineKeyboardButton("➡️ Next", callback_data=f"admin_users_page_{page+1}"))
        
        if nav_row:
            keyboard.append(nav_row)
        
        # Export option
        keyboard.append([InlineKeyboardButton("📁 Export to CSV", callback_data="admin_export_users")])
        keyboard.append([InlineKeyboardButton("↩️ Back", callback_data="admin_users_menu")])
        
        return message_text, InlineKeyboardMarkup(keyboard)
    
    def paginate_payments(self, payments: List[Any], page: int = 1) -> Tuple[str, InlineKeyboardMarkup]:
        """
        Paginate payments list and return formatted message with navigation.
        
        Args:
            payments: List of payment records
            page: Current page number (1-based)
        
        Returns:
            Tuple of (message_text, keyboard_markup)
        """
        if not payments:
            return "No payments found.", InlineKeyboardMarkup([[
                InlineKeyboardButton("↩️ Back", callback_data="admin_payments_menu")
            ]])
        
        total_payments = len(payments)
        total_pages = (total_payments + self.page_size - 1) // self.page_size
        page = max(1, min(page, total_pages))  # Clamp page to valid range
        
        start_idx = (page - 1) * self.page_size
        end_idx = min(start_idx + self.page_size, total_payments)
        page_payments = payments[start_idx:end_idx]
        
        # Build message
        header = f"<b>Payments (Page {page}/{total_pages}, {total_payments} total):</b>\n\n"
        table_header = "<pre>PayID | UserID | TG Handle | X User | Tier |B.Psts|R.Psts| Cost </pre>\n"
        table_divider = "<pre>------|--------|-----------|--------|------|------|------|------</pre>\n"
        
        rows = []
        for p in page_payments:
            payment_id = p[0]
            user_id = p[1]
            x_username = p[8] if len(p) > 8 and p[8] else "N/A"
            tier = p[2] if len(p) > 2 and p[2] else "N/A"
            bpost = p[9] if len(p) > 9 and p[9] is not None else 0
            rpost = p[10] if len(p) > 10 and p[10] is not None else 0
            total_cost = p[4] if len(p) > 4 and p[4] is not None else 0.00
            
            try:
                user_record = get_user(user_id)
                username_tg = user_record[1] if user_record and user_record[1] else "N/A"
                username_tg_display = (username_tg.title()[:9] + '…') if len(username_tg) > 9 else username_tg.title()
            except Exception as e:
                logger.error(f"Error getting user record for user {user_id}: {e}")
                username_tg_display = "N/A"
            
            x_username_display = (x_username[:7] + '…') if len(x_username) > 7 else x_username
            tier_display = (tier[:3] + '…') if len(tier) > 3 else tier
            
            row = (
                f"<pre> {payment_id:<3} | {user_id:<6} | {username_tg_display:<9} | {x_username_display:<6} | "
                f"{tier_display:<3} | {bpost:<3} | {rpost:<3} | ${total_cost:<5.2f}</pre>\n"
            )
            rows.append(row)
        
        message_text = header + table_header + table_divider + "".join(rows)
        
        # Build navigation keyboard
        keyboard = []
        nav_row = []
        
        if page > 1:
            nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"admin_payments_page_{page-1}"))
        if page < total_pages:
            nav_row.append(InlineKeyboardButton("➡️ Next", callback_data=f"admin_payments_page_{page+1}"))
        
        if nav_row:
            keyboard.append(nav_row)
        
        # Export option
        keyboard.append([InlineKeyboardButton("📁 Export to CSV", callback_data="admin_export_payments")])
        keyboard.append([InlineKeyboardButton("↩️ Back", callback_data="admin_payments_menu")])
        
        return message_text, InlineKeyboardMarkup(keyboard)

class AdminExporter:
    """Handles CSV export for admin data."""
    
    @staticmethod
    def export_users_to_csv() -> str:
        """Export all users to CSV file and return file path."""
        users = get_all_users()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Create temporary file
        temp_fd, temp_path = tempfile.mkstemp(suffix=f"_users_{timestamp}.csv", prefix="viralcore_")
        
        try:
            with os.fdopen(temp_fd, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                
                # Write header
                writer.writerow([
                    'User ID', 'Username', 'Referrer ID', 'Affiliate Balance', 
                    'Is Admin', 'Is Reply Guy', 'X Posts', 'TG Posts', 'Export Timestamp'
                ])
                
                # Write user data
                for u in users:
                    user_id = u[0]
                    username = u[1] if u[1] else ""
                    referrer = u[2] if len(u) > 2 else ""
                    affiliate_balance = u[3] if len(u) > 3 else 0.0
                    is_admin = u[4] if len(u) > 4 else 0
                    is_reply_guy = u[5] if len(u) > 5 else 0
                    
                    try:
                        total_x_posts, total_tg_posts, _ = get_user_metrics(user_id)
                    except Exception:
                        total_x_posts, total_tg_posts = 0, 0
                    
                    writer.writerow([
                        user_id, username, referrer, affiliate_balance,
                        is_admin, is_reply_guy, total_x_posts, total_tg_posts,
                        timestamp
                    ])
            
            logger.info(f"Users exported to CSV: {temp_path}")
            return temp_path
            
        except Exception as e:
            logger.error(f"Error exporting users to CSV: {e}")
            os.close(temp_fd)
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise
    
    @staticmethod
    def export_payments_to_csv() -> str:
        """Export all payments to CSV file and return file path."""
        payments = get_all_payments()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Create temporary file
        temp_fd, temp_path = tempfile.mkstemp(suffix=f"_payments_{timestamp}.csv", prefix="viralcore_")
        
        try:
            with os.fdopen(temp_fd, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                
                # Write header
                writer.writerow([
                    'Payment ID', 'User ID', 'Username', 'Plan Type', 'Quantity', 
                    'Amount Paid USD', 'Payment Method', 'Transaction Ref', 'Timestamp',
                    'X Username', 'Posts', 'RPosts', 'Export Timestamp'
                ])
                
                # Write payment data
                for p in payments:
                    payment_id = p[0]
                    user_id = p[1]
                    plan_type = p[2] if len(p) > 2 else ""
                    quantity = p[3] if len(p) > 3 else 0
                    amount_paid = p[4] if len(p) > 4 else 0.0
                    payment_method = p[5] if len(p) > 5 else ""
                    transaction_ref = p[6] if len(p) > 6 else ""
                    payment_timestamp = p[7] if len(p) > 7 else ""
                    x_username = p[8] if len(p) > 8 else ""
                    posts = p[9] if len(p) > 9 else 0
                    rposts = p[10] if len(p) > 10 else 0
                    
                    # Get username
                    try:
                        user_record = get_user(user_id)
                        username = user_record[1] if user_record and user_record[1] else ""
                    except Exception:
                        username = ""
                    
                    writer.writerow([
                        payment_id, user_id, username, plan_type, quantity,
                        amount_paid, payment_method, transaction_ref, payment_timestamp,
                        x_username, posts, rposts, timestamp
                    ])
            
            logger.info(f"Payments exported to CSV: {temp_path}")
            return temp_path
            
        except Exception as e:
            logger.error(f"Error exporting payments to CSV: {e}")
            os.close(temp_fd)
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

async def safe_send_message_or_file(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    keyboard: InlineKeyboardMarkup,
    file_generator_func: Optional[callable] = None,
    filename_prefix: str = "export"
) -> None:
    """
    Safely send a message, falling back to file attachment if message is too long.
    
    Args:
        update: Telegram update object
        context: Bot context
        text: Message text to send
        keyboard: Keyboard markup
        file_generator_func: Optional function to generate CSV file if message too long
        filename_prefix: Prefix for generated filename
    """
    query = update.callback_query
    
    try:
        # Try to send as regular message first
        await clear_bot_messages(update, context)
        msg = await query.message.reply_text(
            text=text,
            parse_mode="HTML",
            reply_markup=keyboard
        )
        context.chat_data.setdefault("bot_messages", []).append(msg.message_id)
        
    except BadRequest as e:
        if "message is too long" in str(e).lower() and file_generator_func:
            logger.info("Message too long, falling back to CSV export")
            
            try:
                # Generate CSV file
                csv_path = file_generator_func()
                
                # Send as document
                with open(csv_path, 'rb') as csv_file:
                    await query.message.reply_document(
                        document=csv_file,
                        filename=f"{filename_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        caption="Data export (message was too long for chat)",
                        reply_markup=keyboard
                    )
                
                # Clean up temporary file
                os.unlink(csv_path)
                
            except Exception as export_error:
                logger.error(f"Failed to export as CSV: {export_error}")
                # Send error message as last resort
                await query.message.reply_text(
                    "❌ Data too large to display and export failed. Please contact administrator.",
                    reply_markup=keyboard
                )
        else:
            # Re-raise if not a message length issue or no fallback available
            raise

# Create global instances
admin_paginator = AdminPaginator()
admin_exporter = AdminExporter()