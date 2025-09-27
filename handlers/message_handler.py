from telegram import Update
from telegram.ext import ContextTypes
from handlers.admin_message_handlers import admin_message_handler
from handlers.custom_order_handlers import custom_order_handler

async def message_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # context.user_data can be None in some edge cases (e.g., if persistence/user data
    # store not initialized yet). Guard against None so .get calls below are safe.
    raw_flags = getattr(context, "user_data", None)
    flags = raw_flags or {}
    if raw_flags is None:
        # Lightweight debug note; avoids crashing the handler path. Replace with central logger if available.
        # We intentionally do not import project-wide logging here to prevent circular imports.
        print("[message_router] context.user_data was None; using empty dict fallback")

    # Check for service ID input first
    if flags.get("awaiting_service_id_input"):
        from handlers.admin_service_handlers import handle_service_id_input
        await handle_service_id_input(update, context)
        return

    # Check for admin-related flags first
    if any([
        flags.get("awaiting_broadcast"),
        flags.get("awaiting_add_payment"),
        flags.get("awaiting_admin_add_posts"),
        flags.get("awaiting_add_custom_plan"),
        flags.get("awaiting_update_payment"),
        flags.get("awaiting_reset_purchase"),
        flags.get("awaiting_reset_affiliate"),
        flags.get("awaiting_promotion"),
        flags.get("awaiting_reply_promotion"),
        flags.get("awaiting_admin_add_replies"),
        flags.get("awaiting_admin_add_bonus"),
        flags.get("awaiting_demotion"),
        flags.get("awaiting_delete_payment"),
        flags.get("awaiting_delete_user"),
    ]):
        await admin_message_handler(update, context)
    # Check for custom order input flags
    elif any([
        flags.get("awaiting_custom_quantity_input"),
        flags.get("awaiting_x_poll_details"),
        flags.get("awaiting_direct_add_link_input"),
        flags.get("awaiting_slow_push_profile_link"), # New for slow push profile link
        flags.get("awaiting_slow_push_days_input"),   # New for slow push days
        # Add any other flags indicating a user text input for an order
    ]):
        await custom_order_handler(update, context)
    else:
        # Default behavior if no specific flags are set
        # This might be to show a main menu, or a "command not recognized" message
        # For now, let's assume custom_order_handler can handle this too if no flags
        # are set, or you might have a different general message handler.
        # If custom_order_handler is ONLY for flags, then you'll need another
        # general message handler here.
        await custom_order_handler(update, context) # Or a general_message_handler