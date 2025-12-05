#!/usr/bin/env python3
# handlers/menu_handlers.py

import os
import logging
import re

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputMediaPhoto,
)
from telegram.ext import ContextTypes # Keep CallbackQueryHandler import separate if adding it to main app
from telegram.error import BadRequest
from telegram.constants import ParseMode

from utils.config import APIConfig
from utils.notification import notify_admin # Import the notification function
from utils.db_utils import (
    get_user,
    get_referrer,
    get_x_purchases,
    get_user_metrics,
    get_total_referrals,
    is_reply_guy,
    decrement_affiliate_balance, # Added for withdrawal handler
    format_detailed_balances_message, # Added for withdrawal handler
    get_affiliate_balance # Added for withdrawal handler
)
from utils.menu_utils import (
    get_main_menu_text,
    main_menu_keyboard,
    clear_bot_messages,
    clear_awaiting_flags,
)
from utils.admin_db_utils import is_admin as is_user_admin
from utils.messaging import escape_markdown_v2
from handlers.payment_handler import PaymentHandler
from utils.payment_utils import initiate_flutterwave_transfer # Added for withdrawal handler
import sys, os

current_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
root_dir = os.path.abspath(os.path.join(current_dir, "..", ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from viralmonitor.utils.db import (
    get_total_amount,
    get_total_posts,
    get_user_daily_posts,
    add_post,
    remove_amount # Added for withdrawal handler
)

# Access the global dictionary from custom_order_handlers.py (Assuming it's defined there)
# IMPORTANT: This assumes 'pending_withdrawals' is a global dict in custom_order_handlers.
# If it's not, you'll need to define it here or pass it around differently.
# For simplicity, assuming it's correctly exposed/imported.

try:
    from handlers.custom_order_handlers import pending_withdrawals, pending_replies_orders
except ImportError:
    # print("Could not import pending_withdrawals from handlers.custom_order_handlers. Make sure it's defined globally there.")
    pending_withdrawals = {} # Fallback to empty dict
    pending_replies_orders = {}



logger = logging.getLogger(__name__)

# --- Helper for processing quantity and preparing next step (payment or poll details) ---
async def _process_quantity_and_set_next_step(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    qty: int,
    back_callback: str,
    plan_type: str # Added to distinguish between 'x_poll', 'tg_custom', 'x_engagement', 'direct_add', 'slow_push'
) -> tuple[str, list[list[InlineKeyboardButton]], str] | tuple[None, None, None]:
    """
    Calculates total cost, stores data, and sets the next step based on the plan type.
    Returns text, keyboard, and slide_key for rendering.
    """
    text = ""
    keyboard: list[list[InlineKeyboardButton]] = []
    slide_key = "qty_confirmation" # Default slide key
    total_cost = 0.0 # Initialize total_cost

    context.user_data["posts"] = qty # Use 'posts' for engagement, 'quantity' might be better for followers/votes
    context.user_data["ordered_quantity"] = qty # More generic for all order types

    # Clear previous specific flags, set current one
    context.user_data.pop("is_tg_custom_order", None)
    context.user_data.pop("is_x_poll_order", None)
    context.user_data.pop("is_x_engagement_order", None)
    context.user_data.pop("is_direct_add_order", None)
    context.user_data.pop("is_slow_push_order", None)

    # Set plan type for context.user_data for later use (e.g., in payment success handler)
    context.user_data["current_plan_type"] = plan_type

    if plan_type == "tg_custom":
        context.user_data["is_tg_custom_order"] = True
        tqty = context.user_data.get("tqty")
        if not tqty:
            await update.callback_query.message.reply_text("Something went wrong. Please select amount of comments first.")
            return None, None, None
        unit_price = 0.02 # $0.1 per 5 comments -> $0.02 per 1 comment
        total_cost = (tqty * unit_price) * qty
        context.user_data["tqty"] = tqty # Ensure tqty is stored if it's dynamic
        escaped_total = escape_markdown_v2(f"${total_cost:.2f}")
        text = (
            f"For {qty} posts with {tqty} comments each at $0\.1 per 5 comments, your total is {escaped_total}\n\n"
            "Proceed to payment?"
        )
        keyboard = [
            [InlineKeyboardButton("Crypto", callback_data="payment_crypto"),
             InlineKeyboardButton("Bank", callback_data="payment_bank")],
            [InlineKeyboardButton("⬅️ Back", callback_data=back_callback)]
        ]
    elif plan_type == "x_poll":
        context.user_data["is_x_poll_order"] = True
        unit_price = 0.03 # $0.3 per 10 Votes -> $0.03 per vote
        total_cost = qty * unit_price
        # Now, direct to payment first
        escaped_total = escape_markdown_v2(f"${total_cost:.2f}")
        text = (
            f"You've selected {qty} Votes at $0\.3 per 10 Votes, totaling {escaped_total}\.\n\n"
            "Proceed to payment?"
        )
        keyboard = [
            [InlineKeyboardButton("Crypto", callback_data="payment_crypto"),
             InlineKeyboardButton("Bank", callback_data="payment_bank")],
            [InlineKeyboardButton("⬅️ Back", callback_data=back_callback)]
        ]
    elif plan_type == "x_engagement": # For general X engagement tiers (t1-t5)
        tier_name = context.user_data.get("tier")
        if not tier_name:
            await update.callback_query.message.reply_text("Something went wrong. Please select a tier first.")
            return None, None, None
        unit_price = APIConfig.TIER_DETAILS[tier_name]["price"]
        total_cost = qty * unit_price
        escaped_unit = escape_markdown_v2(f"${unit_price:.2f}")
        escaped_total = escape_markdown_v2(f"${total_cost:.2f}")
        text = (
            f"For {qty} posts at {escaped_unit} per post, your total is {escaped_total}\n\n"
            "Proceed to payment?"
        )
        keyboard = [
            [InlineKeyboardButton("Crypto", callback_data="payment_crypto"),
             InlineKeyboardButton("Bank", callback_data="payment_bank")],
            [InlineKeyboardButton("⬅️ Back", callback_data=back_callback)]
        ]
    elif plan_type == "direct_add":
        context.user_data["is_direct_add_order"] = True
        if qty < APIConfig.FOLLOWER_DETAILS["direct_add"]["min_qty"]:
            await update.callback_query.message.reply_text(
                f"Minimum quantity for Direct Add is {APIConfig.FOLLOWER_DETAILS['direct_add']['min_qty']} followers."
            )
            return None, None, None
        # Price is per 1k followers, so adjust unit price
        unit_price_per_follower = APIConfig.FOLLOWER_DETAILS["direct_add"]["price_per_k"] / 1000
        total_cost = qty * unit_price_per_follower
        escaped_price = escape_markdown_v2(f"${APIConfig.FOLLOWER_DETAILS['direct_add']['price_per_k']:.2f}")
        escaped_total = escape_markdown_v2(f"${total_cost:.2f}")
        text = (
            f"You've selected {qty} Direct Add Followers at {escaped_price} per 1k, "
            f"totaling {escaped_total}\.\n\nProceed to payment?"
        )
        keyboard = [
            [InlineKeyboardButton("Crypto", callback_data="payment_crypto"),
             InlineKeyboardButton("Bank", callback_data="payment_bank")],
            [InlineKeyboardButton("⬅️ Back", callback_data=back_callback)]
        ]
    elif plan_type == "slow_push":
        context.user_data["is_slow_push_order"] = True
        if qty < APIConfig.FOLLOWER_DETAILS["slow_push"]["min_qty"]:
            await update.callback_query.message.reply_text(
                f"Minimum quantity for Slow Push is {APIConfig.FOLLOWER_DETAILS['slow_push']['min_qty']} followers (in multiples of 10)."
            )
            return None, None, None
        # if qty % 10 != 0:
        #     await update.callback_query.message.reply_text(
        #         "Slow Push quantity must be in multiples of 10."
        #     )
        #     return None, None, None

        # Price is per 10 followers
        unit_price_per_follower = APIConfig.FOLLOWER_DETAILS["slow_push"]["price_per_10"] / 10
        total_cost = qty * unit_price_per_follower
        escaped_price = escape_markdown_v2(f"${APIConfig.FOLLOWER_DETAILS['slow_push']['price_per_10']:.2f}")
        escaped_total = escape_markdown_v2(f"${total_cost:.2f}")
        text = (
            f"You've selected {qty} Slow Push Followers at {escaped_price} per 10, "
            f"totaling {escaped_total}\. Enter amount of days to push \(1\-200\)\:\n\n"
        )
        context.user_data["awaiting_slow_push_input"] = True # Flag for message handler
        keyboard = [
            [InlineKeyboardButton("⬅️ Back", callback_data="followers_plans_x")]
        ]
        # Retrieve order details from context.user_data
        context.user_data["ordered_quantity"] = qty
        context.user_data["total_cost"] = total_cost 

    elif plan_type == "tg_premium":
        context.user_data["is_tg_premium_order"] = True
        if qty < 50:
            await update.callback_query.message.reply_text(
                f"Minimum quantity for Premium Member is 50 followers (in multiples of 10)."
            )
            return None, None, None

        # Price is per 10 followers
        unit_price_per_follower = 3.5 / 50
        total_cost = qty * unit_price_per_follower
        escaped_total = escape_markdown_v2(f"${total_cost:.2f}")
        text = (
            f"You've selected {qty} Premium Members at $3\.5 per 50, "
            f"totaling {escaped_total}\.\n\nProceed to payment?"
        )
        keyboard = [
            [InlineKeyboardButton("Crypto", callback_data="payment_crypto"),
             InlineKeyboardButton("Bank", callback_data="payment_bank")],
            [InlineKeyboardButton("⬅️ Back", callback_data=back_callback)]
        ]
    else:
        await update.callback_query.message.reply_text("Something went wrong. Please select a valid plan first.")
        return None, None, None

    context.user_data["total_cost"] = total_cost
    context.user_data["ordered_quantity"] = qty
    return text, keyboard, slide_key

# --- Main Menu Handler ---
async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Central callback_query handler for all menu options.
    """
    query = update.callback_query
    try:
        await query.answer()
    except Exception as e:
        logger.error("Failed to answer callback query: %s", e)
    data = query.data
    user_id = query.from_user.id
    username = query.from_user.username or ""

    # Ensure user exists in database (create if not exists with proper defaults)
    from utils.db_utils import create_user
    create_user(user_id, username)

    # Prepare user info
    user_rec = get_user(user_id)
    is_admin = is_user_admin(user_id)
    ph: PaymentHandler = context.bot_data["payment_handler"]

    # Clear any one-off awaiting flags at the start of any menu interaction
    clear_awaiting_flags(context)

    # Initialize variables for the final message send
    reply_text_content = ""
    reply_keyboard: list[list[InlineKeyboardButton]] = []
    current_slide_key = None

    # --- Dispatch Logic ---

    if data == "main_menu":
        # 1) If they were mid-payment, cancel those background tasks
        for key in ["transaction_timeout_task", "transaction_timeout_job", "bank_poll_task"]:
            task_or_job = context.user_data.pop(key, None)
            if task_or_job:
                if hasattr(task_or_job, 'cancel') and callable(task_or_job.cancel):
                    task_or_job.cancel()
                elif hasattr(task_or_job, 'schedule_removal') and callable(task_or_job.schedule_removal):
                    task_or_job.schedule_removal()

        # Clear any specific order flags when returning to main menu
        context.user_data.pop("current_plan_type", None)
        context.user_data.pop("is_tg_custom_order", None)
        context.user_data.pop("is_x_poll_order", None)
        context.user_data.pop("is_x_engagement_order", None)
        context.user_data.pop("is_direct_add_order", None)
        context.user_data.pop("is_slow_push_order", None)
        context.user_data.pop("tqty", None) # Clear comments quantity too
        context.user_data.pop("tier", None) # Clear tier too

        reply_text_content = get_main_menu_text()
        reply_keyboard = main_menu_keyboard(is_admin=is_admin)
        current_slide_key = "main_menu"

    # ... (existing affiliate, service_balance, support handlers - no changes needed) ...

    elif data == "service_menu":
        reply_text_content = "Please select one of the service plan categories\\:"
        reply_keyboard = [
            [InlineKeyboardButton("Twitter/X", callback_data="x_plans")],
            [InlineKeyboardButton("Telegram", callback_data="tg_plans")],
            # Check if user is a reply guy, if so, add the panel option
            ([InlineKeyboardButton("Reply Guys Panel", callback_data="reply_guys_panel")] if is_reply_guy(user_id) else []),
            [InlineKeyboardButton("⬅️ Back", callback_data="main_menu")]
        ]
        current_slide_key = "service_menu"

    # --- Affiliate Program Handler ---
    elif data == "affiliate_menu":
        referrer_info = get_referrer(user_id)
        if referrer_info:
            referrer_id = referrer_info[0]
            referrer_username = referrer_info[1] if referrer_info[1] else "No username"
            referrer_msg = f"Your referrer: [{escape_markdown_v2(referrer_username)}](tg://user?id={referrer_id})\\."
        else:
            referrer_msg = "You don't currently have a referrer\\."

        total_referrals = get_total_referrals(user_id)

        reply_text_content = (
            f"🤝 *Affiliate Program*\n\n"
            f"Share your referral link to earn commissions on new purchases\\!\n"
            f"Your referral link: `https://t\\.me/{escape_markdown_v2(context.bot.username)}?start=ref_{user_id}`\n\n"
            f"You have referred *{total_referrals}* users\\.\n"
            f"{referrer_msg}\n\n"
            f"You earn *10%* of every successful payment made by your referrals\\." 
        )
        reply_keyboard  = [
            [InlineKeyboardButton("↩️ Balance", callback_data="affiliate_balance_menu")],
            [InlineKeyboardButton("↩️ Back to Main Menu", callback_data="main_menu")]
        ]


    # --- My Balance Handler ---
    elif data == "affiliate_balance_menu":
        balance = get_affiliate_balance(user_id)
        context.user_data["ref_balance"] = balance
        total_referrals = get_total_referrals(user_id)

        # Escape the decimal balance to handle the period
        escaped_balance = escape_markdown_v2(f"{balance:.2f}")
        
        reply_text_content = (
            f"💰 *My Balance*\n\n"
            f"Your current affiliate balance: *${escaped_balance}*\n"
            f"Total users referred by you: *{total_referrals}*\n\n"
            f"You can use your balance to pay for services or request a payout\\."
        )
        reply_keyboard  = [
            [InlineKeyboardButton("💸 Withdraw Balance", callback_data="withdraw")],
            [InlineKeyboardButton("↩️ Back to Main Menu", callback_data="main_menu")]
        ]

    # --- My Balance Handler ---
    elif data == "my_balance_menu":
        # Retrieve both remaining engagement and affiliate balance
        total_x_posts, total_tg_posts, affiliate_balance = get_user_metrics(user_id)
        total_referrals = get_total_referrals(user_id) # Still useful for context

        # Escape the decimal balance to handle the period
        escaped_balance = escape_markdown_v2(f"{affiliate_balance:.2f}")
        
        reply_text_content = (
            f"💰 *My Balance & Engagements*\n\n"
            f"📊 *Posts Left:*\n"
            f"🐦 X \\(Twitter\\): {total_x_posts} posts\n"
            f"✈️ Telegram: {total_tg_posts} posts\n\n"
            f"💸 *Affiliate Balance:* ${escaped_balance}\n"
        )
        reply_keyboard = [
            [InlineKeyboardButton("View Detailed Balance", callback_data="balance_details")],
            [InlineKeyboardButton("↩️ Back to Main Menu", callback_data="main_menu")]
        ]

    elif data == "balance_details":
        # Get the formatted detailed message
        reply_text_content = format_detailed_balances_message(user_id)

        # Define the keyboard for this panel
        reply_keyboard = [
            [InlineKeyboardButton("↩️ Back to My Balance", callback_data="my_balance_menu")],
            [InlineKeyboardButton("🏡 Back to Main Menu", callback_data="main_menu")]
        ]


    # --- Task 2 Earn Handler (Placeholder) ---
    elif data == "task_to_earn_menu":
        reply_text_content = (
            f"✅ *Task 2 Earn*\n\n"
            f"This section is under development\\. Soon you'll be able to earn credits by completing simple tasks\\!"
        )
        reply_keyboard  = [
            # Add task-specific buttons here if needed later
            [InlineKeyboardButton("↩️ Back to Main Menu", callback_data="main_menu")]
        ]

    # --- Support Handler ---
    elif data == "support_menu":
        # Replace with your actual support details or a link
        support_channel_link = "https://t.me/ViralCore_Support" # Replace with your channel/group
        support_admin_username = "@ViralCore_Support" # Replace with your admin's username

        reply_text_content = (
            f"ℹ️ *Support*\n\n"
            f"If you have any questions or encounter issues, please contact our support team:\n"
            f"\\- Telegram Channel: [Our Support Channel]({escape_markdown_v2(support_channel_link)})\n"
            f"\\- Direct Admin: {escape_markdown_v2(support_admin_username)}\n\n"
            f"We are here to help you\\!"
        )
        reply_keyboard = [
            [InlineKeyboardButton("Join Support Channel", url=support_channel_link)],
            [InlineKeyboardButton("↩️ Back to Main Menu", callback_data="main_menu")]
        ]


    elif data == "x_plans":
        # Ensure only relevant flags are set/cleared for X plans
        context.user_data.pop("tg_custom", None) # Ensure TG custom is off
        context.user_data.pop("x_poll", None) # Ensure X poll is off if it was set
        context.user_data.pop("tier", None) # Clear tier from previous X engagement

        reply_text_content = "X Service Plans\:\n\n"
        reply_keyboard = [
            [InlineKeyboardButton("Engagement", callback_data="engagement_plans_x")],
            [InlineKeyboardButton("Followers", callback_data="followers_plans_x")], # This is the new entry point
            [InlineKeyboardButton("Poll Plan", callback_data="poll_plans_x")],
            [InlineKeyboardButton("Special Plans", callback_data="special_plans")],
            [InlineKeyboardButton("⬅️ Back", callback_data="service_menu")]
        ]
        current_slide_key = "x_plans_menu"

    elif data == "engagement_plans_x":
        context.user_data.pop("x_poll", None) # Ensure X poll is off
        context.user_data["x_engagement"] = True # Set flag for X engagement plans current_plan_type
        # context.user_data.pop("tier", None) # Let this be handled by x_tier_ callbacks
        reply_text_content = (
            "X Service Plans\:\n\n"
            "Select a Tier after choosing your preferred plan\:"
        )
        reply_keyboard = [
            [InlineKeyboardButton("Tier 1 Engagement", callback_data="x_tier_t1")],
            [InlineKeyboardButton("Tier 2 Engagement", callback_data="x_tier_t2")],
            [InlineKeyboardButton("Tier 3 Engagement", callback_data="x_tier_t3")],
            [InlineKeyboardButton("Tier 4 Engagement", callback_data="x_tier_t4")],
            [InlineKeyboardButton("Tier 5 Engagement", callback_data="x_tier_t5")], # Corrected to t5
            # Custom plans options
            [InlineKeyboardButton("🎯 My Custom Plans", callback_data="custom_plans_selection")],
            [InlineKeyboardButton("📋 View My Plans", callback_data="my_custom_plans")],
            [InlineKeyboardButton("Custom (Contact Support)", callback_data="custom_order")],
            [InlineKeyboardButton("⬅️ Back", callback_data="x_plans")]
        ]
        current_slide_key = "engagement_plans_x"

    elif data == "followers_plans_x": # New Followers menu
        # Clear any other X-related flags for a clean start
        context.user_data.pop("x_custom", None) # This seems like a broad flag, might need specific handling
        context.user_data.pop("x_poll", None)
        context.user_data.pop("tier", None) # For engagement tiers

        reply_text_content = (
            "X Follower Plans\:\n\n"
            "Select a plan\:"
        )
        reply_keyboard = [
            [InlineKeyboardButton("Direct Add", callback_data="direct_add_select_qty")], # New callback
            [InlineKeyboardButton("Giveaway", callback_data="giveaway")],
            [InlineKeyboardButton("Slow Push (Daily)", callback_data="slow_push_select_qty")], # New callback
            [InlineKeyboardButton("⬅️ Back", callback_data="x_plans")]
        ]
        current_slide_key = "followers_plans_x"

    elif data == "direct_add_select_qty": # New handler for Direct Add quantity
        # Set relevant flags or context for direct add
        context.user_data["current_plan_type"] = "direct_add"
        escaped_price = escape_markdown_v2(f"${APIConfig.FOLLOWER_DETAILS['direct_add']['price_per_k']:.2f}")
        reply_text_content = (
            f"Direct Add Followers\:\n\n"
            f"Price\: {escaped_price} per 1000 followers\.\n"
            f"Minimum\: {APIConfig.FOLLOWER_DETAILS['direct_add']['min_qty']} followers\.\n\n"
            "Please select the number of followers you would like to purchase\:"
        )
        reply_keyboard = [
            [InlineKeyboardButton("1,000", callback_data="qty_direct_add_1000")],
            [InlineKeyboardButton("2,000", callback_data="qty_direct_add_2000")],
            [InlineKeyboardButton("5,000", callback_data="qty_direct_add_5000")],
            [InlineKeyboardButton("10,000", callback_data="qty_direct_add_10000")],
            [InlineKeyboardButton("Custom Quantity", callback_data="custom_quantity_direct_add")], # New custom quantity
            [InlineKeyboardButton("⬅️ Back", callback_data="followers_plans_x")]
        ]
        current_slide_key = "direct_add_qty_selection"

    elif data == "slow_push_select_qty": # New handler for Slow Push quantity
        # Set relevant flags or context for slow push
        context.user_data["current_plan_type"] = "slow_push"
        escaped_price = escape_markdown_v2(f"${APIConfig.FOLLOWER_DETAILS['slow_push']['price_per_10']:.2f}")
        reply_text_content = (
            f"Slow Push Followers\:\n\n"
            f"Price\: {escaped_price} per 10 followers\.\n"
            f"Minimum\: {APIConfig.FOLLOWER_DETAILS['slow_push']['min_qty']} followers \(in multiples of 10\)\.\n\n"
            "Please select the number of followers you would like to purchase\:"
        )
        reply_keyboard = [
            [InlineKeyboardButton("100", callback_data="qty_slow_push_100")],
            [InlineKeyboardButton("250", callback_data="qty_slow_push_250")],
            [InlineKeyboardButton("500", callback_data="qty_slow_push_500")],
            [InlineKeyboardButton("1,000", callback_data="qty_slow_push_1000")],
            [InlineKeyboardButton("Custom Quantity", callback_data="custom_quantity_slow_push")], # New custom quantity
            [InlineKeyboardButton("⬅️ Back", callback_data="slow_push")]
        ]
        current_slide_key = "slow_push_qty_selection"

    elif data == "giveaway":
        support_username = "ViralCore_Support"
        support_link = f"https://t.me/{support_username}"

        reply_text_content = (
            "This method publishes a giveaway ad for you on X with the task to follow your account\.\n\n"
            "All followers are organic and are from real and active users\.\n\n"
            "To discuss the pricing and specific details please tap the button to contact support\."
        )
        reply_keyboard = [
            [InlineKeyboardButton("Contact Support Directly", url=support_link)],
            [InlineKeyboardButton("⬅️ Back", callback_data="followers_plans_x")]
        ]
        current_slide_key = "giveaway_plan"

    elif data == "poll_plans_x":
        context.user_data["x_poll"] = True # Keep this flag for future checks
        context.user_data["current_plan_type"] = "x_poll"
        # No need to pop 'tier' or 'tg_custom' here, handled by x_plans entry point
        # context.user_data.pop("tier", None) # Not needed as _process_quantity handles specific flags
        # context.user_data.pop("tg_custom", None) # Not needed as _process_quantity handles specific flags

        reply_text_content = (
            "Twitter Poll Plan\:\n\n"
            "$0\.3 per 10 VOTES"
            "\n\nPlease select the number of Votes you would like to purchase\:"
        )
        reply_keyboard = [
            [InlineKeyboardButton("10", callback_data="qty_x_poll_10"),
             InlineKeyboardButton("25", callback_data="qty_x_poll_25")],
            [InlineKeyboardButton("50", callback_data="qty_x_poll_50"),
             InlineKeyboardButton("100", callback_data="qty_x_poll_100")],
            [InlineKeyboardButton("Custom Quantity", callback_data="custom_quantity_poll")],
            [InlineKeyboardButton("⬅️ Back", callback_data="x_plans")]
        ]
        current_slide_key = "poll_plans_x"

    elif data == "special_plans":
        context.user_data["special_plans"] = True
        reply_text_content = (
            "X Specific Plans\n\n"
            "Need extra metrics like\: likes, comments, profile clicks, link clicks, detail expands, views, impressions, reposts and more\."
        )
        support_username = "ViralCore_Support"
        support_link = f"https://t.me/{support_username}"

        reply_keyboard = [
            [InlineKeyboardButton("Contact Support Directly", url=support_link)],
            [InlineKeyboardButton("⬅️ Back", callback_data="x_plans")]
        ]
        current_slide_key = "special_plans"

    elif data == "tg_plans":
        context.user_data["tg_custom"] = True
        context.user_data.pop("tg_engagement", None)
        context.user_data.pop("tg_automation", None)
        context.user_data.pop("tg_premium", None)
        context.user_data.pop("tg_extra_plans", None)
        context.user_data.pop("x_poll", None)

        reply_text_content = "Telegram Service Plans\:\n\n"
        reply_keyboard = [
            [InlineKeyboardButton("Engagement", callback_data="engagement_plans_tg")],
            [InlineKeyboardButton("Premium Members", callback_data="premium_plans_tg")],
            [InlineKeyboardButton("Extra Plans", callback_data="extra_plans_tg")],
            [InlineKeyboardButton("Automated Services", callback_data="automated_plans_tg")],
            [InlineKeyboardButton("⬅️ Back", callback_data="service_menu")]
        ]
        current_slide_key = "tg_plans_menu"

    elif data == "engagement_plans_tg":
        context.user_data["tg_engagement"] = True
        context.user_data.pop("tqty", None)
        reply_text_content = (
            "Telegram Engagement Plan\:\n\n"
            "$0\.1 per 5 COMMENTS, reactions inclusive"
            "\n\nPlease select the number of COMMENTS you would like to purchase\:"
        )
        reply_keyboard = [
            [InlineKeyboardButton("5", callback_data="tgc_5"),
             InlineKeyboardButton("10", callback_data="tgc_10")],
            [InlineKeyboardButton("15", callback_data="tgc_15"),
             InlineKeyboardButton("20", callback_data="tgc_20")],
            [InlineKeyboardButton("25", callback_data="tgc_25"),
             InlineKeyboardButton("30", callback_data="tgc_30")],
            [InlineKeyboardButton("⬅️ Back", callback_data="tg_plans")]
        ]
        current_slide_key = "engagement_plans_tg"

    elif data == "automated_plans_tg":
        context.user_data["tg_automation"] = True
        context.user_data["current_plan_type"] = "automated_plans_tg"
        context.user_data["total_cost"] = 10.0
        reply_text_content = (
            "Telegram Automation\n\n"
            "Get a personal bot that constantly monitors your channel for new posts and automatically submits them for raiding"
            "\n\nAt $10 per month\. Proceed to payment?"
        )
        reply_keyboard = [
            [InlineKeyboardButton("Crypto", callback_data="payment_crypto"),
            InlineKeyboardButton("Bank", callback_data="payment_bank")],
            [InlineKeyboardButton("⬅️ Back", callback_data="tg_plans")]
        ]
        current_slide_key = "automated_plans_tg"

    elif data == "premium_plans_tg":
        context.user_data["tg_premium"] = True
        context.user_data["custom_plan_type"] = "tg_premium"
        context.user_data["awaiting_custom_quantity_input"] = True
        context.user_data["custom_premium_quantity_order"] = True
        reply_text_content = (
            "Telegram Premium Members and Views\n\n"
            "Get Premium members to join your channel and consistently view over the next 200 days"
            "\n\nAt $3\.5 per 50 members, reply with the number of MEMBERS you would like to purchase \(Min\: 50\)\:"
        )
        reply_keyboard = [
            [InlineKeyboardButton("⬅️ Back", callback_data="tg_plans")]
        ]
        current_slide_key = "premium_plans_tg"

    elif data == "extra_plans_tg":
        context.user_data["tg_extra_plans"] = True
        reply_text_content = (
            "Telegram Extra Plans\n\n"
            "Need specific likes, comments, views, new members, and more\."
        )
        support_username = "ViralCore_Support"
        support_link = f"https://t.me/{support_username}"

        reply_keyboard = [
            [InlineKeyboardButton("Contact Support Directly", url=support_link)],
            [InlineKeyboardButton("⬅️ Back", callback_data="tg_plans")]
        ]
        current_slide_key = "extra_plans_tg"

    elif data == "custom_order":
        reply_text_content = (
            "Please Contact Support to meet your requirements\:\n\n"
            "@ViralCore\\_Support on Telegram\n"
        )
        reply_keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="main_menu")]]
        current_slide_key = "custom_order_contact"

    elif data.startswith("x_tier_"):
        tier = data.split("_", 2)[2]
        context.user_data["tier"] = tier # Store the selected tier
        details = APIConfig.TIER_DETAILS[tier]
        escaped_price = escape_markdown_v2(f"${details['price']:.2f}")
        escaped_description = escape_markdown_v2(details['description'])
        reply_text_content = (
            f"*Tier {tier.upper()} Selected*\n\n"
            f"{escaped_description}\n"
            f"Price\: *{escaped_price}* per post\n\n"
            "Confirm?"
        )
        reply_keyboard = [
            [InlineKeyboardButton("✅ Yes", callback_data="confirm_amount")],
            [InlineKeyboardButton("⬅️ Back", callback_data="engagement_plans_x")]
        ]
        current_slide_key = f"tier_{tier}"

    elif data == "confirm_amount": # This is for X Engagement tiers after "✅ Yes"
        # The 'tier' should already be in context.user_data from x_tier_ callback
        reply_text_content = "Please select the number of posts you would like to purchase\:"
        reply_keyboard = [
            [InlineKeyboardButton("10", callback_data="qty_x_engagement_10"), # Change callback for clarity
             InlineKeyboardButton("25", callback_data="qty_x_engagement_25")],
            [InlineKeyboardButton("50", callback_data="qty_x_engagement_50"),
             InlineKeyboardButton("100", callback_data="qty_x_engagement_100")],
            [InlineKeyboardButton("Custom Quantity", callback_data="custom_quantity_x_engagement")], # Change callback for clarity
            [InlineKeyboardButton("⬅️ Back", callback_data="engagement_plans_x")]
        ]
        current_slide_key = "confirm_amount_selection"

    elif data.startswith("tgc_"): # TG engagement comment quantity selected
        tqty = int(data.split("_", 1)[1])
        context.user_data["tqty"] = tqty
        reply_text_content = "Please select the number of posts you would like to purchase\:"
        reply_keyboard = [
            # First row: 10 and 25
            [
                InlineKeyboardButton(callback_data='qty_tg_custom_10', text='10'),
                InlineKeyboardButton(callback_data='qty_tg_custom_25', text='25')
            ],
            # Second row: 50 and 100 (if you want them on the same row)
            [
                InlineKeyboardButton(callback_data='qty_tg_custom_50', text='50'),
                InlineKeyboardButton(callback_data='qty_tg_custom_100', text='100')
            ],
            # Third row: Custom Quantity (on its own row)
            [
                InlineKeyboardButton(callback_data='custom_quantity_tg_custom', text='Custom Quantity')
            ],
            # Fourth row: Back button (on its own row)
            [
                InlineKeyboardButton(callback_data='engagement_plans_tg', text='⬅️ Back')
            ]
        ]
        current_slide_key = "tgc_posts_selection"

    elif data.startswith("qty_"):
        # This regex will extract the plan type and quantity.
        # e.g., "qty_x_engagement_10" -> plan_type="x_engagement", qty=10
        # "qty_poll_25" -> plan_type="poll", qty=25
        # "qty_direct_add_1000" -> plan_type="direct_add", qty=1000
        # "qty_slow_push_100" -> plan_type="slow_push", qty=100
        # print(data)
        match = re.match(r"qty_([a-zA-Z_]+)_(\d+)", data)
        if match:
            plan_type_from_data = match.group(1)
            qty_val = int(match.group(2))
            context.user_data["qty"] = qty_val
            
            # Use plan_type_from_data to decide how to process
            reply_text_content, reply_keyboard, current_slide_key = await _process_quantity_and_set_next_step(
                update, context, qty=qty_val, back_callback=query.data, plan_type=plan_type_from_data
            )
            if reply_text_content is None: # Error in _process_quantity_and_set_next_step
                return
        else:
            logger.error(f"Unknown qty_ callback_data format: {data}")
            await query.message.reply_text("Something went wrong. Invalid quantity selection.")
            return # Stop processing this invalid callback

    elif data.startswith("custom_quantity"):
        context.user_data["awaiting_custom_quantity_input"] = True # Flag for message handler

        if data == "custom_quantity_poll":
            context.user_data["custom_plan_type"] = "x_poll" # Store specific plan type for message handler
            reply_text_content = "Enter custom number of *Votes* \(min 10\)\:"
            reply_keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="poll_plans_x")]]
            current_slide_key = "custom_quantity_input_poll"
        elif data == "custom_quantity_tg_custom": # Corrected name
            context.user_data["custom_plan_type"] = "tg_custom"
            reply_text_content = "Enter custom number of *posts* for TG engagement \(min 10\)\:"
            reply_keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data=f"tgc_{context.user_data.get('tqty', '')}")]]
            current_slide_key = "custom_quantity_input_tg"
        elif data == "custom_quantity_x_engagement": # Corrected name
            context.user_data["custom_plan_type"] = "x_engagement"
            reply_text_content = "Enter custom number of *posts* for X engagement \(min 10\)\:"
            reply_keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="confirm_amount")]]
            current_slide_key = "custom_quantity_input_x"
        elif data == "custom_quantity_direct_add": # New custom quantity for Direct Add
            context.user_data["custom_plan_type"] = "direct_add"
            reply_text_content = (
                f"Enter custom number of *Direct Add Followers* \(min {APIConfig.FOLLOWER_DETAILS['direct_add']['min_qty']}\)\:"
            )
            reply_keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="direct_add_select_qty")]]
            current_slide_key = "custom_quantity_input_direct_add"
        elif data == "custom_quantity_slow_push": # New custom quantity for Slow Push
            context.user_data["custom_plan_type"] = "slow_push"
            reply_text_content = (
                f"Enter custom number of *Slow Push Followers* \(min {APIConfig.FOLLOWER_DETAILS['slow_push']['min_qty']}, in multiples of 10\)\:"
            )
            reply_keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="slow_push_select_qty")]]
            current_slide_key = "custom_quantity_input_slow_push"
        elif data == "custom_premium_quantity_order": # For TG Premium Members
            context.user_data["custom_plan_type"] = "tg_premium"
            reply_text_content = (
                f"Enter custom number of *Telegram Premium Members* \(min 50\)\:"
            )
            reply_keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="premium_plans_tg")]]
            current_slide_key = "custom_quantity_input_tg_premium"
        else:
            logger.error(f"Unknown custom_quantity callback_data: {data}")
            await query.message.reply_text("Something went wrong. Invalid custom quantity selection.")
            return # Stop processing this invalid callback

    elif data == "reply_guys_panel":

        context.user_data.pop("awaiting_bank_details", None)
        context.user_data.pop("withdraw_order", None)
        context.user_data.pop("submit_replies_order", None)

        replies = get_total_posts(user_id)
        amount = get_total_amount(user_id)
        daily_posts = get_user_daily_posts(user_id)

        daily_breakdown_lines = [f"{day}\\.: {count} replies" for day, count in daily_posts]
        daily_breakdown_string = "\n".join(daily_breakdown_lines)
        
        # Escape the amount for MarkdownV2
        escaped_amount = escape_markdown_v2(f"{amount:,.2f}")

        reply_text_content = (
            "Full Breakdown\\.:\n\n"
            f"{daily_breakdown_string}\n\n"
            f"Total Replies\\.: *{replies}*\n"
            f"Total Amount\\.: *₦{escaped_amount}*"
        )
        reply_keyboard = [
            [InlineKeyboardButton("Withdraw", callback_data="withdraw")],
            [InlineKeyboardButton("Submit Replies", callback_data="submit_replies")],
            [InlineKeyboardButton("⬅️ Back", callback_data="service_menu")]
        ]
        current_slide_key = "reply_panel"


    elif data == "submit_replies":
        context.user_data["submit_replies_order"] = True
        reply_text_content = f"Enter the Number of replies and Day for submission\. Format\: \(No\. of replies, Day of the week\)\:"
        reply_keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="reply_guys_panel")]]
        current_slide_key = "submit_replies_amount"
        
    

    elif data == "withdraw":
        context.user_data["withdraw_order"] = True
        ref_balance = context.user_data.get("ref_balance")
        
        if ref_balance is not None:
            context.user_data["is_affiliate_withdrawal"] = True
            escaped_balance = escape_markdown_v2(f"{ref_balance:.2f}")
            reply_text_content = f"Enter the amount you'd like to withdraw \\(Balance: *${escaped_balance}*\\):"
            reply_keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="affiliate_balance")]]
            current_slide_key = "withdraw_affiliate_amount"
        else:
            context.user_data["is_affiliate_withdrawal"] = False
            user_total_amount = get_total_amount(user_id)
            context.user_data["reply_balance"] = user_total_amount
            escaped_balance = escape_markdown_v2(f"{user_total_amount:,.2f}")
            reply_text_content = f"Enter the amount you'd like to withdraw \\(Min: ₦100\\) \n\\(Balance: *₦{escaped_balance}*\\):"
            reply_keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="reply_guys_panel")]]
            current_slide_key = "withdraw_reply_amount"

    elif data in ("ghost_writers_plans", "kol_push_plans"):
        reply_text_content = (
            "This plan isn’t on the bot yet.\n"
            "Please contact @ViralCore\\_Support for details."
        )
        reply_keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="service_menu")]]
        current_slide_key = data

    elif data == "payment_crypto":
        reply_text_content = "Choose cryptocurrency\:"
        reply_keyboard = [
            [InlineKeyboardButton("USDT", callback_data="usdt")],
            [InlineKeyboardButton("BNB", callback_data="bsc"),
             InlineKeyboardButton("SOL", callback_data="sol")],
            [InlineKeyboardButton("TRX", callback_data="trx"),
             InlineKeyboardButton("APTOS", callback_data="aptos")],
            # Back button needs to be dynamic based on which plan led to payment
            [InlineKeyboardButton("⬅️ Back", callback_data=f"back_from_payment_{context.user_data.get('current_plan_type', 'main_menu')}")] # Dynamic back
        ]
        current_slide_key = "payment_crypto"

    elif data == "usdt":
        reply_text_content = "Select USDT network\:"
        reply_keyboard = [
            [InlineKeyboardButton("BEP20", callback_data="usdt_bep20")],
            [InlineKeyboardButton("TRC20", callback_data="usdt_trc20")],
            [InlineKeyboardButton("Solana", callback_data="usdt_sol")],
            [InlineKeyboardButton("Aptos", callback_data="usdt_aptos")],
            [InlineKeyboardButton("⬅️ Back", callback_data="payment_crypto")]
        ]
        current_slide_key = "usdt_networks"

    elif data in (
        "bsc", "sol", "trx", "aptos",
        "usdt_bep20", "usdt_trc20", "usdt_sol", "usdt_aptos"
    ):
        await ph.initiate_crypto_payment_flow(update, context, crypto_type=data, callback_query=query)
        return

    elif data == "payment_bank":
        reply_text_content = "Select bank currency\:"
        reply_keyboard = [
            [InlineKeyboardButton("NGN", callback_data="bank_ngn")],
            # Back button needs to be dynamic
            [InlineKeyboardButton("⬅️ Back", callback_data=f"back_from_payment_{context.user_data.get('current_plan_type', 'main_menu')}")] # Dynamic back
        ]
        current_slide_key = "payment_bank"

    elif data in ("bank_usd", "bank_ngn"):
        currency = data.split("_", 1)[1]
        await query.edit_message_text("Please wait while we generate your bank details...")
        await ph.initiate_bank_payment_flow(update, context, currency=currency, callback_query=query)
        return

    # Handle dynamic back buttons from payment
    elif data.startswith("back_from_payment_"):
        plan_type_from_back = data.split("back_from_payment_")[1]
        
        # Reset current_plan_type if it was set before this menu
        context.user_data.pop("current_plan_type", None)

        # Logic to return to the appropriate quantity selection menu
        if plan_type_from_back == "x_engagement":
            reply_text_content = "Please select the number of posts you would like to purchase\:"
            reply_keyboard = [
                [InlineKeyboardButton("10", callback_data="qty_x_engagement_10"),
                 InlineKeyboardButton("25", callback_data="qty_x_engagement_25")],
                [InlineKeyboardButton("50", callback_data="qty_x_engagement_50"),
                 InlineKeyboardButton("100", callback_data="qty_x_engagement_100")],
                [InlineKeyboardButton("Custom Quantity", callback_data="custom_quantity_x_engagement")],
                [InlineKeyboardButton("⬅️ Back", callback_data="engagement_plans_x")]
            ]
            current_slide_key = "confirm_amount_selection" # This is the slide key for X engagement quantity
        elif plan_type_from_back == "x_poll":
            reply_text_content = (
                "Twitter Poll Plan\:\n\n"
                "$0\.3 per 10 VOTES"
                "\n\nPlease select the number of Votes you would like to purchase\:"
            )
            reply_keyboard = [
                [InlineKeyboardButton("10", callback_data="qty_poll_10"),
                 InlineKeyboardButton("25", callback_data="qty_poll_25")],
                [InlineKeyboardButton("50", callback_data="qty_poll_50"),
                 InlineKeyboardButton("100", callback_data="qty_poll_100")],
                [InlineKeyboardButton("Custom Quantity", callback_data="custom_quantity_poll")],
                [InlineKeyboardButton("⬅️ Back", callback_data="x_plans")]
            ]
            current_slide_key = "poll_plans_x"
        elif plan_type_from_back == "tg_custom":
            tqty = context.user_data.get('tqty', 0) # Retain the tqty if possible
            reply_text_content = "Please select the number of posts you would like to purchase\:"
            reply_keyboard = [
                [InlineKeyboardButton("10", callback_data="qty_tg_custom_10"),
                 InlineKeyboardButton("25", callback_data="qty_tg_custom_25")],
                [InlineKeyboardButton("50", callback_data="qty_tg_custom_50"),
                 [InlineKeyboardButton("100", callback_data="qty_tg_custom_100")],
                [InlineKeyboardButton("Custom Quantity", callback_data="custom_quantity_tg_custom")],
                [InlineKeyboardButton("⬅️ Back", callback_data="engagement_plans_tg")]
            ]]
            current_slide_key = "tgc_posts_selection"
        elif plan_type_from_back == "automated_plans_tg": # Back from automated TG payment
             reply_text_content = (
                "Telegram Automation\n\n"
                "Get a personal bot that constantly monitors your channel for new posts and automatically submits them for raiding"
                "\n\nAt $10 per month\. Proceed to payment?"
            )
             reply_keyboard = [
                [InlineKeyboardButton("Crypto", callback_data="payment_crypto"),
                InlineKeyboardButton("Bank", callback_data="payment_bank")],
                [InlineKeyboardButton("⬅️ Back", callback_data="tg_plans")]
            ]
             current_slide_key = "automated_plans_tg"
        elif plan_type_from_back == "direct_add":
            escaped_price = escape_markdown_v2(f"${APIConfig.FOLLOWER_DETAILS['direct_add']['price_per_k']:.2f}")
            reply_text_content = (
                f"Direct Add Followers\:\n\n"
                f"Price\: {escaped_price} per 1k followers\.\n"
                f"Minimum\: {APIConfig.FOLLOWER_DETAILS['direct_add']['min_qty']} followers\.\n\n"
                "Please select the number of followers you would like to purchase\:"
            )
            reply_keyboard = [
                [InlineKeyboardButton("1,000", callback_data="qty_direct_add_1000")],
                [InlineKeyboardButton("2,000", callback_data="qty_direct_add_2000")],
                [InlineKeyboardButton("5,000", callback_data="qty_direct_add_5000")],
                [InlineKeyboardButton("10,000", callback_data="qty_direct_add_10000")],
                [InlineKeyboardButton("Custom Quantity", callback_data="custom_quantity_direct_add")],
                [InlineKeyboardButton("⬅️ Back", callback_data="followers_plans_x")]
            ]
            current_slide_key = "direct_add_qty_selection"
        elif plan_type_from_back == "slow_push":
            escaped_price = escape_markdown_v2(f"${APIConfig.FOLLOWER_DETAILS['slow_push']['price_per_10']:.2f}")
            reply_text_content = (
                f"Slow Push Followers\:\n\n"
                f"Price\: {escaped_price} per 10 followers\.\n"
                f"Minimum\: {APIConfig.FOLLOWER_DETAILS['slow_push']['min_qty']} followers \(in multiples of 10\)\.\n\n"
                "Please select the number of followers you would like to purchase\:"
            )
            reply_keyboard = [
                [InlineKeyboardButton("100", callback_data="qty_slow_push_100")],
                [InlineKeyboardButton("250", callback_data="qty_slow_push_250")],
                [InlineKeyboardButton("500", callback_data="qty_slow_push_500")],
                [InlineKeyboardButton("1,000", callback_data="qty_slow_push_1000")],
                [InlineKeyboardButton("Custom Quantity", callback_data="custom_quantity_slow_push")],
                [InlineKeyboardButton("⬅️ Back", callback_data="followers_plans_x")]
            ]
            current_slide_key = "slow_push_qty_selection"
        else: # Fallback to main menu if unknown
            reply_text_content = get_main_menu_text()
            reply_keyboard = main_menu_keyboard(is_admin)
            current_slide_key = "main_menu"


    else: # Fallback for any unhandled callback data
        reply_text_content = get_main_menu_text()
        reply_keyboard = main_menu_keyboard(is_admin)
        current_slide_key = "main_menu"

    # --- Final Message Rendering ---
    img_path = APIConfig.SLIDE_IMAGES.get(current_slide_key)
    await clear_bot_messages(update, context)
    # NOTE: DO NOT escape the entire reply_text_content here.
    # Template markdown formatting (like *bold*) would be broken.
    # User values should be escaped where they are inserted into templates.
    # Static special chars (. ! - ( ) etc.) should be pre-escaped in templates.

    try:
        if img_path and os.path.isfile(img_path):
            await query.edit_message_media(
                media=InputMediaPhoto(media=img_path, caption=reply_text_content, parse_mode=ParseMode.MARKDOWN_V2),
                reply_markup=InlineKeyboardMarkup(reply_keyboard)
            )
        else:
            # print(reply_keyboard)
            await query.edit_message_text(
                text=reply_text_content,
                reply_markup=InlineKeyboardMarkup(reply_keyboard),
                parse_mode=ParseMode.MARKDOWN_V2
            )
    except BadRequest as e:
        logger.warning("menu_handler edit failed (%s) for user %s. Resending message.", e, query.from_user.id)
        if img_path and os.path.isfile(img_path):
            msg = await query.message.reply_photo(
                photo=img_path,
                caption=reply_text_content,
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=InlineKeyboardMarkup(reply_keyboard)
            )
        else:
            msg = await query.message.reply_text(
                text=reply_text_content,
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=InlineKeyboardMarkup(reply_keyboard)
            )
        context.chat_data.setdefault("bot_messages", []).append(msg.message_id)
    finally:
        try:
            await query.answer()
        except Exception as e:
            logger.error("Failed to answer callback query: %s", e)

# ##### MODIFICATION: Start of handle_withdrawal_approval function
import re # Make sure re is imported at the top of the file

async def handle_withdrawal_approval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer() # Acknowledge the callback

    # ##### MODIFICATION: Access pending_withdrawals from bot_data
    # This dictionary holds all pending withdrawal requests for admin approval.
    pending_withdrawals = context.bot_data.get("pending_withdrawals", {})

    callback_data = query.data
    # Use regex to parse action and request_id from callback_data
    match = re.match(r"^(approve_withdrawal_|reject_withdrawal_)(\d+)$", callback_data)

    if not match:
        logger.warning(f"Invalid callback data for withdrawal approval: {callback_data}")
        await query.edit_message_text(
            "❌ An internal error occurred with the withdrawal request ID\. Please try again or contact support\.",
            parse_mode='MarkdownV2' # ##### MODIFICATION: Consistent ParseMode, escape '.'
        )
        return

    action_type = match.group(1) # e.g., 'approve_withdrawal_'
    request_id = int(match.group(2))

    withdrawal_data = pending_withdrawals.get(request_id)

    if not withdrawal_data:
        # Request not found, likely already processed or bot restarted
        edited_admin_message = (
            f"❌ Withdrawal request with ID `{request_id}` not found or already processed\. "
            f"It might have been cleared due to bot restart or concurrent admin action\."
        )
        await query.edit_message_text(edited_admin_message, reply_markup=None, parse_mode='MarkdownV2')
        logger.warning(f"Withdrawal request ID {request_id} not found in pending_withdrawals.")
        return

    # ##### MODIFICATION: Remove the request from pending_withdrawals immediately
    # This prevents double processing and ensures it's "used up" once clicked.
    del pending_withdrawals[request_id]
    context.bot_data["pending_withdrawals"] = pending_withdrawals # Save the updated dictionary back

    user_id_requester = withdrawal_data["user_id"]
    withdrawal_amount_usd = withdrawal_data["withdrawal_amount_usd"]
    withdrawal_amount_ngn = withdrawal_data["withdrawal_amount_ngn"]
    bank_details_raw = withdrawal_data["bank_details"] # raw input for admin message
    account_name = withdrawal_data["account_name"]
    account_number = withdrawal_data["account_number"]
    bank_name = withdrawal_data["bank_name"]
    is_affiliate_withdrawal = withdrawal_data["is_affiliate_withdrawal"]
    user_first_name = withdrawal_data["user_first_name"]
    user_username = withdrawal_data["user_username"]
    user_message_id = withdrawal_data["user_message_id"] # Message ID to reply to the user's initial request

    # Escape all dynamic strings for MarkdownV2 before use in messages
    escaped_user_first_name = escape_markdown_v2(user_first_name)
    escaped_user_username = escape_markdown_v2(user_username) if user_username else None
    escaped_bank_details = escape_markdown_v2(bank_details_raw)
    escaped_account_name = escape_markdown_v2(account_name)
    escaped_account_number = escape_markdown_v2(account_number)
    escaped_bank_name = escape_markdown_v2(bank_name)


    if action_type == "approve_withdrawal_":
        # --- Initiate Flutterwave Transfer ---
        try:
            # Transfer amount is in NGN for Flutterwave
            transfer_response = initiate_flutterwave_transfer(
                amount=withdrawal_amount_ngn,
                beneficiary_name=account_name,
                account_number=account_number,
                account_bank=bank_name
            )
            print(transfer_response)
            if transfer_response.get("status") == "success":
                # --- Validate and process balance update atomically ---
                try:
                    from utils.balance_operations import atomic_withdraw_operation, validate_withdrawal_request
                    
                    balance_type = "affiliate" if is_affiliate_withdrawal else "reply"
                    
                    # Validate withdrawal before processing
                    is_valid, error_msg = validate_withdrawal_request(
                        user_id_requester, balance_type, withdrawal_amount_usd
                    )
                    
                    if not is_valid:
                        logger.error(f"Withdrawal validation failed for user {user_id_requester}: {error_msg}")
                        # Notify admin of validation failure
                        validation_error_message = (
                            f"❌ *WITHDRAWAL VALIDATION FAILED\\!*\n\n"
                            f"User: [{escaped_user_first_name}](tg://user?id={user_id_requester})\n"
                            f"Error: {escape_markdown_v2(error_msg)}\n"
                            f"Amount: *₦{int(withdrawal_amount_ngn)}*\n\n"
                            f"The Flutterwave transfer was successful but balance update failed\\. "
                            f"Manual intervention may be required\\."
                        )
                        await query.edit_message_text(
                            validation_error_message,
                            reply_markup=None,
                            parse_mode='MarkdownV2'
                        )
                        return
                    
                    # Generate operation ID for idempotency
                    operation_id = f"withdraw_{user_id_requester}_{withdrawal_amount_usd}_{request_id}"
                    
                    # Perform atomic withdrawal
                    balance_success = atomic_withdraw_operation(
                        user_id=user_id_requester,
                        balance_type=balance_type,
                        amount=withdrawal_amount_usd,
                        reason=f"Withdrawal - Request ID: {request_id}",
                        operation_id=operation_id
                    )
                    
                    if not balance_success:
                        logger.error(f"Failed to update {balance_type} balance for user {user_id_requester}")
                        # Notify admin of balance update failure
                        balance_error_message = (
                            f"❌ *BALANCE UPDATE FAILED\\!*\n\n"
                            f"User: [{escaped_user_first_name}](tg://user?id={user_id_requester})\n"
                            f"Balance Type: {escape_markdown_v2(balance_type.title())}\n"
                            f"Amount: *₦{int(withdrawal_amount_ngn)}*\n\n"
                            f"The Flutterwave transfer was successful but balance update failed\\. "
                            f"Manual intervention required\\."
                        )
                        await query.edit_message_text(
                            balance_error_message,
                            reply_markup=None,
                            parse_mode='MarkdownV2'
                        )
                        return
                    
                    logger.info(f"{balance_type.title()} withdrawal of ${withdrawal_amount_usd:.2f} processed for user {user_id_requester}")
                    
                except ImportError:
                    # Fallback to original implementation
                    logger.warning("Using non-atomic balance operations (balance_operations module not available)")
                    if is_affiliate_withdrawal:
                        # Decrement affiliate balance by USD amount
                        success = decrement_affiliate_balance(user_id_requester, withdrawal_amount_usd)
                        if not success:
                            logger.error(f"Failed to decrement affiliate balance for user {user_id_requester}")
                            return
                        logger.info(f"Affiliate withdrawal of ${withdrawal_amount_usd:.2f} processed for user {user_id_requester}")
                    else:
                        # Decrement general post balance by USD amount
                        success = remove_amount(user_id_requester, withdrawal_amount_usd)
                        if not success:
                            logger.error(f"Failed to decrement reply balance for user {user_id_requester}")
                            return
                        logger.info(f"Standard withdrawal of ${withdrawal_amount_usd:.2f} processed for user {user_id_requester}")
                except Exception as e:
                    logger.error(f"Unexpected error in balance operations: {e}")
                    return


                # Notify the user
                escaped_withdrawal_amount = escape_markdown_v2(str(withdrawal_amount_ngn)) # Ensure amount is escaped for MarkdownV2
                user_confirmation_message = (
                    f"Your withdrawal request for *₦{escaped_withdrawal_amount}* has been successfully processed "
                    f"and the funds have been transferred to your bank account\n\n"
                    f"Transaction Details:\n"
                    f"Account Name: `{escaped_account_name}`\n"
                    f"Account Number: `{escaped_account_number}`\n"
                    f"Bank Name: `{escaped_bank_name}`\n\n"
                    f"If you do not receive the funds within a few hours, please contact support", # ##### MODIFICATION: Escaped '.'
                )
                logger.info(f"User {user_id_requester} notified of successful withdrawal.\n {user_confirmation_message}")
                try:
                    # Send confirmation to the user's original chat, if possible
                    await context.bot.send_message(
                        chat_id=user_id_requester,
                        text=user_confirmation_message,
                        parse_mode='MarkdownV2'
                    )
                    logger.info(f"User {user_id_requester} notified of successful withdrawal.")
                except Exception as e:
                    logger.error(f"Failed to notify user {user_id_requester} about withdrawal: {e}")

                # Update the admin message
                edited_admin_message = (
                    f"✅ *WITHDRAWAL APPROVED & PROCESSED\!* ✅\n\n" # ##### MODIFICATION: Escaped '!'
                    f"User: [{escaped_user_first_name}](tg://user?id={user_id_requester})"
                    f"{f' \\(@{escaped_user_username}\\)' if escaped_user_username else ''}\n"
                    f"Withdrawal Type: {escape_markdown_v2('Affiliate' if is_affiliate_withdrawal else 'Standard')}\n"
                    f"Amount: *₦{int(withdrawal_amount_ngn)}*"
                    f"{f' \\(~\\${withdrawal_amount_usd:,.2f}\\)' if is_affiliate_withdrawal else ''}\n\n" # ##### MODIFICATION: Escape '~' and '$'
                    f"Bank Details:\n`{escaped_bank_details}`\n\n"
                    f"Request ID: `{request_id}`\n\n"
                    f"_Funds transferred successfully via Flutterwave\._"
                )
                await query.edit_message_text(edited_admin_message, reply_markup=None, parse_mode='MarkdownV2')
                logger.info(f"Admin message for request {request_id} updated to approved.")

            else:
                # Flutterwave transfer failed - show user-friendly and admin messages
                try:
                    from utils.api_client import create_user_friendly_error_message, create_admin_error_message
                    
                    # Get trace ID if available
                    trace_id = transfer_response.get("trace_id", "N/A")
                    error_message = transfer_response.get("message", "Unknown error")
                    
                    # Create user-friendly error message
                    user_error_msg = create_user_friendly_error_message(
                        error_message, "withdrawal"
                    )
                    
                    # Create detailed admin error message
                    admin_error_details = create_admin_error_message(
                        error_message, "Flutterwave withdrawal"
                    )
                    
                except ImportError:
                    # Fallback to simple messages
                    trace_id = "N/A"
                    user_error_msg = "There was a problem processing your withdrawal. An admin has been notified and will review it shortly."
                    admin_error_details = f"Flutterwave API Error: {transfer_response.get('message', 'Unknown error')}"
                
                # Admin error message with technical details
                error_message_admin = (
                    f"❌ *FLUTTERWAVE TRANSFER FAILED for Request ID {request_id}\\!* ❌\n\n"
                    f"User: [{escaped_user_first_name}](tg://user?id={user_id_requester})"
                    f"{f' \\(@{escaped_user_username}\\)' if escaped_user_username else ''}\n"
                    f"Amount: *₦{int(withdrawal_amount_ngn)}*\n"
                    f"Details:\n`{escaped_bank_details}`\n\n"
                    f"Error: {escape_markdown_v2(transfer_response.get('message', 'Unknown error'))}\n"
                    f"Trace ID: `{trace_id}`\n\n"
                    f"Please investigate and manually process or contact Flutterwave support\\."
                )
                await query.edit_message_text(error_message_admin, reply_markup=None, parse_mode='MarkdownV2')
                logger.error(f"Flutterwave transfer failed for request {request_id}: {admin_error_details}")

                # User-friendly notification
                user_failed_notification = (
                    f"⚠️ {escape_markdown_v2(user_error_msg)}\n\n"
                    f"Your withdrawal request reference: `{request_id}`\n\n"
                    f"We apologize for the inconvenience\\."
                )
                try:
                    await context.bot.send_message(
                        chat_id=user_id_requester,
                        text=user_failed_notification,
                        parse_mode='MarkdownV2'
                    )
                except Exception as e:
                    logger.error(f"Failed to notify user {user_id_requester} about withdrawal failure: {e}")

        except Exception as e:
            # General error during processing or Flutterwave call
            error_message_admin = (
                f"❌ *ERROR PROCESSING WITHDRAWAL for Request ID {request_id}\!* ❌\n\n" # ##### MODIFICATION: Escaped '!'
                f"User: [{escaped_user_first_name}](tg://user?id={user_id_requester})"
                f"{f' \\(@{escaped_user_username}\\)' if escaped_user_username else ''}\n"
                f"Amount: *₦{int(withdrawal_amount_ngn)}*\n"
                f"Details:\n`{escaped_bank_details}`\n\n"
                f"Error: {escape_markdown_v2(str(e))}\n\n" # ##### MODIFICATION: Escape error message
                f"Please investigate manually\." # ##### MODIFICATION: Escaped '.'
            )
            await query.edit_message_text(error_message_admin, reply_markup=None, parse_mode='MarkdownV2')
            logger.error(f"General error processing withdrawal request {request_id}: {e}")

            user_failed_notification = (
                f"⚠️ Your withdrawal request for *₦{int(withdrawal_amount_ngn)}* encountered an error and could not be processed\. "
                f"An admin has been notified and will review it shortly\. "
                f"We apologize for the inconvenience\." # ##### MODIFICATION: Escaped '.'
            )
            try:
                await context.bot.send_message(
                    chat_id=user_id_requester,
                    text=user_failed_notification,
                    parse_mode='MarkdownV2'
                )
                await notify_admin(user_id_requester, error_message_admin)
            except Exception as e:
                logger.error(f"Failed to notify user {user_id_requester} about withdrawal error: {e}")


    elif action_type == "reject_withdrawal_":
        # --- Notify the user of rejection ---
        user_rejection_message = (
            f"❌ Your withdrawal request for *₦{int(withdrawal_amount_ngn)}* has been rejected by an admin\. "
            f"Reason: Your request was declined\. " # Simplified reason, consider adding a text input for admin to specify reason
            f"If you believe this is an error, please contact support\." # ##### MODIFICATION: Escaped '.'
        )
        try:
            await context.bot.send_message(
                chat_id=user_id_requester,
                text=user_rejection_message,
                parse_mode='MarkdownV2'
            )
            logger.info(f"User {user_id_requester} notified of rejected withdrawal.")
        except Exception as e:
            logger.error(f"Failed to notify user {user_id_requester} about rejected withdrawal: {e}")

        # --- Update the admin message ---
        edited_admin_message = (
            f"❌ *WITHDRAWAL REJECTED\!* ❌\n\n" # ##### MODIFICATION: Escaped '!'
            f"User: [{escaped_user_first_name}](tg://user?id={user_id_requester})"
            f"{f' \\(@{escaped_user_username}\\)' if escaped_user_username else ''}\n"
            f"Withdrawal Type: {escape_markdown_v2('Affiliate' if is_affiliate_withdrawal else 'Standard')}\n"
            f"Amount: *₦{int(withdrawal_amount_ngn)}*"
            f"{f' \\(~\\${withdrawal_amount_usd:,.2f}\\)' if is_affiliate_withdrawal else ''}\n\n" # ##### MODIFICATION: Escape '~' and '$'
            f"Bank Details:\n`{escaped_bank_details}`\n\n"
            f"Request ID: `{request_id}`\n\n"
            f"_Request was rejected by an admin\._" # ##### MODIFICATION: Escaped '.'
        )
        await query.edit_message_text(edited_admin_message, reply_markup=None, parse_mode='MarkdownV2')
        logger.info(f"Admin message for request {request_id} updated to rejected.")

async def handle_replies_approval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer() # Acknowledge the callback

    callback_data = query.data
    # Use regex to parse action and request_id from callback_data
    match = re.match(r"^(approve_replies_order_|reject_replies_order_)(\d+)$", callback_data)

    if not match:
        logger.warning(f"Invalid callback data for replies order approval/rejection: {callback_data}")
        await query.edit_message_text(
            "❌ An internal error occurred with the the replies order request ID\\. Please try again or contact support\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    action_type = match.group(1) # e.g., 'approve_replies_' or 'reject_replies_'
    request_id = int(match.group(2))

    pending_replies_orders = context.bot_data.get("pending_replies_orders", {})
    order_data = pending_replies_orders.get(request_id)

    if not order_data:
        await query.edit_message_text(
            "❌ This replies order request was not found or already processed\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        logger.warning(f"Admin tried to process non-existent replies order ID: {request_id}")
        return

    user_id = order_data["user_id"]
    num_replies = order_data["num_replies"]
    day_of_week = order_data["day_of_week"]
    user_first_name = order_data["user_first_name"]
    user_username = order_data["user_username"]
    user_username = user_username.lower()
    day_of_week = day_of_week.lower()

    print(f"Admin action: {action_type} for request ID {request_id} by user {user_id} ({user_username}) "
          f"for {num_replies} replies on {day_of_week}.")

    if action_type == "approve_replies_order_":
        # --- CRITICAL: Call the function to update the user's DB record ---
        db_update_success = add_post(user_id, user_username, day_of_week, num_replies)

        # print(f"DB update success: {db_update_success} for request ID {request_id}.")

        if db_update_success:
            # Remove from pending list AFTER successful DB update
            del pending_replies_orders[request_id]
            context.bot_data["pending_replies_orders"] = pending_replies_orders # Save updated dict

            # Update admin message
            escaped_user_first_name = escape_markdown_v2(user_first_name)
            escaped_user_username = escape_markdown_v2(user_username) if user_username else None

            await query.edit_message_text(
                f"✅ Replies order request ID `{request_id}` approved and *added to user's database* for user "
                f"[{escaped_user_username}](tg://user?id={user_id})\\. "
                f"*{num_replies} replies on {day_of_week}*\\."
                , parse_mode=ParseMode.MARKDOWN_V2
            )
            logger.info(f"Admin approved replies order ID {request_id} for user {user_id}. User DB updated.")

            # Notify user
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🎉 Your replies *{num_replies} replies on {day_of_week}* has been approved and filled\\!\n\n"
                    "Check your balance for confirmation\\."
                , parse_mode=ParseMode.MARKDOWN_V2
            )
        else:
            # If DB update failed, do NOT remove from pending_replies_orders
            await query.edit_message_text(
                f"❌ Failed to update user's database for replies order request ID `{request_id}`\\. "
                f"The order is still pending in the system\\. Please check logs\\."
                , parse_mode=ParseMode.MARKDOWN_V2
            )
            logger.error(f"Failed to update user DB for replies order {request_id} for user {user_id}. Order remains pending.")
            # Optionally, notify the admin more urgently or provide retry options

    elif action_type == "reject_replies_order_":
        # Remove from pending list
        del pending_replies_orders[request_id]
        context.bot_data["pending_replies_orders"] = pending_replies_orders # Save updated dict

        escaped_user_first_name = escape_markdown_v2(user_first_name)
        escaped_user_username = escape_markdown_v2(user_username) if user_username else None

        # Update admin message
        await query.edit_message_text(
            f"🚫 Replies order request ID `{request_id}` rejected for user "
            f"[{escaped_user_username}](tg://user?id={user_id})\\. "
            f"*{num_replies} replies on {day_of_week}*\\."
            , parse_mode=ParseMode.MARKDOWN_V2
        )
        logger.info(f"Admin rejected replies order ID {request_id} for user {user_id}.")

        # Notify user of rejection
        await context.bot.send_message(
            chat_id=user_id,
            text=f"😔 Your replies order for *{num_replies} replies on {day_of_week}* has been rejected\\.\n\n"
                "Please contact support for more details if needed\\."
            , parse_mode=ParseMode.MARKDOWN_V2
        )


# ##### MODIFICATION: End of handle_withdrawal_approval function