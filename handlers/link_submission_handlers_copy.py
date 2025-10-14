#!/usr/bin/env python3
# handlers/link_submission_handlers.py

from telegram.helpers import escape_markdown
import logging, re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from utils.boost_utils import BoostManager
from utils.notification import notify_admin
from utils.messaging import escape_markdown_v2

from utils.db_utils import (
    TWEETS_DB_FILE,
    TG_DB_FILE,
    GROUPS_TWEETS_DB_FILE,
    get_connection,
    get_x_purchases,
    get_tg_purchases,
    get_tg_accounts,
    get_x_accounts,
    update_purchase_x_username,
    decrement_x_rpost,
    get_custom_plan,
    get_latest_tier_for_x,
    decrement_tg_rpost,
    get_latest_tg_plan
)
from utils.link_utils import create_shortened_link, extract_tweet_id, is_tg_link

logger = logging.getLogger(__name__)


async def submitlink(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        await update.message.reply_text("Please use /submitlink in a private chat.")
        return

    if len(context.args) != 1:
        await update.message.reply_text(
            "Usage: /submitlink <twitter_link/tg_link>\n"
            "Example: /submitlink https://x.com/status/1234567890 or /submitlink https://t.me/somechannel\n"
        )
        return

    link = context.args[0]
    lower_link = link.lower()

    # Check for Telegram links on multiple domains (e.g., t.me, telegram.me)
    if any(domain in lower_link for domain in ["t.me", "telegram.me"]):
        await process_tg_link(update, context, link)
    elif "x.com" in lower_link or "twitter.com" in lower_link:
        await process_twitter_link(update, context, link)
    else:
        await update.message.reply_text("Invalid link provided. Please submit a valid Twitter or Telegram link.")


async def handle_twitter_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    twitter_link = update.message.text.strip()
    await process_twitter_link(update, context, twitter_link)


async def handle_awaiting_x_poll_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    logger.info(f"Poll handler received text: '{text}' (user_id={user_id})")
    # This handler only proceeds if 'awaiting_x_poll_details' is True
    # and then immediately pops it, so it only runs once per expectation.
    if context.user_data.get("awaiting_x_poll_details", None):
        logger.info(f"User {user_id} is inputting X poll details: {text}")
        match = re.match(r"(.+),\s*(\d+)", text)
        if match:
            x_poll_link = match.group(1).strip()
            option_number = int(match.group(2).strip())

            # Basic validation
            if not (x_poll_link.startswith("https://x.com/") or x_poll_link.startswith("https://twitter.com/")):
                await update.message.reply_text(
                    "That doesn't look like a valid X (Twitter) poll link. Please send a correct link and option number (e.g., `https://x.com/status/12345/polls/abcdef, 1`)."
                )
                # Re-set the flag if validation fails so they can retry
                context.user_data["awaiting_x_poll_details"] = True
                return
            if not (1 <= option_number <= 4): # Assuming polls have 2-4 options
                await update.message.reply_text("Option number should be 1, 2, 3, or 4. Please try again.")
                # Re-set the flag if validation fails so they can retry
                context.user_data["awaiting_x_poll_details"] = True
                return

            # Retrieve order details from context.user_data
            ordered_quantity = context.user_data.pop("ordered_quantity", None)


            # Clear other relevant flags that might have been set by payment handler
            context.user_data.pop("current_plan_type", None)
            context.user_data.pop("is_x_poll_order", None) # Clear specific order flag

            if not ordered_quantity:
                logger.error(f"Missing data for X Poll order completion for user {user_id}. Context: {context.user_data}")
                await update.message.reply_text(
                    "An error occurred with your order details. Please contact support, or use /start to begin a new order."
                )
                # No redirect to menu_handler here, just return
                return

            # Notify admin about X Poll order
            admin_message = (
                f"🚀 *New X Poll Order\!* 🚀\n\n"
                f"👤 User: {update.effective_user.mention_markdown_v2()} \(ID: `{user_id}`\)\n"
                f"🔗 Poll Link: `{escape_markdown_v2(x_poll_link)}`\n"
                f"🔢 Option Number: `{option_number}`\n"
                f"📦 Quantity: `{ordered_quantity}` votes\n"
                f"Status: *Paid \(Manual Process Required\)*"
            )
            await notify_admin(user_id, admin_message)

            await update.message.reply_text(
                "Thank you! Your X Poll order has been received. "
                "We've sent the details to our team and they will process it shortly.\n\n"
                "You can use /start or /menu to see the main options." # Added instruction
            )
            # Removed: await menu_handler(update, context)
            return # Ensure the handler explicitly returns after completion
        else:
            await update.message.reply_text(
                "Invalid format. Please send the X poll link and option number separated by a comma (e.g., `https://x.com/status/12345/polls/abcdef, 1`)."
            )
            # Re-set the flag if format is invalid so they can retry
            context.user_data["awaiting_x_poll_details"] = True
            return
    # If the flag wasn't set, this handler does nothing, and the message
    # will fall through to subsequent handlers (like the general Twitter link handler)
    logger.debug(f"handle_awaiting_x_poll_details: Flag not set for user {user_id}. Passing through.")


async def process_twitter_link(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    twitter_link: str
):
    if update.effective_chat.type != "private":
        await update.message.reply_text("Please send links in a private chat.")
        return
    
    if context.user_data.pop("awaiting_x_poll_details", False):
        logger.debug(f"handle_twitter_link: Skipping as bot is awaiting X poll details.")
        return

    tweet_id = extract_tweet_id(twitter_link)
    if not tweet_id:
        await update.message.reply_text("❌ Invalid Twitter/X link.")
        return

    # Duplicate check
    conn = get_connection(TWEETS_DB_FILE)
    if not conn:
        await update.message.reply_text("❌ Internal error. Try again later.")
        return

    c = conn.cursor()
    c.execute("SELECT 1 FROM tweets WHERE tweet_id = ?", (tweet_id,))
    if c.fetchone():
        conn.close()
        await update.message.reply_text("❌ This link has already been submitted.")
        return
    conn.close()

    # Check remaining posts
    user_id = update.effective_user.id
    purchases = get_x_purchases(user_id)
    total_rposts = sum(p[3] for p in purchases)

    #print(total_rposts)

    if total_rposts <= 0:
        await update.message.reply_text(
            "You have no remaining posts. Please purchase more to continue."
        )
        return

    # Shorten link
    shortened = create_shortened_link(twitter_link) or twitter_link

    # Store pending tweet
    context.user_data["pending_tweet"] = {
        "tweet_id": tweet_id,
        "twitter_link": twitter_link,
        "shortened_link": shortened
    }

    # Prompt for X account
    raw_accounts = get_x_accounts(user_id)
    accounts = sorted({acc.strip().lower() for acc in raw_accounts if acc.strip()})
    if accounts:
        keyboard = [
            [InlineKeyboardButton(f"@{acc.title()}", callback_data=f"select_x_{acc}")]
            for acc in accounts
        ]
        await update.message.reply_text(
            "Select which X account to use for this post:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        context.user_data["awaiting_x_username"] = True
        await update.message.reply_text(
            "You have not set an X username yet.\n"
            "Please send your username (without '@'), then resend your link."
        )

async def handle_tg_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_link = update.message.text.strip()
    await process_tg_link(update, context, tg_link)

async def process_tg_link(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    tg_link: str
):
    if update.effective_chat.type != "private":
        await update.message.reply_text("Please send links in a private chat.")
        return

    # --- Check for Telegram link ---
    if not is_tg_link(tg_link):
        await update.message.reply_text("❌ Invalid Telegram link.")
        # Proceed with your Telegram-specific logic here
        return

    # Duplicate check
    conn = get_connection(TG_DB_FILE)
    if not conn:
        await update.message.reply_text("❌ Internal error. Try again later.")
        return

    c = conn.cursor()
    c.execute("SELECT 1 FROM telegram_posts WHERE tg_link = ?", (tg_link,))
    if c.fetchone():
        conn.close()
        await update.message.reply_text("❌ This link has already been submitted.")
        return
    conn.close()

    # Check remaining posts
    user_id = update.effective_user.id
    purchases = get_tg_purchases(user_id)
    total_rposts = sum(p[3] for p in purchases)

    # print(total_rposts)

    if total_rposts <= 0:
        await update.message.reply_text(
            "You have no remaining posts. Please purchase more to continue."
        )
        return


    # Store pending tweet
    context.user_data["pending_tg_link"] = {
        "telegram_link": tg_link,
    }

    # Prompt for X account
    raw_accounts = get_tg_accounts(user_id)
    accounts = sorted({acc.strip().lower() for acc in raw_accounts if acc.strip()})
    if accounts:
        keyboard = [
            [InlineKeyboardButton(f"@{acc.title()}", callback_data=f"select_tg_{acc}")]
            for acc in accounts
        ]
        await update.message.reply_text(
            "Select which TG account to use for this post:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        context.user_data["awaiting_tg_username"] = True
        await update.message.reply_text(
            "You have not set a TG username yet.\n"
            "Please send your username (without '@'), then resend your link."
        )



async def x_account_selection_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    acc = query.data.removeprefix("select_x_")

    # If user is setting their X username
    if context.user_data.pop("awaiting_x_username", None):
        update_purchase_x_username(user_id, acc)
        await query.edit_message_text(
            f"✅ X username set to @{acc}. Now resend your link."
        )
        return

    # Retrieve pending tweet
    pending = context.user_data.get("pending_tweet")
    if not pending:
        await query.edit_message_text("❌ No pending post found.")
        return

    # Fetch tier & remaining posts
    tier, rpost = get_latest_tier_for_x(user_id, acc)
    # print(tier, rpost)
    if not tier:
        await query.edit_message_text(f"No active plan found for @{acc}")
        return

    purchases = get_x_purchases(user_id)
    total_rpost = sum(p[3] for p in purchases)

    if total_rpost <= 10:
        await query.edit_message_text(
            f"You have {total_rpost - 1} left. Please Top up to avoid losing access to our services"
        )


    # Compute targets
    if tier == "ct":
        # Check if user has selected a specific custom plan
        selected_plan = context.user_data.get("selected_custom_plan")
        t_l, t_rt, t_cm, t_vw = get_custom_plan(user_id, selected_plan)
        
        # If no custom plan targets found, prompt user to select a plan
        if (t_l, t_rt, t_cm, t_vw) == (0, 0, 0, 0):
            # Import here to avoid circular imports
            from handlers.custom_plans_handlers import show_custom_plans_selection
            await show_custom_plans_selection(update, context)
            return
    else:
        metrics_map = {
            "t1": (30, 10, 5, 2000),
            "t2": (50, 20, 10, 5000),
            "t3": (75, 30, 15, 7000),
            "t4": (100, 40, 20, 10000),
            "t5": (150, 60, 30, 15000),
        }
        t_l, t_cm, t_rt, t_vw = metrics_map.get(tier, (0, 0, 0, 0))

    # Deduct one post
    decrement_x_rpost(user_id, acc)

    # Find alerts group
    conn = get_connection(GROUPS_TWEETS_DB_FILE)
    target_group: int | None = None
    if conn:
        c = conn.cursor()
        c.execute("SELECT group_id FROM groups")
        for (group_id,) in c.fetchall():
            #print(group_id)
            try:
                chat = await context.bot.get_chat(group_id)
                if "comments" in (chat.title or "").lower():
                    target_group = group_id
                    break
            except Exception:
                continue
        conn.close()

    # Alert the group (or note missing)
    link = escape_markdown(pending['twitter_link'], version=2)
    alert_text = (
        "🚨 *New Post Submitted*\n\n"
        f"*Link:* {link}\n\n"
        "*Targets:*\n"
        f"  Comments: `{t_cm}`\n"
        f"  Retweets: `{t_rt}`\n"
        "_This post is now in the queue_"
    )
    if target_group:
        await context.bot.send_message(
            chat_id=target_group,
            text=alert_text,
            parse_mode="MarkdownV2"
        )
        # Confirm back in PM
        await query.message.reply_text(
            f"✅ Post queued under @{acc}.\n"
            f"Targets: 👍 {t_l}  🔁 {t_rt}  💬 {t_cm}  👀 {t_vw}"
        )
    else:
        # No alerts group found → send as a NEW message
        await query.message.reply_text(
            "✅ Your post is queued, but no alerts group was configured."
        )

    # Start the boost
    boost_manager = BoostManager()
    boost_manager.start_boost(
        link=pending["twitter_link"],
        likes=t_l,
        views=t_vw,
        comments=t_cm
    )

    context.user_data.pop("pending_tweet", None)
    # Finally save into tweets DB
    # Think about putting it into the if target block so that users can resend
    conn = get_connection(TWEETS_DB_FILE)
    if conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO tweets
            (tweet_id, twitter_link, target_likes, target_retweets, target_comments, target_views, click_count)
            VALUES (?, ?, ?, ?, ?, ?, 0)
        """, (
            pending["tweet_id"],
            pending["twitter_link"],
            t_l, t_rt, t_cm, t_vw
        ))
        conn.commit()
        conn.close()



    
async def tg_account_selection_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    acc = query.data.removeprefix("select_tg_")

    # If user is setting their TG username
    if context.user_data.pop("awaiting_tg_username", None):
        update_purchase_x_username(user_id, acc)
        await query.edit_message_text(
            f"✅ TG username set to @{acc}. Now resend your link."
        )
        return

    # Retrieve pending tweet
    pending = context.user_data.get("pending_tg_link")
    if not pending:
        await query.edit_message_text("❌ No pending post found.")
        return

    # Fetch tier & remaining posts
    tier, quantity, rpost = get_latest_tg_plan(user_id, acc)
    if not tier:
        await query.edit_message_text(f"No active plan found for @{acc}")
        return


    if rpost <= 10:
        await query.edit_message_text(
            f"You have {rpost - 1} left for your {tier} plan. Please Top up to avoid losing access to our services"
        )

    # Deduct one post
    decrement_tg_rpost(user_id)

    # Find alerts group
    conn = get_connection(GROUPS_TWEETS_DB_FILE)
    target_group: int | None = None
    if conn:
        c = conn.cursor()
        c.execute("SELECT group_id FROM groups")
        for (group_id,) in c.fetchall():
            #print(group_id)
            try:
                chat = await context.bot.get_chat(group_id)
                if "comments" in (chat.title or "").lower():
                    target_group = group_id
                    break
            except Exception:
                continue
        conn.close()

    #print(quantity)
    # Alert the group (or note missing)
    link = escape_markdown(pending['telegram_link'], version=2)
    alert_text = (
        "🚨 *New Post Submitted*\n\n"
        f"*Link:* {link}\n\n"
        "*Targets:*\n"
        f"  Comments/Reactions: `{quantity if quantity else 0}`\n" 
        "_This post is now in the queue_"
    )
    if target_group:
        await context.bot.send_message(
            chat_id=target_group,
            text=alert_text,
            parse_mode="MarkdownV2"
        )
        # Confirm back in PM
        await query.message.reply_text(
            f"✅ Post queued under @{acc}.\n"
            f"Targets: 👍 {quantity}  🔁 {quantity}  💬 {quantity}  👀 {quantity}"
        )
    else:
        # No alerts group found → send as a NEW message
        await query.message.reply_text(
            "✅ Your post is queued, but no alerts group was configured."
        )
    context.user_data.pop("pending_tg_link", None)
    # Finally save into tweets DB
    conn = get_connection(TG_DB_FILE)
    if conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO telegram_posts
            (tg_link, target_comments, target_reactions)
            VALUES (?, ?, ?)
        """, (
            pending["telegram_link"],
            quantity if quantity else 0,  
            quantity if quantity else 0,  
        ))
        conn.commit()
        conn.close()