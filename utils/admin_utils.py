# utils/admin_utils.py
import logging
from typing import List
from utils.config import APIConfig
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import ContextTypes

from utils.db_utils import (
    get_user
)
from utils.admin_db_utils import(
    get_all_payments,
    get_all_users
)
from utils.menu_utils import clear_bot_messages

logger = logging.getLogger(__name__)


async def send_message_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, admin_message, reply_text):
    # Send the withdrawal request to specified ADMIN_IDS
    for admin_id in APIConfig.ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=admin_message,
                parse_mode='Markdown'
            )
            print(f"Withdrawal details sent to admin ID: {admin_id}")
        except Exception as e:
            print(f"Failed to send withdrawal details to admin ID {admin_id}: {e}")
            # You might want to log this error or notify yourself if an admin isn't reachable
    await update.message.reply_text(reply_text, parse_mode='Markdown')

class AdminUtils:
    """
    Encapsulates admin panel logic and handlers.
    """
    def __init__(self):
        self.awaiting_flags: List[str] = [
            'awaiting_broadcast', 'awaiting_add_payment', 'awaiting_admin_add_posts',
            'awaiting_add_custom_plan', 'awaiting_update_payment',
            'awaiting_reset_affiliate', 'awaiting_reset_purchase',
            'awaiting_promotion', 'awaiting_demotion',
            'awaiting_delete_payment', 'awaiting_delete_user'
        ]

    async def panel_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Handle admin panel menu callbacks.
        """
        query = update.callback_query
        await query.answer()
        data = query.data

        # Main admin panel
        if data == 'admin_panel':
            await clear_bot_messages(update, context)
            text = '🔧 Admin Panel:\nChoose an action:'
            keyboard = [
                [InlineKeyboardButton('Broadcast', callback_data='admin_broadcast')],
                [InlineKeyboardButton('View Users', callback_data='admin_view_users')],
                [InlineKeyboardButton('View Payments', callback_data='admin_view_payments')],
                [InlineKeyboardButton('Add Payment', callback_data='admin_add_payment')],
                [InlineKeyboardButton('Add Posts', callback_data='admin_add_posts')],
                [InlineKeyboardButton('Add Custom Plan', callback_data='admin_add_custom_plan')],
                [InlineKeyboardButton('Update Payment', callback_data='admin_update_payment')],
                [InlineKeyboardButton('Reset Purchase', callback_data='admin_reset_purchase')],
                [InlineKeyboardButton('Reset Affiliate', callback_data='admin_reset_affiliate')],
                [InlineKeyboardButton('Promote User', callback_data='admin_promote_user')],
                [InlineKeyboardButton('Demote User', callback_data='admin_demote_user')],
                [InlineKeyboardButton('Delete Payment', callback_data='admin_delete_payment')],
                [InlineKeyboardButton('Delete User', callback_data='admin_delete_user')],
                [InlineKeyboardButton('🏠 Main Menu', callback_data='main_menu')]
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

        # Broadcast
        elif data == 'admin_broadcast':
            await clear_bot_messages(update, context)
            context.user_data['awaiting_broadcast'] = True
            text = 'Enter message to broadcast to all users:'
            kb = [[InlineKeyboardButton('Back', callback_data='admin_panel')]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))

        # View users
        elif data == 'admin_view_users':
            await clear_bot_messages(update, context)
            users = get_all_users()
            if users:
                header = '<b>All Users:</b>\n'
                lines = [
                    f"ID:{u[0]} {u[1].title()} Admin:{'Yes' if u[4] else 'No'}" for u in users
                ]
                text = header + '\n'.join(lines)
            else:
                text = 'No users found.'
            kb = [[InlineKeyboardButton('Back', callback_data='admin_panel')]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')

        # View payments
        elif data == 'admin_view_payments':
            await clear_bot_messages(update, context)
            payments = get_all_payments()
            if payments:
                header = '<b>All Payments:</b>\n'
                rows = []
                for p in payments:
                    pid, uid, xuser, tier, posts, rposts, cost, ts = p
                    username = get_user(uid)[1] if get_user(uid) else 'Unknown'
                    rows.append(f"{pid}: User {username} Tier:{tier} Posts:{posts}/{rposts} Cost:${cost:.2f}")
                text = header + '\n'.join(rows)
            else:
                text = 'No payments found.'
            kb = [[InlineKeyboardButton('Back', callback_data='admin_panel')]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')

        # Add payment
        elif data == 'admin_add_payment':
            await clear_bot_messages(update, context)
            context.user_data['awaiting_add_payment'] = True
            text = 'Reply: <user_id>,<x_username>,<tier>,<posts>,<cost>'
            kb = [[InlineKeyboardButton('Back', callback_data='admin_panel')]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))

        # Add posts
        elif data == 'admin_add_posts':
            await clear_bot_messages(update, context)
            context.user_data['awaiting_admin_add_posts'] = True
            text = 'Reply: <payment_id>,<posts_to_add_or_remove>'
            kb = [[InlineKeyboardButton('Back', callback_data='admin_panel')]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))

        # Add custom plan
        elif data == 'admin_add_custom_plan':
            await clear_bot_messages(update, context)
            context.user_data['awaiting_add_custom_plan'] = True
            text = 'Reply: <user_id>,<likes>,<retweets>,<comments>,<views>'
            kb = [[InlineKeyboardButton('Back', callback_data='admin_panel')]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))

        # Update payment
        elif data == 'admin_update_payment':
            await clear_bot_messages(update, context)
            context.user_data['awaiting_update_payment'] = True
            text = 'Reply: <payment_id>,<user_id>,<tier>,<new_total_cost>'
            kb = [[InlineKeyboardButton('Back', callback_data='admin_panel')]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))

        # Reset affiliate balance
        elif data == 'admin_reset_affiliate':
            await clear_bot_messages(update, context)
            context.user_data['awaiting_reset_affiliate'] = True
            text = 'Reply with user ID to reset affiliate balance'
            kb = [[InlineKeyboardButton('Back', callback_data='admin_panel')]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))

        # Reset purchase
        elif data == 'admin_reset_purchase':
            await clear_bot_messages(update, context)
            context.user_data['awaiting_reset_purchase'] = True
            text = 'Reply with user ID to reset purchases'
            kb = [[InlineKeyboardButton('Back', callback_data='admin_panel')]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))

        # Promote user
        elif data == 'admin_promote_user':
            await clear_bot_messages(update, context)
            context.user_data['awaiting_promotion'] = True
            text = 'Reply with user ID to promote'
            kb = [[InlineKeyboardButton('Back', callback_data='admin_panel')]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))

        # Demote user
        elif data == 'admin_demote_user':
            await clear_bot_messages(update, context)
            context.user_data['awaiting_demotion'] = True
            text = 'Reply with user ID to demote'
            kb = [[InlineKeyboardButton('Back', callback_data='admin_panel')]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))

        # Delete payment
        elif data == 'admin_delete_payment':
            await clear_bot_messages(update, context)
            context.user_data['awaiting_delete_payment'] = True
            text = 'Reply with payment ID to delete'
            kb = [[InlineKeyboardButton('Back', callback_data='admin_panel')]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))

        # Delete user
        elif data == 'admin_delete_user':
            await clear_bot_messages(update, context)
            context.user_data['awaiting_delete_user'] = True
            text = 'Reply with user ID to delete'
            kb = [[InlineKeyboardButton('Back', callback_data='admin_panel')]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))

        else:
            logger.warning(f"Unknown admin action: {data}")
            await query.answer('Unknown admin action.', show_alert=True)