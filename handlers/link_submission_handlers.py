#!/usr/bin/env python3
# handlers/link_submission_handlers.py

from telegram.helpers import escape_markdown
import logging, re, os, json, math
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackContext
from utils.boost_utils import BoostManager
from utils.notification import notify_admin
from utils.messaging import escape_markdown_v2
from utils.likes_group import send_to_likes_group, METRICS as LIKES_GROUP_METRICS

from settings.bot_settings import (
    COMMENT_GROUP_IDS,
    ACCOUNTS_PER_GROUP,
    BATCH_INTERVAL_SECONDS,
    POINTER_FILE
)

from utils.db_utils import (
    TWEETS_DB_FILE,
    TG_DB_FILE,
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
    get_latest_tg_plan,
    get_user_custom_plans,
    decrement_custom_plan_posts
)
from utils.link_utils import create_shortened_link, extract_tweet_id, is_tg_link

logger = logging.getLogger(__name__)


def _get_batch_pointer() -> int:
    if not os.path.exists(POINTER_FILE):
        return 0
    try:
        with open(POINTER_FILE, 'r') as f:
            data = json.load(f)
        return data.get('pointer', 0)
    except Exception:
        return 0


def _set_batch_pointer(idx: int):
    os.makedirs(os.path.dirname(POINTER_FILE), exist_ok=True)
    with open(POINTER_FILE, 'w') as f:
        json.dump({'pointer': idx}, f)


def _get_batch_pointer() -> int:
    if not os.path.exists(POINTER_FILE):
        return 0
    try:
        with open(POINTER_FILE, 'r') as f:
            data = json.load(f)
        return data.get('pointer', 0)
    except Exception:
        return 0


def _set_batch_pointer(idx: int):
    os.makedirs(os.path.dirname(POINTER_FILE), exist_ok=True)
    with open(POINTER_FILE, 'w') as f:
        json.dump({'pointer': idx}, f)


async def _send_to_group(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    data = job.data
    chat_id = data['chat_id']
    text = data['text']
    parse_mode = data.get('parse_mode', None)
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode
        )
    except Exception as e:
        logger.error(f"Failed to send link to {chat_id}: {e}")
       

def generate_x_link_message(user_id: int, link: str, t_cm: str, t_rt:str) -> str:
    """
    Build the message sent to comment groups.
    Includes a mention of the user and the link.
    """
    safe_link = escape_markdown(link, version=2)
    return (
        f"🚨 New Link Submission 🚨\n\n"
        f"👤 ID: `{user_id}`\n"
        f"🔗 {link}\n\n"
        "*Targets:*\n"
        f"  Comments: `{t_cm}`\n"
        f"  Retweets: `{t_rt}`\n"
        "_This post is now in the queue_"
    )


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

    # Duplicate check removed - users can now submit the same link multiple times
    # Anti-abuse rate limiting is handled at the purchase/balance level

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
    
    # Clear any previously selected custom plan for fresh selection
    context.user_data.pop("selected_custom_plan", None)
    context.user_data.pop("selected_x_account", None)

    # Prompt for X account
    raw_accounts = get_x_accounts(user_id)
    accounts = sorted({acc.strip().lower() for acc in raw_accounts if acc.strip()})
    if accounts:
        keyboard = []
        
        # Add regular tier plan options for each account
        for acc in accounts:
            tier, remaining = get_latest_tier_for_x(user_id, acc)
            if tier and remaining and remaining > 0:
                # User has active tier plan for this account
                tier_display = tier.upper()
                keyboard.append([InlineKeyboardButton(
                    f"@{acc.title()} ({tier_display} - {remaining} posts left)",
                    callback_data=f"select_x_{acc}"
                )])
        
        # Add custom plan options (once each, not per account)
        # Custom plans are user-level, not account-specific
        custom_plans = get_user_custom_plans(user_id, active_only=True)
        if custom_plans:
            for plan in custom_plans:
                plan_name = plan['plan_name']
                # Check if this plan has posts remaining
                max_posts = plan.get('max_posts', 0)
                if max_posts > 0:  # Only show plans with remaining posts
                    # Use first account for callback, but plan is user-level
                    first_acc = accounts[0] if accounts else "default"
                    keyboard.append([InlineKeyboardButton(
                        f"Custom: {plan_name} - {max_posts} posts left",
                        callback_data=f"select_x_{first_acc}_custom_{plan_name}"
                    )])
        
        if keyboard:
            await update.message.reply_text(
                "Select which account and plan to use for this post:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text(
                "❌ You have no active plans with remaining posts. Please purchase a plan first."
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

    # Duplicate check removed - users can now submit the same link multiple times
    # Anti-abuse rate limiting is handled at the purchase/balance level

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
    selection = query.data.removeprefix("select_x_")
    
    # Parse selection - could be "account", "account_custom_planname"
    if "_custom_" in selection:
        # Format: account_custom_planname (user selected account + custom plan)
        parts = selection.split("_custom_", 1)
        acc = parts[0]
        plan_name = parts[1]
        context.user_data["selected_custom_plan"] = plan_name
        selected_plan_type = "custom"
    else:
        # Format: account (regular tier selection)
        acc = selection
        context.user_data.pop("selected_custom_plan", None)
        selected_plan_type = "tier"

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

    # Determine which plan type was selected and compute targets accordingly
    if selected_plan_type == "custom":
        # User selected a custom plan
        selected_plan = context.user_data.get("selected_custom_plan") if context.user_data else None
        
        if selected_plan:
            # Get targets for the selected custom plan
            t_l, t_rt, t_cm, t_vw = get_custom_plan(user_id, selected_plan)
            
            # If the selected plan doesn't exist, show error
            if (t_l, t_rt, t_cm, t_vw) == (0, 0, 0, 0):
                await query.edit_message_text(f"❌ Custom plan '{selected_plan}' not found or inactive.")
                return
                
            # Decrement custom plan usage
            if not decrement_custom_plan_posts(user_id, selected_plan):
                await query.edit_message_text(f"❌ Custom plan '{selected_plan}' has no remaining posts.")
                return
            
        else:
            await query.edit_message_text("❌ No custom plan selected.")
            return
            
    else:
        # User selected a regular tier plan
        tier, remaining = get_latest_tier_for_x(user_id, acc)
        if not tier or not remaining or remaining <= 0:
            await query.edit_message_text(f"❌ No active tier plan found for @{acc} or no posts remaining.")
            return

        # Use tier-based metrics
        metrics_map = {
            "t1": (30, 5, 10, 2000),
            "t2": (50, 10, 20, 5000),
            "t3": (75, 15, 30, 7000),
            "t4": (100, 20, 40, 10000),
            "t5": (150, 30, 60, 15000),
        }
        t_l, t_rt, t_cm, t_vw = metrics_map.get(tier, (0, 0, 0, 0))
        
        # Decrement the tier plan usage
        decrement_x_rpost(user_id, acc)

    # Build the message
    link_md = escape_markdown(pending['twitter_link'], version=2)
    message_text = generate_x_link_message(user_id, link_md, str(t_cm), str(t_rt))

    # --- priority group logic ---
    total_groups = len(COMMENT_GROUP_IDS)
    batch_count = math.ceil(t_cm / ACCOUNTS_PER_GROUP)

    # Always include group 1 first
    priority = COMMENT_GROUP_IDS[0]
    remaining = max(0, batch_count - 1)

    start_idx = _get_batch_pointer()
    seq = []
    i = 0
    while len(seq) < remaining and total_groups > 1:
        idx = (start_idx + i) % total_groups
        grp = COMMENT_GROUP_IDS[idx]
        if grp != priority:
            seq.append(grp)
        i += 1

    batch_groups = [priority] + seq
    new_pointer = (start_idx + i) % total_groups
    _set_batch_pointer(new_pointer)

    # Schedule sends with MarkdownV2
    for idx, chat_id in enumerate(batch_groups):
        delay = idx * BATCH_INTERVAL_SECONDS
        context.application.job_queue.run_once(
            _send_to_group,
            when=delay,
            data={
                'chat_id': chat_id,
                'text': message_text,
                'parse_mode': 'MarkdownV2'
            }
        )
    
    # Track Group 1 send
    LIKES_GROUP_METRICS["posts_sent_group1"] += 1

    # Send to Likes Group (independent, fail-safe operation)
    # This happens immediately and is exempt from rotation
    try:
        await send_to_likes_group(
            context=context,
            post_id=pending["tweet_id"],
            content=pending["twitter_link"],
            likes_needed=t_l-t_cm,  # likes_needed is the target_likes
            post_type="twitter",
        )
    except Exception as e:
        # Fail-safe: log but don't interrupt Group 1 flow
        logger.error(
            f"[LikesGroup] Exception in send_to_likes_group for tweet {pending['tweet_id']}: {e}",
            exc_info=True
        )

    # Confirm back to user
    await query.edit_message_text(
        f"✅ Post queued under @{acc}.\n"
        f"Targets: 👍 {t_l}  🔁 {t_rt}  💬 {t_cm}  👀 {t_vw}\n"
        #f"Will send to {len(batch_groups)} groups, starting with group 1."
    )

    # Boost and cleanup
    BoostManager().start_boost(
        link=pending["twitter_link"],
        likes=t_l,
        views=t_vw,
        comments=t_cm
    )
    context.user_data.pop("pending_tweet", None)

    # Save to DB
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
        update_purchase_x_username(user_id, acc)  # consider a TG‐specific updater here
        await query.edit_message_text(
            f"✅ TG username set to @{acc}. Now resend your link."
        )
        return

    # Retrieve pending link
    pending = context.user_data.get("pending_tg_link")
    if not pending:
        await query.edit_message_text("❌ No pending post found.")
        return

    # Fetch plan & remaining posts
    tier, quantity, rpost = get_latest_tg_plan(user_id, acc)
    if not tier:
        await query.edit_message_text(f"No active plan found for @{acc}")
        return

    # Warn if low
    if rpost <= 10:
        await query.edit_message_text(
            f"You have {rpost - 1} left for your {tier} plan. Please top up soon."
        )

    # Deduct one post
    decrement_tg_rpost(user_id)

    # Build message text
    link = pending["telegram_link"]
    link = escape_markdown_v2(link)
    message_text = (
        "🚨 New Telegram Post 🚨\n\n"
        f"🔗 {link}\n\n"
        f"💬 Targets: {quantity or 0} comments/reactions"
    )

    # Priority + sequential groups
    total_groups = len(COMMENT_GROUP_IDS)
    batch_count = math.ceil((quantity or 0) / ACCOUNTS_PER_GROUP) if total_groups else 0

    # Always send to group 1 first
    priority = COMMENT_GROUP_IDS[0] if total_groups else None
    remaining = max(0, batch_count - 1)
    start_idx = _get_batch_pointer()

    seq = []
    i = 0
    while len(seq) < remaining and total_groups > 1:
        idx = (start_idx + i) % total_groups
        grp = COMMENT_GROUP_IDS[idx]
        if grp != priority:
            seq.append(grp)
        i += 1

    batch_groups = ([priority] if priority is not None else []) + seq
    new_pointer = (start_idx + i) % total_groups if total_groups else 0
    _set_batch_pointer(new_pointer)

    # Schedule sends
    for idx, chat_id in enumerate(batch_groups):
        delay = idx * BATCH_INTERVAL_SECONDS
        context.application.job_queue.run_once(
            _send_to_group,
            when=delay,
            data={
                'chat_id': chat_id,
                'text': message_text,
                'parse_mode': 'MarkdownV2'
            }
        )
    
    # Track Group 1 send
    LIKES_GROUP_METRICS["posts_sent_group1"] += 1

    # Send to Likes Group (independent, fail-safe operation)
    # For Telegram posts, likes_needed is based on quantity (target reactions)
    # Using quantity as likes_needed since TG posts track reactions
    try:
        await send_to_likes_group(
            context=context,
            post_id=pending["telegram_link"],  # Using link as ID for TG posts
            content=pending["telegram_link"],
            likes_needed=quantity or 0,  # likes_needed = target reactions
            post_type="telegram",
        )
    except Exception as e:
        # Fail-safe: log but don't interrupt Group 1 flow
        logger.error(
            f"[LikesGroup] Exception in send_to_likes_group for TG post {pending['telegram_link']}: {e}",
            exc_info=True
        )

    # Confirm back in the chat
    await query.edit_message_text(
        f"✅ Post queued under @{acc}\n"
        f"Targets: 👍 {quantity or 0}  💬 {quantity or 0}"
    )

    # Cleanup & save
    context.user_data.pop("pending_tg_link", None)
    conn = get_connection(TG_DB_FILE)
    if conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO telegram_posts
            (tg_link, target_comments, target_reactions)
            VALUES (?, ?, ?)
        """, (
            link,
            quantity or 0,
            quantity or 0,
        ))
        conn.commit()
        conn.close()
