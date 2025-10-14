#!/usr/bin/env python3
"""
Custom plans selection handlers - allows users to select from multiple custom plans.
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from utils.db_utils import get_user_custom_plans, get_custom_plan

logger = logging.getLogger(__name__)

async def show_custom_plans_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user their available custom plans for selection."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    # Get user's custom plans
    custom_plans = get_user_custom_plans(user_id, active_only=True)
    
    if not custom_plans:
        await query.edit_message_text(
            "❌ You don't have any custom plans available.\n\n"
            "Contact @ViralCore_Support to create custom plans for your account."
        )
        return
    
    # Build selection keyboard
    keyboard = []
    for plan in custom_plans:
        plan_name = plan['plan_name']
        plan_text = f"{plan_name} ({plan['target_likes']}L, {plan['target_retweets']}RT, {plan['target_comments']}C, {plan['target_views']}V)"
        keyboard.append([InlineKeyboardButton(
            plan_text, 
            callback_data=f"select_custom_plan_{plan_name}"
        )])
    
    keyboard.append([InlineKeyboardButton("⬅️ Back to X Plans", callback_data="x_plans")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🎯 **Select Custom Plan**\n\n"
        "Choose which custom plan to use for your link submission:\n\n"
        f"You have {len(custom_plans)} custom plan(s) available:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def handle_custom_plan_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle selection of a specific custom plan."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    # Extract plan name from callback data
    plan_name = query.data.removeprefix("select_custom_plan_")
    
    # Verify plan exists and get details
    plans = get_user_custom_plans(user_id, active_only=True)
    selected_plan = next((p for p in plans if p['plan_name'] == plan_name), None)
    
    if not selected_plan:
        await query.edit_message_text(
            f"❌ Custom plan '{plan_name}' not found or inactive.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Back to Plans", callback_data="custom_plans_selection")
            ]])
        )
        return
    
    # Store selected plan in context
    context.user_data["selected_custom_plan"] = plan_name
    
    # Check if there's a pending post submission to continue
    pending_tweet = context.user_data.get("pending_tweet")
    selected_x_account = context.user_data.get("selected_x_account")
    
    if pending_tweet and selected_x_account:
        # Continue with the post submission process by calling the X account handler again
        await query.edit_message_text(
            f"✅ **Selected Custom Plan: {plan_name}**\n\n"
            f"📊 **Plan Details:**\n"
            f"• Target Likes: {selected_plan['target_likes']}\n"
            f"• Target Retweets: {selected_plan['target_retweets']}\n"
            f"• Target Comments: {selected_plan['target_comments']}\n"
            f"• Target Views: {selected_plan['target_views']}\n\n"
            f"🚀 Processing your post...",
            parse_mode='Markdown'
        )
        
        # Continue the submission by calling the X account selection handler again
        from handlers.link_submission_handlers import x_account_selection_handler
        
        # Modify the query data to simulate the X account selection
        query.data = f"select_x_{selected_x_account}"
        
        await x_account_selection_handler(update, context)
        return
        
    await query.edit_message_text(
        f"✅ **Selected Custom Plan: {plan_name}**\n\n"
        f"📊 **Plan Details:**\n"
        f"• Target Likes: {selected_plan['target_likes']}\n"
        f"• Target Retweets: {selected_plan['target_retweets']}\n"
        f"• Target Comments: {selected_plan['target_comments']}\n"
        f"• Target Views: {selected_plan['target_views']}\n\n"
        f"Now you can submit your X link with `/submitlink` or paste it directly.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⬅️ Back to Plans", callback_data="custom_plans_selection")
        ]]),
        parse_mode='Markdown'
    )

async def show_my_custom_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's custom plans with management options (view only for now)."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    # Get user's custom plans (including inactive ones for management)
    all_plans = get_user_custom_plans(user_id, active_only=False)
    
    if not all_plans:
        await query.edit_message_text(
            "📋 **My Custom Plans**\n\n"
            "❌ You don't have any custom plans yet.\n\n"
            "Contact @ViralCore_Support to create custom plans for your account.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="main_menu")
            ]]),
            parse_mode='Markdown'
        )
        return
    
    # Build plans list
    plans_text = "📋 **My Custom Plans**\n\n"
    
    for i, plan in enumerate(all_plans, 1):
        status = "🟢 Active" if plan['is_active'] else "🔴 Inactive"
        plans_text += (
            f"**{i}. {plan['plan_name']}** {status}\n"
            f"   • Likes: {plan['target_likes']}\n"
            f"   • Retweets: {plan['target_retweets']}\n"
            f"   • Comments: {plan['target_comments']}\n"
            f"   • Views: {plan['target_views']}\n"
            f"   • Created: {plan['created_at'][:10]}\n\n"
        )
    
    keyboard = [
        [InlineKeyboardButton("🎯 Select Plan for Submission", callback_data="custom_plans_selection")],
        [InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="main_menu")]
    ]
    
    await query.edit_message_text(
        plans_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )