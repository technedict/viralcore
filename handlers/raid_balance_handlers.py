#!/usr/bin/env python3
# handlers/raid_balance_handlers.py

import sqlite3
import asyncio
import logging
from telegram import Update, ChatPermissions
from telegram.ext import ContextTypes
from utils.config import APIConfig
from utils.db_utils import TWEETS_DB_FILE, get_x_purchases
from utils.db_utils import get_user_metrics, get_referrer, save_purchase, update_affiliate_balance
from ViralCore_V2.utils.link_utils import disable_bitly_link
from handlers.payment_handler import PaymentHandler
from utils.admin_db_utils import add_posts, get_username_by_payment

logger = logging.getLogger(__name__)

# Tracks active raids per group_id
is_raid_active: dict[int, dict] = {}

async def raid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /raid in a group: Lock the group, post the next tweet link & targets, and start a checker.
    """
    chat = update.effective_chat
    user = update.effective_user

    # Only in group/supergroup
    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text("This command only works in groups.")
        return

    # Only admin/creator
    member = await context.bot.get_chat_member(chat.id, user.id)
    if member.status not in ("administrator", "creator"):
        await context.bot.send_message(chat.id, "Only admins can start a raid.")
        return

    # Already raiding?
    if is_raid_active.get(chat.id):
        await context.bot.send_message(chat.id, "A raid is already active here.")
        return

    # Fetch next tweet to raid
    conn = sqlite3.connect(TWEETS_DB_FILE)
    c = conn.cursor()
    c.execute(
        "SELECT id, tweet_id, twitter_link, target_likes, "
        "target_retweets, target_comments, target_views, views "
        "FROM tweets WHERE completed=0 AND group_id IS NULL ORDER BY id ASC LIMIT 1"
    )
    row = c.fetchone()
    conn.close()

    if not row:
        await context.bot.send_message(chat.id, "No posts queued for raiding.")
        return

    db_id, tweet_id, link, tl, tr, tc, tv, views_flag = row

    # Assign to this group
    conn = sqlite3.connect(TWEETS_DB_FILE)
    sqlite = conn.cursor()
    sqlite.execute("UPDATE tweets SET group_id=? WHERE id=?", (chat.id, db_id))
    conn.commit()
    conn.close()

    # Lock the chat
    await context.bot.set_chat_permissions(chat.id, ChatPermissions(can_send_messages=False))

    # Post the raid message
    text = (
        f"🚨 Raid started for tweet: {link}\n\n"
        f"Targets:\n"
        f"👍 Likes: {tl}\n"
        f"🔁 Retweets: {tr}\n"
    )
    # Comments or Views
    if views_flag:
        text += f"👀 Views: {tv}\n"
    else:
        text += f"💬 Comments: {tc}\n"
    msg = await context.bot.send_message(chat.id, text)

    # Record active raid
    is_raid_active[chat.id] = {
        "db_id": db_id,
        "tweet_id": tweet_id,
        "msg_id": msg.message_id,
        "targets": {"likes": tl, "retweets": tr, "comments": tc, "views": tv},
        "views_flag": views_flag
    }

    # Start periodic metric check
    async def _checker():
        handler = PaymentHandler()  # for on-chain checks if needed
        while is_raid_active.get(chat.id):
            await asyncio.sleep(25)
            # Fetch metrics from Twitter
            try:
                resp = APIConfig.TWITTER_CLIENT.get_tweet(
                    tweet_id, tweet_fields=["public_metrics"]
                )
                pm = resp.data.public_metrics
                current_likes = pm.get("like_count", 0)
                current_retweets = pm.get("retweet_count", 0)
                current_comments = pm.get("reply_count", 0)
                current_views = pm.get("impression_count", 0)
            except Exception as e:
                logger.error("Twitter API error: %s", e)
                continue

            state = is_raid_active[chat.id]
            tl_, tr_, tc_, tv_ = (
                state["targets"]["likes"],
                state["targets"]["retweets"],
                state["targets"]["comments"],
                state["targets"]["views"],
            )
            vf = state["views_flag"]

            done = (
                current_likes >= tl_ and
                current_retweets >= tr_ and
                (vf and current_views >= tv_ or (not vf and current_comments >= tc_))
            )
            if done:
                # Unlock
                await context.bot.set_chat_permissions(
                    chat.id, ChatPermissions(can_send_messages=True)
                )
                await context.bot.send_message(chat.id, "🎉 Targets reached! Raid complete.")

                # Cleanup DB and Bitly link if views_flag
                conn2 = sqlite3.connect(TWEETS_DB_FILE)
                c2 = conn2.cursor()
                if vf:
                    c2.execute("DELETE FROM tweets WHERE id=?", (db_id,))
                    disable_bitly_link(link)
                else:
                    c2.execute("UPDATE tweets SET completed=1 WHERE id=?", (db_id,))
                conn2.commit()
                conn2.close()

                # Remove raid state
                is_raid_active.pop(chat.id, None)
                break

    context.application.create_task(_checker())


async def stop_raid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /stopraid: Immediately stop the raid, unlock group, and optionally reassign or delete the tweet.
    """
    chat = update.effective_chat
    user = update.effective_user

    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text("This command only works in groups.")
        return

    member = await context.bot.get_chat_member(chat.id, user.id)
    if member.status not in ("administrator", "creator"):
        await update.message.reply_text("Only admins can stop a raid.")
        return

    state = is_raid_active.pop(chat.id, None)
    if not state:
        await update.message.reply_text("No active raid here.")
        return

    # Unlock
    await context.bot.set_chat_permissions(
        chat.id, ChatPermissions(can_send_messages=True)
    )
    await update.message.reply_text("Raid has been stopped and the group is unlocked.")

    # You could requeue or delete the tweet here if desired.


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /balance: Show the user their total remaining posts across all purchases (private only).
    """
    if update.effective_chat.type != "private":
        await update.message.reply_text("Use /balance in a private chat.")
        return

    user_id = update.effective_user.id
    purchases = get_x_purchases(user_id)
    total = sum(p[3] for p in purchases)
    await update.message.reply_text(f"You have {total} posts remaining.")


async def addposts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /addposts <payment_id> <delta>
    Admin command to add or remove posts from a specific purchase.
    """
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /addposts <payment_id> <delta_posts>")
        return

    try:
        payment_id = int(context.args[0])
        delta = int(context.args[1])
    except ValueError:
        await update.message.reply_text("Both payment_id and delta must be integers.")
        return

    # Perform the update
    add_posts(payment_id, delta)
    username = get_username_by_payment(payment_id)

    action = "Removed" if delta < 0 else "Added"
    await update.message.reply_text(
        f"{action} {abs(delta)} posts on Payment {payment_id} ({username})."
    )
