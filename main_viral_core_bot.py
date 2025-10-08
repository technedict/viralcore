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
# Ensure BaseFilter is imported (used for custom filter classes)
from telegram.ext.filters import BaseFilter

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
from handlers.link_submission_handlers import (
    submitlink,
    handle_twitter_link,
    x_account_selection_handler,
    tg_account_selection_handler,
    handle_tg_link,
    handle_awaiting_x_poll_details
)
from handlers.raid_balance_handlers import raid, stop_raid, balance, addposts
from handlers.menu_handlers import menu_handler, handle_withdrawal_approval, handle_replies_approval
from handlers.admin_handlers import admin_panel_handler
from handlers.message_handler import message_router
from handlers.track_groups_handler import track_groups
from handlers.link_click_handlers import handle_link_click
from handlers.payment_handler import PaymentHandler

# Enhanced Logging Setup
from utils.logging import setup_logging, get_logger

# Setup comprehensive logging configuration
setup_logging(
    bot_log_level=logging.WARNING,
    console_log_level=logging.INFO,
    debug_file_log_level=logging.DEBUG,
    use_structured_format=True
)

logger = get_logger(__name__)


# --- Custom Filter Class Definition ---
class IsAwaitingXPollDetails(BaseFilter):
    """
    Custom filter used to detect when the user is expected to provide
    X/Twitter poll details. Returns True only if user_data indicates
    we're awaiting the details.
    """
    def __call__(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        if update.effective_user:
            return context.user_data.get("awaiting_x_poll_details", False)
        return False


async def main():
    # Validate and load configuration
    APIConfig.validate()

    # Initialize all databases
    init_main_db()
    init_tweet_db()
    init_tg_db()
    init_groups_db()
    init_custom_db()

    # Initialize shutdown manager job queue (but DO NOT register signal handlers yet)
    shutdown_manager.init_job_queue()

    # Build the application
    app = ApplicationBuilder().token(APIConfig.TELEGRAM_BOT_TOKEN).build()

    # attach app to shutdown manager so it can stop polling / close http client early
    shutdown_manager.set_app(app)

    # Now that the app is attached, register the signal handlers.
    # This ensures signal handler can immediately stop polling and close the client.
    shutdown_manager.setup_signal_handlers()

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
    
    # NEW: Withdrawal management handlers
    from handlers.admin_withdrawal_handlers import (
        admin_pending_withdrawals_handler,
        admin_approve_withdrawal_handler,
        admin_reject_withdrawal_handler,
        admin_withdrawal_stats_handler
    )
    app.add_handler(CallbackQueryHandler(
        admin_pending_withdrawals_handler,
        pattern=r"^admin_withdrawals_pending$"
    ))
    app.add_handler(CallbackQueryHandler(
        admin_approve_withdrawal_handler,
        pattern=r"^admin_approve_withdrawal_\d+$"
    ))
    app.add_handler(CallbackQueryHandler(
        admin_reject_withdrawal_handler,
        pattern=r"^admin_reject_withdrawal_\d+$"
    ))
    app.add_handler(CallbackQueryHandler(
        admin_withdrawal_stats_handler,
        pattern=r"^admin_withdrawals_stats$"
    ))
    
    # NEW: Service management handlers
    from handlers.admin_service_handlers import (
        admin_services_current_handler,
        admin_services_edit_handler,
        admin_edit_specific_service_handler,
        admin_confirm_service_update_handler,
        admin_services_audit_handler
    )
    app.add_handler(CallbackQueryHandler(
        admin_services_current_handler,
        pattern=r"^admin_services_current$"
    ))
    app.add_handler(CallbackQueryHandler(
        admin_services_edit_handler,
        pattern=r"^admin_services_edit$"
    ))
    app.add_handler(CallbackQueryHandler(
        admin_edit_specific_service_handler,
        pattern=r"^admin_edit_service_[^_]+_.+$"
    ))
    app.add_handler(CallbackQueryHandler(
        admin_confirm_service_update_handler,
        pattern=r"^admin_confirm_service_update$"
    ))
    app.add_handler(CallbackQueryHandler(
        admin_services_audit_handler,
        pattern=r"^admin_services_audit$"
    ))
    
    app.add_handler(CallbackQueryHandler(
        admin_panel_handler,
        pattern=r"^admin_"
    ))
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
        pattern=r"^(?!admin_|approve_withdrawal_|reject_withdrawal_|approve_replies_order_|reject_replies_order_).*"
    ))

    # --- Chat Member Handler (track group joins/leaves) ---
    app.add_handler(ChatMemberHandler(
        track_groups,
        ChatMemberHandler.MY_CHAT_MEMBER
    ))

    # Message handlers with grouping and custom filter
    app.add_handler(MessageHandler(
        filters.Regex(r"https?://(?:twitter\.com|x\.com)/.+/status/\d+") & ~filters.COMMAND & filters.ChatType.PRIVATE & IsAwaitingXPollDetails(),
        handle_awaiting_x_poll_details
    ), group=0)

    app.add_handler(MessageHandler(
        filters.Regex(r"https?://(?:twitter\.com|x\.com)/.+/status/\d+") & filters.ChatType.PRIVATE,
        handle_twitter_link
    ), group=1)

    app.add_handler(MessageHandler(
        filters.Regex(r"^https?:\/\/(www\.)?(t\.me|telegram\.me|telegram\.dog)\/"),
        handle_tg_link
    ))

    app.add_handler(MessageHandler(
        filters.Regex(r"https?://bit\.ly/.+"),
        handle_link_click
    ))

    app.add_handler(MessageHandler(
        filters.Regex(r"^(0x[a-fA-F0-9]{64}|[a-fA-F0-9]{64}|[1-9A-HJ-NP-Za-km-z]{43,})$") & filters.ChatType.PRIVATE,
        payment_handler.handle_transaction_hash_input
    ))

    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        message_router
    ))
    
    # Photo handler for admin broadcast with images
    app.add_handler(MessageHandler(
        filters.PHOTO & ~filters.COMMAND,
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

    # Run startup recovery immediately (best-effort; log errors but continue)
    try:
        await startup_recovery()
    except Exception as e:
        logger.error(f"Error during startup recovery: {e}")

    # ----- Application lifecycle management (robust across PTB versions) -----
    try:
        # Initialize internals and start app
        await app.initialize()
        await app.start()

        # Start the Updater/poller if available
        if hasattr(app, "updater") and hasattr(app.updater, "start_polling"):
            try:
                await app.updater.start_polling()
                logger.info("Updater polling started (via app.updater.start_polling()).")
            except Exception as e:
                logger.warning(f"app.updater.start_polling() failed: {e}")
        else:
            logger.info("No app.updater.start_polling available; assuming app will handle polling via handlers.")

        # Wait on the shutdown event exposed by the shutdown manager.
        # The signal handler schedules graceful_shutdown and sets this event.
        shutdown_event = getattr(shutdown_manager, "shutdown_event", None)
        if shutdown_event is not None:
            logger.info("Waiting for shutdown_event from shutdown_manager...")
            await shutdown_event.wait()
        else:
            logger.info("No shutdown_event found on shutdown_manager. Waiting until cancelled (Ctrl+C).")
            stop_event = asyncio.Event()
            try:
                await stop_event.wait()
            except asyncio.CancelledError:
                pass

    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    except Exception:
        logger.exception("Unexpected error while running the bot")
    finally:
        # ----- Clean shutdown -----
        logger.info("Starting clean shutdown of Application and background managers...")

        # First, let shutdown_manager do the heavy lifting: stop polling and close http client
        try:
            await shutdown_manager.graceful_shutdown()
        except Exception:
            logger.exception("Error during graceful_shutdown")

        # Then stop the updater and application as additional cleanup
        if hasattr(app, "updater") and hasattr(app.updater, "stop_polling"):
            try:
                await app.updater.stop_polling()
                logger.info("Updater polling stopped.")
            except Exception:
                logger.exception("Error while stopping updater polling")

        try:
            await app.stop()
        except Exception:
            logger.exception("Error during app.stop()")

        try:
            if hasattr(app, "shutdown"):
                await app.shutdown()
        except Exception:
            logger.exception("Error during app.shutdown()")

    logger.info("Shutdown complete.")


if __name__ == "__main__":
    # Run the main function inside asyncio's event loop.
    asyncio.run(main())
