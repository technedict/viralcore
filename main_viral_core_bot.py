#!/usr/bin/env python3
# main_bot.py

import logging
import asyncio
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ChatMemberHandler,
    filters,
    ContextTypes
)
# Make sure to import BaseFilter
from telegram.ext.filters import BaseFilter # <--- Add this import!

from utils.config import APIConfig
from utils.db_utils import (
    init_main_db,
    init_tweet_db,
    init_groups_db,
    init_custom_db,
    init_tg_db
)
from utils.graceful_shutdown import shutdown_manager
from handlers.start_handler import start
from handlers.link_submission_handlers import submitlink, handle_twitter_link, x_account_selection_handler, tg_account_selection_handler, handle_tg_link, handle_awaiting_x_poll_details
from handlers.raid_balance_handlers import raid, stop_raid, balance, addposts
from handlers.menu_handlers import menu_handler, handle_withdrawal_approval, handle_replies_approval
from handlers.admin_handlers import admin_panel_handler
from handlers.message_handler import message_router
from handlers.track_groups_handler import track_groups
from handlers.link_click_handlers import handle_link_click
from handlers.payment_handler import PaymentHandler

# --- Enhanced Logging Setup ---
from utils.logging import setup_logging, get_logger

# Setup comprehensive logging configuration
setup_logging(
    bot_log_level=logging.WARNING,      # Only WARNING and ERROR to bot.log
    console_log_level=logging.INFO,     # INFO and DEBUG to console
    debug_file_log_level=logging.DEBUG, # All levels to debug.log (filtered)
    use_structured_format=True          # Use JSON structured format
)

logger = get_logger(__name__)

# --- Custom Filter Class Definition ---
# This class will be used as a custom filter for the MessageHandler
class IsAwaitingXPollDetails(BaseFilter): # <--- Inherit from BaseFilter
    def __call__(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """
        Checks if the bot is awaiting X poll details from the user.
        """
        if update.effective_user: # Ensure there's an effective user
            return context.user_data.get("awaiting_x_poll_details", False)
        return False # If no effective user, this filter should not apply


def main():
    # Validate and load configuration
    APIConfig.validate()

    # Initialize all databases
    init_main_db()
    init_tweet_db()
    init_tg_db()
    init_groups_db()
    init_custom_db()
    
    # Initialize shutdown manager and setup signal handlers
    shutdown_manager.setup_signal_handlers()
    shutdown_manager.init_job_queue()

    # Build the application
    app = ApplicationBuilder().token(APIConfig.TELEGRAM_BOT_TOKEN).build()

    # Instantiate and store the shared PaymentHandler
    payment_handler = PaymentHandler()
    app.bot_data["payment_handler"] = payment_handler

    # --- Command Handlers ---
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("submitlink", submitlink))
    app.add_handler(CommandHandler("raid", raid))
    app.add_handler(CommandHandler("stopraid", stop_raid))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("addposts", addposts))

    # --- CallbackQuery Handlers ---
    app.add_handler(CallbackQueryHandler(
        x_account_selection_handler,
        pattern=r"^select_x_"
    ))
    app.add_handler(CallbackQueryHandler(
        tg_account_selection_handler,
        pattern=r"^select_tg_"
    ))
    app.add_handler(CallbackQueryHandler(
        admin_panel_handler,
        pattern=r"^admin_"
    ))
    # NEW: Specific handler for withdrawal approvals/rejections
    app.add_handler(CallbackQueryHandler(
        handle_withdrawal_approval,
        pattern=r"^(approve_withdrawal_|reject_withdrawal_)\d+$"
    ))
    app.add_handler(CallbackQueryHandler(
        handle_replies_approval,
        pattern=r"^(approve_replies_order_|reject_replies_order_)\d+$"
    ))
    app.add_handler(CallbackQueryHandler(
        menu_handler,
        # Updated pattern: Matches anything that is NOT 'admin_', 'approve_withdrawal_', or 'reject_withdrawal_'
        pattern=r"^(?!admin_|approve_withdrawal_|reject_withdrawal_|approve_replies_order_|reject_replies_order_).*"
    ))

    # --- Chat Member Handler (track group joins/leaves) ---
    app.add_handler(ChatMemberHandler(
        track_groups,
        ChatMemberHandler.MY_CHAT_MEMBER
    ))

   # 1. Register the handler that specifically waits for poll details.
    # It uses our custom filter class instance.
    # This handler must be added *before* the general Twitter/X link handler.
    app.add_handler(MessageHandler(
        filters.Regex(r"https?://(?:twitter\.com|x\.com)/.+/status/\d+") & ~filters.COMMAND & filters.ChatType.PRIVATE & IsAwaitingXPollDetails(), # <--- Use an instance of the class!
        handle_awaiting_x_poll_details
    ), group=0) # Assign a group with higher priority (lower number)

    # 2. Register the general Twitter/X link handler.
    # This will only be reached if the custom filter did NOT match.
    app.add_handler(MessageHandler(
        filters.Regex(r"https?://(?:twitter\.com|x\.com)/.+/status/\d+") & filters.ChatType.PRIVATE,
        handle_twitter_link
    ), group=1) # Assign a group with lower priority (higher number)

    app.add_handler(MessageHandler(
        filters.Regex(r"^https?:\/\/(www\.)?(t\.me|telegram\.me|telegram\.dog)\/"),
        handle_tg_link
    ))

    # Bitly click‐tracking links
    app.add_handler(MessageHandler(
        filters.Regex(r"https?://bit\.ly/.+"),
        handle_link_click
    ))

    # Transaction hash replies (crypto payments)
    app.add_handler(MessageHandler(
        filters.Regex(r"^(0x[a-fA-F0-9]{64}|[a-fA-F0-9]{64}|[1-9A-HJ-NP-Za-km-z]{43,})$")
        & filters.ChatType.PRIVATE,
        payment_handler.handle_transaction_hash_input
    ))

    # --- Fallback Text Handlers ---
    # Admin replies to flagged prompts
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        message_router
    ))

    logger.info("Bot is up and running!")
    
    # Register cleanup callback for recovery on startup
    async def startup_recovery():
        logger.info("Performing startup recovery...")
        recovered_jobs = await shutdown_manager.recover_stale_jobs(threshold_minutes=30)
        if recovered_jobs > 0:
            logger.info(f"Recovered {recovered_jobs} stale jobs on startup")
    
    shutdown_manager.register_cleanup_callback(startup_recovery)
    
    try:
        # Run startup recovery
        asyncio.create_task(startup_recovery())
        
        # Start the bot
        app.run_polling()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    finally:
        # Perform graceful shutdown
        asyncio.run(shutdown_manager.graceful_shutdown())

if __name__ == "__main__":
    main()