#!/usr/bin/env python3
# handlers/admin_service_handlers.py
# Admin handlers for boosting service provider management

import logging
import re
from typing import Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from utils.boosting_service_manager import get_boosting_service_manager, ServiceType
from utils.messaging import escape_markdown_v2

logger = logging.getLogger(__name__)

async def admin_services_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin boosting services menu."""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    # Check if user is admin
    from utils.admin_db_utils import is_admin
    if not is_admin(user.id):
        await query.edit_message_text("❌ You don't have permission to access this menu.")
        return
    
    keyboard = [
        [InlineKeyboardButton("📝 Edit Service IDs", callback_data="admin_services_edit")],
        [InlineKeyboardButton("📊 Current Mappings", callback_data="admin_services_current")],
        [InlineKeyboardButton("📋 Audit Log", callback_data="admin_services_audit")],
        [InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data="admin_panel")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    menu_text = (
        "⚙️ *Boosting Service Management*\n\n"
        "Manage provider service IDs for likes and views boosting\\."
    )
    
    await query.edit_message_text(
        menu_text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN_V2
    )

async def admin_services_current_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current provider service mappings."""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    # Check if user is admin
    from utils.admin_db_utils import is_admin
    if not is_admin(user.id):
        await query.edit_message_text("❌ You don't have permission to access this feature.")
        return
    
    # Get current mappings
    mappings = get_boosting_service_manager().get_current_provider_mappings_summary()
    
    if not mappings:
        keyboard = [
            [InlineKeyboardButton("⬅️ Back to Menu", callback_data="admin_services_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "❌ *No Service Mappings Found*\n\n"
            "No active boosting services configured\\.",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    
    # Format mappings for display
    mappings_text = "📊 *Current Provider Service Mappings*\n\n"
    
    for service_type, providers in mappings.items():
        mappings_text += f"**{service_type.title()} Service:**\n"
        for provider_name, service_id in providers.items():
            mappings_text += f"• {escape_markdown_v2(provider_name)}: `{service_id}`\n"
        mappings_text += "\n"
    
    keyboard = [
        [InlineKeyboardButton("📝 Edit These IDs", callback_data="admin_services_edit")],
        [InlineKeyboardButton("🔄 Refresh", callback_data="admin_services_current")],
        [InlineKeyboardButton("⬅️ Back to Menu", callback_data="admin_services_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        mappings_text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN_V2
    )

async def admin_services_edit_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle service ID editing interface."""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    # Check if user is admin
    from utils.admin_db_utils import is_admin
    if not is_admin(user.id):
        await query.edit_message_text("❌ You don't have permission to access this feature.")
        return
    
    # Get current mappings
    mappings = get_boosting_service_manager().get_current_provider_mappings_summary()
    
    if not mappings:
        await query.edit_message_text(
            "❌ *No Service Mappings Found*\n\n"
            "No active boosting services configured\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    
    # Create edit options
    keyboard = []
    
    for service_type, providers in mappings.items():
        for provider_name, service_id in providers.items():
            button_text = f"Edit {provider_name} {service_type} ({service_id})"
            callback_data = f"admin_edit_service_{service_type}_{provider_name}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    keyboard.append([InlineKeyboardButton("⬅️ Back to Menu", callback_data="admin_services_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    edit_text = (
        "📝 *Edit Provider Service IDs*\n\n"
        "Select a provider/service combination to edit:"
    )
    
    await query.edit_message_text(
        edit_text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN_V2
    )

async def admin_edit_specific_service_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle editing of specific service/provider combination."""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    # Check if user is admin
    from utils.admin_db_utils import is_admin
    if not is_admin(user.id):
        await query.edit_message_text("❌ You don't have permission to perform this action.")
        return
    
    # Parse callback data: admin_edit_service_{service_type}_{provider_name}
    match = re.match(r"admin_edit_service_([^_]+)_(.+)", query.data)
    if not match:
        await query.edit_message_text("❌ Invalid service/provider combination.")
        return
    
    service_type_str = match.group(1)
    provider_name = match.group(2)
    
    try:
        service_type = ServiceType(service_type_str)
    except ValueError:
        await query.edit_message_text(f"❌ Invalid service type: {service_type_str}")
        return
    
    # Get current service ID
    current_service_id = get_boosting_service_manager().get_provider_service_id(service_type, provider_name)
    
    if current_service_id is None:
        await query.edit_message_text(
            f"❌ No mapping found for {escape_markdown_v2(provider_name)} {service_type.value} service\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    
    # Store editing context in user_data
    context.user_data["editing_service"] = {
        "service_type": service_type.value,
        "provider_name": provider_name,
        "current_service_id": current_service_id
    }
    
    edit_text = (
        f"📝 *Edit {escape_markdown_v2(provider_name)} {service_type.value.title()} Service ID*\n\n"
        f"**Current Configuration:**\n"
        f"• Provider: {escape_markdown_v2(provider_name)}\n"
        f"• Service Type: {service_type.value.title()}\n"
        f"• Current Service ID: `{current_service_id}`\n\n"
        f"**Please send the new service ID:**\n"
        f"Type the new service ID number and send it\\."
    )
    
    keyboard = [
        [InlineKeyboardButton("❌ Cancel", callback_data="admin_services_edit")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        edit_text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN_V2
    )
    
    # Set flag to await new service ID input
    context.user_data["awaiting_service_id_input"] = True

async def handle_service_id_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle new service ID input from admin."""
    
    if not context.user_data.get("awaiting_service_id_input"):
        return  # Not waiting for service ID input
    
    user = update.message.from_user
    
    # Check if user is admin
    from utils.admin_db_utils import is_admin
    if not is_admin(user.id):
        await update.message.reply_text("❌ You don't have permission to perform this action.")
        return
    
    editing_context = context.user_data.get("editing_service")
    if not editing_context:
        await update.message.reply_text("❌ No editing context found. Please start again.")
        context.user_data.pop("awaiting_service_id_input", None)
        return
    
    # Parse new service ID
    try:
        new_service_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid service ID. Please enter a valid number."
        )
        return
    
    service_type_str = editing_context["service_type"]
    provider_name = editing_context["provider_name"]
    current_service_id = editing_context["current_service_id"]
    
    # Validate new service ID
    if not get_boosting_service_manager().validate_provider_service_id(provider_name, new_service_id):
        await update.message.reply_text(
            f"❌ Invalid service ID for provider {provider_name}. "
            f"Please enter a valid service ID (typically between 1000-99999)."
        )
        return
    
    # Get active service
    service_type = ServiceType(service_type_str)
    active_service = get_boosting_service_manager().get_active_service(service_type)
    
    if not active_service:
        await update.message.reply_text(
            f"❌ No active {service_type.value} service found."
        )
        context.user_data.pop("awaiting_service_id_input", None)
        context.user_data.pop("editing_service", None)
        return
    
    # Show confirmation
    confirmation_text = (
        f"⚠️ *Confirm Service ID Change*\n\n"
        f"**Details:**\n"
        f"• Provider: {escape_markdown_v2(provider_name)}\n"
        f"• Service Type: {service_type.value.title()}\n"
        f"• Previous ID: `{current_service_id}`\n"
        f"• New ID: `{new_service_id}`\n\n"
        f"**Are you sure you want to make this change?**\n"
        f"This will affect all future boosting requests\\."
    )
    
    # Store new service ID for confirmation
    context.user_data["pending_service_update"] = {
        "service_id": active_service.id,
        "provider_name": provider_name,
        "new_service_id": new_service_id,
        "service_type": service_type_str
    }
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm Changes", callback_data="admin_confirm_service_update"),
            InlineKeyboardButton("❌ Cancel", callback_data="admin_services_edit")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        confirmation_text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN_V2
    )
    
    # Clear input flag
    context.user_data.pop("awaiting_service_id_input", None)

async def admin_confirm_service_update_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle confirmation of service ID update."""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    # Check if user is admin
    from utils.admin_db_utils import is_admin
    if not is_admin(user.id):
        await query.edit_message_text("❌ You don't have permission to perform this action.")
        return
    
    pending_update = context.user_data.get("pending_service_update")
    if not pending_update:
        await query.edit_message_text("❌ No pending update found.")
        return
    
    service_id = pending_update["service_id"]
    provider_name = pending_update["provider_name"]
    new_service_id = pending_update["new_service_id"]
    service_type = pending_update["service_type"]
    
    # Perform the update
    success = get_boosting_service_manager().update_provider_service_mapping(
        service_id=service_id,
        provider_name=provider_name,
        new_provider_service_id=new_service_id,
        admin_id=user.id,
        reason=f"Updated via admin interface by {user.username or user.first_name}"
    )
    
    # Clear pending update
    context.user_data.pop("pending_service_update", None)
    context.user_data.pop("editing_service", None)
    
    if success:
        success_text = (
            f"✅ *Service ID Updated Successfully\\!*\n\n"
            f"**Updated Configuration:**\n"
            f"• Provider: {escape_markdown_v2(provider_name)}\n"
            f"• Service Type: {service_type.title()}\n"
            f"• New Service ID: `{new_service_id}`\n\n"
            f"The change has been logged in the audit trail\\."
        )
        
        keyboard = [
            [InlineKeyboardButton("📊 View Current", callback_data="admin_services_current")],
            [InlineKeyboardButton("📝 Edit More", callback_data="admin_services_edit")],
            [InlineKeyboardButton("⬅️ Back to Menu", callback_data="admin_services_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            success_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN_V2
        )
        
    else:
        await query.edit_message_text(
            "❌ *Failed to update service ID*\n\n"
            "A system error occurred\\. Please check the logs and try again\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )

async def admin_services_audit_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show audit log for service changes."""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    # Check if user is admin
    from utils.admin_db_utils import is_admin
    if not is_admin(user.id):
        await query.edit_message_text("❌ You don't have permission to access this feature.")
        return
    
    # Get recent audit entries
    audit_entries = get_boosting_service_manager().get_audit_log(limit=10)
    
    if not audit_entries:
        keyboard = [
            [InlineKeyboardButton("⬅️ Back to Menu", callback_data="admin_services_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "📋 *Service Audit Log*\n\n"
            "No audit entries found\\.",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    
    # Format audit log
    audit_text = "📋 *Service Audit Log*\n\n"
    
    for entry in audit_entries[:5]:  # Show only 5 most recent
        admin_name = entry.get('admin_username', f"Admin_{entry['admin_id']}")
        created_at = entry['created_at'][:19].replace('T', ' ')
        
        audit_text += (
            f"**{entry['action'].title()}** by {escape_markdown_v2(admin_name)}\n"
            f"• Date: {escape_markdown_v2(created_at)}\n"
        )
        
        if entry['old_provider_service_id'] and entry['new_provider_service_id']:
            audit_text += f"• Change: `{entry['old_provider_service_id']}` → `{entry['new_provider_service_id']}`\n"
        
        if entry['reason']:
            audit_text += f"• Reason: {escape_markdown_v2(entry['reason'])}\n"
        
        audit_text += "\n"
    
    if len(audit_entries) > 5:
        audit_text += f"\\.\\.\\. and {len(audit_entries) - 5} more entries"
    
    keyboard = [
        [InlineKeyboardButton("🔄 Refresh", callback_data="admin_services_audit")],
        [InlineKeyboardButton("⬅️ Back to Menu", callback_data="admin_services_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        audit_text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN_V2
    )