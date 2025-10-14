#!/usr/bin/env python3
# handlers/admin_message_handlers.py

import logging
from telegram import Update
from telegram.ext import ContextTypes
from viralmonitor.utils.db import add_post
from utils.admin_db_utils import (
    add_payment,
    add_posts,
    add_custom_plan,
    update_payment,
    reset_purchase,
    reset_affiliate_balance,
    promote_user_to_admin,
    promote_user_to_reply_guy,
    demote_user,
    delete_payment,
    delete_user,
    get_all_users
)

logger = logging.getLogger(__name__)

async def admin_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Catch replies to admin prompts and perform the corresponding DB action.
    Flags set in context.user_data indicate which action to take.
    """
    text = update.message.text.strip() if update.message.text else None

    print(f"Admin message handler received text: {text}")

    # 1) Broadcast message (with optional image)
    if context.user_data.pop("awaiting_broadcast", None):
        # Check if message has photo
        photo = None
        if update.message.photo:
            # Get the largest photo
            photo = update.message.photo[-1].file_id
            # Caption is the text for photo messages
            text = update.message.caption.strip() if update.message.caption else ""
        else:
            text = update.message.text.strip() if update.message.text else ""
        
        sent = 0
        failed = 0
        for uid, *_ in get_all_users():
            try:
                if photo:
                    # Send photo with caption
                    await context.bot.send_photo(
                        chat_id=uid, 
                        photo=photo,
                        caption=text if text else None
                    )
                else:
                    # Send text only
                    await context.bot.send_message(chat_id=uid, text=text)
                sent += 1
            except Exception as e:
                logger.exception("Failed to broadcast to %s: %s", uid, e)
                failed += 1
        
        result_msg = f"✅ Broadcast sent to {sent} users."
        if failed > 0:
            result_msg += f"\n⚠️ Failed to send to {failed} users."
        
        await update.message.reply_text(result_msg)
        logger.info(f"Broadcast completed: sent={sent}, failed={failed}, has_image={photo is not None}")
        return

    # 2) Add payment: "UserID, XUsername, Tier, Posts, TotalCost"
    if context.user_data.pop("awaiting_add_payment", None):
        try:
            parts = [p.strip() for p in text.split(",")]
            if len(parts) != 6:
                raise ValueError("Expected 6 values.")
            uid = int(parts[0])
            xuser = parts[1].lower()
            tier = parts[2].lower()
            comments = int(parts[3])  # Assuming comments is the 4th part
            posts = int(parts[4])
            cost = float(parts[5])
            add_payment(uid, xuser, tier, comments, posts, cost)
            await update.message.reply_text(f"✅ Payment added for user {uid}.")
        except Exception as e:
            logger.exception("Error adding payment")
            await update.message.reply_text(
                "❌ Invalid format. Use: `UserID, XUsername, Tier, Posts, TotalCost`"
            )
        return

    # 3) Add/remove posts: "PaymentID, ΔPosts"
    if context.user_data.pop("awaiting_admin_add_posts", None):
        try:
            pid_str, delta_str = [p.strip() for p in text.split(",")]
            pid = int(pid_str)
            delta = int(delta_str)
            add_posts(pid, delta)
            action = "Removed" if delta < 0 else "Added"
            await update.message.reply_text(
                f"✅ {action} {abs(delta)} posts on payment {pid}."
            )
        except Exception as e:
            logger.exception("Error updating posts")
            await update.message.reply_text(
                "❌ Invalid format. Use: `PaymentID, ΔPosts`"
            )
        return
    
    # 4) Add/remove replies/bonus: "UserID, TG Username, Amount, Day of the Week"
    if context.user_data.pop("awaiting_admin_add_replies", None) or context.user_data.pop("awaiting_admin_add_bonus", None):
        try:
            uid_str, tg_username, amount, dow = [p.strip() for p in text.split(",")]
            amount = int(amount)
            uid = int(uid_str)
            tg_username = tg_username.lower()
            dow = dow.lower()
            add_post(usid=uid, tg_username=tg_username, count=amount, day_of_week=dow)
            action = "Removed" if amount < 0 else "Added"
            await update.message.reply_text(
                f"✅ {action} {abs(amount)} posts on user {uid}."
            )
        except Exception as e:
            logger.exception("Error adding replies/bonus")
            await update.message.reply_text(
                "❌ Invalid format. Use: `UserID, TG Username, Amount, Day of the Week`"
            )
        return

    # 5) Add custom plan: "UserID, PlanName, Likes, Retweets, Comments, Views, MaxPosts"
    if context.user_data.pop("awaiting_add_custom_plan", None):
        try:
            parts = [p.strip() for p in text.split(",")]
            if len(parts) == 5:
                # Old format: UserID, Likes, Retweets, Comments, Views
                uid, likes, rts, cmts, views = [int(p) for p in parts]
                plan_name = "Admin Plan"
                max_posts = 50  # Default
            elif len(parts) == 6:
                # Format: UserID, PlanName, Likes, Retweets, Comments, Views
                uid = int(parts[0])
                plan_name = parts[1]
                likes, rts, cmts, views = [int(p) for p in parts[2:]]
                max_posts = 50  # Default
            elif len(parts) == 7:
                # Full format: UserID, PlanName, Likes, Retweets, Comments, Views, MaxPosts
                uid = int(parts[0])
                plan_name = parts[1]
                likes, rts, cmts, views, max_posts = [int(p) for p in parts[2:]]
            else:
                raise ValueError("Invalid number of parameters")
            
            success = add_custom_plan(uid, likes, rts, cmts, views, plan_name, max_posts)
            if success:
                await update.message.reply_text(f"✅ Custom plan '{plan_name}' created for user {uid} with {max_posts} posts.")
            else:
                await update.message.reply_text(f"❌ Plan name '{plan_name}' already exists for user {uid}.")
        except Exception as e:
            logger.exception("Error adding custom plan")
            await update.message.reply_text(
                "❌ Invalid format. Use: `UserID, PlanName, Likes, Retweets, Comments, Views` or `UserID, Likes, Retweets, Comments, Views`"
            )
        return

    # 6) Update payment: "PaymentID, UserID, Tier, NewTotalCost"
    if context.user_data.pop("awaiting_update_payment", None):
        try:
            pid_str, uid_str, tier, cost_str = [p.strip() for p in text.split(",")]
            pid = int(pid_str)
            uid = int(uid_str)
            cost = float(cost_str)
            tier = tier.lower()
            update_payment(tier, cost, pid, uid)
            await update.message.reply_text(f"✅ Payment {pid} updated.")
        except Exception as e:
            logger.exception("Error updating payment")
            await update.message.reply_text(
                "❌ Invalid format. Use: `PaymentID, UserID, Tier, NewTotalCost`"
            )
        return

    # 7) Reset purchases: "UserID"
    if context.user_data.pop("awaiting_reset_purchase", None):
        try:
            uid = int(text)
            reset_purchase(uid)
            await update.message.reply_text(f"✅ Purchases reset for user {uid}.")
        except Exception:
            await update.message.reply_text("❌ Invalid UserID.")
        return

    # 7) Reset affiliate balance: "UserID"
    if context.user_data.pop("awaiting_reset_affiliate", None):
        try:
            uid = int(text)
            reset_affiliate_balance(uid)
            await update.message.reply_text(f"✅ Affiliate balance reset for user {uid}.")
        except Exception:
            await update.message.reply_text("❌ Invalid UserID.")
        return

    # 8) Promote to admin: "UserID"
    if context.user_data.pop("awaiting_promotion", None):
        try:
            uid = int(text)
            promote_user_to_admin(uid)
            await update.message.reply_text(f"✅ User {uid} promoted to admin.")
        except Exception:
            await update.message.reply_text("❌ Invalid UserID.")
        return

    # 8) Promote to admin: "UserID"
    if context.user_data.pop("awaiting_reply_promotion", None):
        try:
            uid = int(text)
            promote_user_to_reply_guy(uid)
            await update.message.reply_text(f"✅ User {uid} promoted to a reply guy.")
        except Exception:
            await update.message.reply_text("❌ Invalid UserID.")
        return

    # 9) Demote from admin: "UserID"
    if context.user_data.pop("awaiting_demotion", None):
        try:
            uid = int(text)
            demote_user(uid)
            await update.message.reply_text(f"✅ User {uid} demoted from admin.")
        except Exception:
            await update.message.reply_text("❌ Invalid UserID.")
        return

    # 10) Delete payment: "PaymentID"
    if context.user_data.pop("awaiting_delete_payment", None):
        try:
            pid = int(text)
            delete_payment(pid)
            await update.message.reply_text(f"✅ Payment {pid} deleted.")
        except Exception:
            await update.message.reply_text("❌ Invalid PaymentID.")
        return

    # 11) Delete user: "UserID"
    if context.user_data.pop("awaiting_delete_user", None):
        try:
            uid = int(text)
            delete_user(uid)
            await update.message.reply_text(f"✅ User {uid} deleted.")
        except Exception:
            await update.message.reply_text("❌ Invalid UserID.")
        return

    # If no admin flag matched, ignore or pass to other handlers
