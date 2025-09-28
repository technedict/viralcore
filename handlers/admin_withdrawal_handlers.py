#!/usr/bin/env python3
# handlers/admin_withdrawal_handlers.py
# Admin handlers for withdrawal management

import logging
import re
from typing import List

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from utils.withdrawal_service import get_withdrawal_service, PaymentMode, AdminApprovalState, WithdrawalStatus
from utils.notification import notify_admin
from utils.messaging import escape_markdown_v2

logger = logging.getLogger(__name__)

async def admin_withdrawals_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin withdrawals menu."""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    # Check if user is admin
    from utils.admin_db_utils import is_admin
    if not is_admin(user.id):
        await query.edit_message_text("❌ You don't have permission to access this menu.")
        return
    
    keyboard = [
        [InlineKeyboardButton("📋 Pending Manual Withdrawals", callback_data="admin_withdrawals_pending")],
        [InlineKeyboardButton("📊 Withdrawal Statistics", callback_data="admin_withdrawals_stats")],
        [InlineKeyboardButton("🔍 Search Withdrawals", callback_data="admin_withdrawals_search")],
        [InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data="admin_panel")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    menu_text = (
        "🏦 *Admin Withdrawals Management*\n\n"
        "Select an option to manage withdrawal requests:"
    )
    
    await query.edit_message_text(
        menu_text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN_V2
    )

async def admin_pending_withdrawals_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle pending manual withdrawals view."""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    # Check if user is admin
    from utils.admin_db_utils import is_admin
    if not is_admin(user.id):
        await query.edit_message_text("❌ You don't have permission to access this feature.")
        return
    
    # Get pending manual withdrawals
    pending_withdrawals = get_withdrawal_service().get_pending_manual_withdrawals()
    
    if not pending_withdrawals:
        keyboard = [
            [InlineKeyboardButton("⬅️ Back to Withdrawals Menu", callback_data="admin_withdrawals_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "✅ *No Pending Manual Withdrawals*\n\n"
            "All manual withdrawal requests have been processed\\.",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    
    # Show first withdrawal for approval
    withdrawal = pending_withdrawals[0]
    
    # Get user info
    from utils.db_utils import get_connection, DB_FILE
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('SELECT username FROM users WHERE id = ?', (withdrawal.user_id,))
        user_row = c.fetchone()
        username = user_row[0] if user_row else f"User_{withdrawal.user_id}"
    
    withdrawal_text = (
        f"💰 *Manual Withdrawal Request*\n\n"
        f"📋 **Details:**\n"
        f"• Request ID: `{withdrawal.id}`\n"
        f"• User: [{escape_markdown_v2(username)}](tg://user?id={withdrawal.user_id})\n"
        f"• Amount: *₦{int(withdrawal.amount_ngn)}* \\(${withdrawal.amount_usd:.2f}\\)\n"
        f"• Type: {escape_markdown_v2('Affiliate' if withdrawal.is_affiliate_withdrawal else 'Standard')}\n"
        f"• Created: {escape_markdown_v2(withdrawal.created_at[:19].replace('T', ' '))}\n\n"
        f"🏦 **Bank Details:**\n"
        f"• Name: {escape_markdown_v2(withdrawal.account_name)}\n"
        f"• Number: `{withdrawal.account_number}`\n"
        f"• Bank: {escape_markdown_v2(withdrawal.bank_name)}\n\n"
        f"**Raw Details:**\n`{escape_markdown_v2(withdrawal.bank_details_raw)}`\n\n"
        f"Remaining requests: {len(pending_withdrawals)}"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"admin_approve_withdrawal_{withdrawal.id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"admin_reject_withdrawal_{withdrawal.id}")
        ],
        [InlineKeyboardButton("⏭️ Next Request", callback_data="admin_withdrawals_pending")] if len(pending_withdrawals) > 1 else [],
        [InlineKeyboardButton("⬅️ Back to Menu", callback_data="admin_withdrawals_menu")]
    ]
    
    reply_markup = InlineKeyboardMarkup([row for row in keyboard if row])  # Filter empty rows
    
    await query.edit_message_text(
        withdrawal_text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN_V2
    )

async def admin_approve_withdrawal_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle manual withdrawal approval."""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    # Check if user is admin
    from utils.admin_db_utils import is_admin
    if not is_admin(user.id):
        await query.edit_message_text("❌ You don't have permission to perform this action.")
        return
    
    # Extract withdrawal ID from callback data
    match = re.match(r"admin_approve_withdrawal_(\d+)", query.data)
    if not match:
        await query.edit_message_text("❌ Invalid withdrawal ID.")
        return
    
    withdrawal_id = int(match.group(1))
    
    # Get withdrawal details
    withdrawal = get_withdrawal_service().get_withdrawal(withdrawal_id)
    if not withdrawal:
        await query.edit_message_text("❌ Withdrawal not found.")
        return
    
    if withdrawal.payment_mode != PaymentMode.MANUAL:
        await query.edit_message_text("❌ This is not a manual withdrawal.")
        return
    
    if withdrawal.admin_approval_state != AdminApprovalState.PENDING:
        await query.edit_message_text(f"❌ Withdrawal is not pending \\(current state: {withdrawal.admin_approval_state.value}\\).", parse_mode=ParseMode.MARKDOWN_V2)
        return
    
    # Approve the withdrawal
    success = get_withdrawal_service().approve_manual_withdrawal(
        withdrawal_id=withdrawal_id,
        admin_id=user.id,
        reason=f"Approved by admin {user.username or user.first_name}"
    )
    
    if success:
        # Get user info for notification
        from utils.db_utils import get_connection, DB_FILE
        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            c.execute('SELECT username FROM users WHERE id = ?', (withdrawal.user_id,))
            user_row = c.fetchone()
            username = user_row[0] if user_row else f"User_{withdrawal.user_id}"
        
        success_text = (
            f"✅ *Withdrawal Approved Successfully\\!*\n\n"
            f"📋 **Details:**\n"
            f"• Request ID: `{withdrawal.id}`\n"
            f"• User: [{escape_markdown_v2(username)}](tg://user?id={withdrawal.user_id})\n"
            f"• Amount: *₦{int(withdrawal.amount_ngn)}* \\(${withdrawal.amount_usd:.2f}\\)\n"
            f"• Balance deducted successfully\n"
            f"• User will be notified"
        )
        
        keyboard = [
            [InlineKeyboardButton("📋 View More Pending", callback_data="admin_withdrawals_pending")],
            [InlineKeyboardButton("⬅️ Back to Menu", callback_data="admin_withdrawals_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            success_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN_V2
        )
        
        # Notify user of approval (you can implement user notification here)
        # await notify_user_withdrawal_approved(withdrawal.user_id, withdrawal)
        
    else:
        await query.edit_message_text(
            "❌ *Failed to approve withdrawal*\n\n"
            "This could be due to insufficient balance or a system error\\. "
            "Please check the logs and try again\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )

async def admin_reject_withdrawal_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle manual withdrawal rejection."""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    # Check if user is admin
    from utils.admin_db_utils import is_admin
    if not is_admin(user.id):
        await query.edit_message_text("❌ You don't have permission to perform this action.")
        return
    
    # Extract withdrawal ID from callback data
    match = re.match(r"admin_reject_withdrawal_(\d+)", query.data)
    if not match:
        await query.edit_message_text("❌ Invalid withdrawal ID.")
        return
    
    withdrawal_id = int(match.group(1))
    
    # Get withdrawal details
    withdrawal = get_withdrawal_service().get_withdrawal(withdrawal_id)
    if not withdrawal:
        await query.edit_message_text("❌ Withdrawal not found.")
        return
    
    if withdrawal.payment_mode != PaymentMode.MANUAL:
        await query.edit_message_text("❌ This is not a manual withdrawal.")
        return
    
    if withdrawal.admin_approval_state != AdminApprovalState.PENDING:
        await query.edit_message_text(f"❌ Withdrawal is not pending \\(current state: {withdrawal.admin_approval_state.value}\\).", parse_mode=ParseMode.MARKDOWN_V2)
        return
    
    # Reject the withdrawal
    success = get_withdrawal_service().reject_manual_withdrawal(
        withdrawal_id=withdrawal_id,
        admin_id=user.id,
        reason=f"Rejected by admin {user.username or user.first_name}"
    )
    
    if success:
        # Get user info for notification
        from utils.db_utils import get_connection, DB_FILE
        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            c.execute('SELECT username FROM users WHERE id = ?', (withdrawal.user_id,))
            user_row = c.fetchone()
            username = user_row[0] if user_row else f"User_{withdrawal.user_id}"
        
        success_text = (
            f"❌ *Withdrawal Rejected*\n\n"
            f"📋 **Details:**\n"
            f"• Request ID: `{withdrawal.id}`\n"
            f"• User: [{escape_markdown_v2(username)}](tg://user?id={withdrawal.user_id})\n"
            f"• Amount: *₦{int(withdrawal.amount_ngn)}* \\(${withdrawal.amount_usd:.2f}\\)\n"
            f"• Status: Rejected\n"
            f"• User will be notified"
        )
        
        keyboard = [
            [InlineKeyboardButton("📋 View More Pending", callback_data="admin_withdrawals_pending")],
            [InlineKeyboardButton("⬅️ Back to Menu", callback_data="admin_withdrawals_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            success_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN_V2
        )
        
        # Notify user of rejection (you can implement user notification here)
        # await notify_user_withdrawal_rejected(withdrawal.user_id, withdrawal)
        
    else:
        await query.edit_message_text(
            "❌ *Failed to reject withdrawal*\n\n"
            "A system error occurred\\. Please check the logs and try again\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )

async def admin_withdrawal_stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle withdrawal statistics view."""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    # Check if user is admin
    from utils.admin_db_utils import is_admin
    if not is_admin(user.id):
        await query.edit_message_text("❌ You don't have permission to access this feature.")
        return
    
    # Get withdrawal statistics
    from utils.db_utils import get_connection, DB_FILE
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        
        # Total withdrawals
        c.execute('SELECT COUNT(*) FROM withdrawals')
        total_withdrawals = c.fetchone()[0]
        
        # Pending manual withdrawals
        c.execute('''
            SELECT COUNT(*) FROM withdrawals 
            WHERE payment_mode = 'manual' AND admin_approval_state = 'pending'
        ''')
        pending_manual = c.fetchone()[0]
        
        # Completed withdrawals
        c.execute('SELECT COUNT(*) FROM withdrawals WHERE status = "completed"')
        completed_withdrawals = c.fetchone()[0]
        
        # Failed withdrawals
        c.execute('SELECT COUNT(*) FROM withdrawals WHERE status = "failed"')
        failed_withdrawals = c.fetchone()[0]
        
        # Total amounts
        c.execute('SELECT SUM(amount_usd), SUM(amount_ngn) FROM withdrawals WHERE status = "completed"')
        amounts_row = c.fetchone()
        total_usd = amounts_row[0] or 0
        total_ngn = amounts_row[1] or 0
        
        # Payment mode distribution
        c.execute('''
            SELECT payment_mode, COUNT(*) 
            FROM withdrawals 
            GROUP BY payment_mode
        ''')
        mode_stats = dict(c.fetchall())
    
    stats_text = (
        f"📊 *Withdrawal Statistics*\n\n"
        f"**Overall:**\n"
        f"• Total Requests: `{total_withdrawals}`\n"
        f"• Completed: `{completed_withdrawals}`\n"
        f"• Failed: `{failed_withdrawals}`\n"
        f"• Pending Manual: `{pending_manual}`\n\n"
        f"**Totals Processed:**\n"
        f"• USD: `${total_usd:.2f}`\n"
        f"• NGN: `₦{int(total_ngn)}`\n\n"
        f"**Payment Modes:**\n"
        f"• Automatic: `{mode_stats.get('automatic', 0)}`\n"
        f"• Manual: `{mode_stats.get('manual', 0)}`"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔄 Refresh Stats", callback_data="admin_withdrawals_stats")],
        [InlineKeyboardButton("⬅️ Back to Menu", callback_data="admin_withdrawals_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        stats_text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN_V2
    )