#!/usr/bin/env python3
# handlers/custom_order_handlers.py

import re
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from fuzzywuzzy import process

# Assuming these imports are correct based on your project structure
from utils.db_utils import update_purchase_x_username, get_user
from utils.menu_utils import clear_bot_messages, main_menu_keyboard # MODIFIED: Import main_menu_keyboard
from utils.messaging import escape_markdown_v2
from utils.config import APIConfig # Import APIConfig to access ADMIN_IDS
from utils.payment_utils import initiate_flutterwave_transfer, get_usd_to_ngn_rate
from utils.notification import notify_admin # NEW: Import the admin notification utility
from utils.withdrawal_settings import get_withdrawal_mode # NEW: Import the withdrawal mode getter
from handlers.menu_handlers import _process_quantity_and_set_next_step, menu_handler # NEW: Import helper and menu_handler
from viralmonitor.utils.db import remove_amount, get_total_amount

logger = logging.getLogger(__name__)

async def custom_order_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Catch free-text replies for:
      - Setting the user’s X username
      - Entering a custom post quantity (for various plan types)
      - Entering post-payment details (X poll, direct add, slow push)
      - Entering withdrawal details
    """
    raw_flags_context = getattr(context, "user_data", None)
    raw_flags_update = getattr(update, "message", None)
    if raw_flags_context is None:
        logger.error("custom_order_handler called but context.user_data is None")
        return
    elif raw_flags_update is None or update.message.text is None:
        logger.error("custom_order_handler called but update.message or update.message.text is None")
        return
    text = update.message.text.strip()
    chat_type = update.effective_chat.type
    user_id = update.effective_user.id
    user_first_name = update.effective_user.first_name
    user_username = update.effective_user.username

    logger.info(f"Custom order handler received text: '{text}' (chat_type={chat_type}, user_id={user_id})")

    # --- 1) X-username prompt ---
    if context.user_data.pop("awaiting_x_username", None) or context.user_data.pop("awaiting_tg_username", None):
        xuser = text.lstrip("@").strip()
        if not xuser:
            await update.message.reply_text(
                "❌ Username can’t be empty. Please send it again without ‘@’."
            )
            return
        xuser = xuser.lower()  # Normalize to lowercase
        update_purchase_x_username(user_id, xuser)
        if context.user_data.pop("awaiting_tg_username", None):
            await update.message.reply_text(
                f"✅ TG username set to @{escape_markdown_v2(xuser)}\!\n\n"
                "Now you can submit your link with /submitlink or paste it here\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        else:
            await update.message.reply_text(
                f"✅ X username set to @{escape_markdown_v2(xuser)}\!\n\n"
                "Now you can submit your link with /submitlink or paste it here\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
        return

    # --- 2) Custom quantity prompt (Unified for all custom quantity inputs) ---
    if context.user_data.pop("awaiting_custom_quantity_input", None): # Renamed flag from custom_quantity_order
        logger.info(f"User {user_id} is inputting custom quantity: {text}")
        try:
            qty = int(text)
            if qty <= 0:
                raise ValueError("Quantity must be a positive number.")

            plan_type = context.user_data.pop("custom_plan_type", None) # Get the stored plan type
            
            if not plan_type:
                logger.error(f"User {user_id} awaiting_custom_quantity_input but no custom_plan_type. Context: {context.user_data}")
                await update.message.reply_text("Something went wrong with the plan type. Please restart from the menu.")
                await menu_handler(update, context) # Redirect to main menu
                return

            # Determine minimum quantity and back_callback based on plan_type
            min_qty = 10 # Default minimum
            back_callback = "main_menu" # Default fallback
            
            if plan_type == "x_poll":
                min_qty = 10
                back_callback = "poll_plans_x"
            elif plan_type == "tg_custom":
                min_qty = 10
                back_callback = f"tgc_{context.user_data.get('tqty', '')}" # tqty should be present for tg_custom
            elif plan_type == "x_engagement":
                min_qty = 10
                back_callback = "confirm_amount" # This is the "select quantity" menu for X engagement
            elif plan_type == "direct_add":
                min_qty = APIConfig.FOLLOWER_DETAILS.get("direct_add", {}).get("min_qty", 50) # Assuming 50 if not set
                back_callback = "direct_add_select_qty"
            elif plan_type == "slow_push":
                min_qty = APIConfig.FOLLOWER_DETAILS.get("slow_push", {}).get("min_qty", 100) # Assuming 100 if not set
                back_callback = "slow_push_select_qty"
            elif plan_type == "tg_premium":
                min_qty = 50 # Example min for premium members
                back_callback = "premium_plans_tg"
            else:
                logger.warning(f"Unknown plan_type '{plan_type}' for custom quantity input for user {user_id}. Using default min_qty and back_callback.")


            if qty < min_qty:
                await update.message.reply_text(f"Minimum quantity for this service is {min_qty}. Please try again.")
                return

            # For Slow Push, ensure quantity is a multiple of 10
            if plan_type == "slow_push" and qty % 10 != 0:
                await update.message.reply_text(f"For Slow Push, quantity must be in multiples of 10. Please try again.")
                return

            # Call _process_quantity_and_set_next_step with the custom quantity
            # This function will calculate cost and set up the payment buttons
            response_text, response_keyboard, slide_key = await _process_quantity_and_set_next_step(
                update, context, qty=qty, back_callback=back_callback, plan_type=plan_type
            )

            if response_text:
                await clear_bot_messages(update, context)
                await update.message.reply_text(
                    text=escape_markdown_v2(response_text),
                    reply_markup=InlineKeyboardMarkup(response_keyboard),
                    parse_mode=ParseMode.MARKDOWN_V2
                )
            return

        except ValueError as e:
            await update.message.reply_text(f"❌ Invalid quantity: {escape_markdown_v2(str(e))}. Please enter a whole number.", parse_mode=ParseMode.MARKDOWN_V2)
            return
        except Exception as e:
            logger.exception(f"Error processing custom quantity for user {user_id}: {e}")
            await update.message.reply_text(
                "An unexpected error occurred while processing your quantity. Please try again or contact support."
            )
            return


    if context.user_data.pop("awaiting_slow_push_input", None):

        # Retrieve order details from context.user_data
        qty = context.user_data.pop("qty", None)
        total_cost = context.user_data.pop("total_cost", None)

        days = int(text)
        if days <= 0:
            raise ValueError("Quantity must be a positive number.")
        
        await update.message.reply_text(
            f"With this, you’re getting {qty} followers spread across {days} days.\n\nProceed to payment?"
        )
        keyboard = [
            [InlineKeyboardButton("Crypto", callback_data="payment_crypto"),
             InlineKeyboardButton("Bank", callback_data="payment_bank")],
            [InlineKeyboardButton("⬅️ Back", callback_data="followers_plans_x")]
        ]
        context.user_data["days"] = days # Store the number of days for later use


    # --- 3) Post-Payment Details: X Poll Link and Option ---
    if context.user_data.pop("awaiting_x_poll_details", None):
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
                return
            if not (1 <= option_number <= 4): # Assuming polls have 2-4 options
                await update.message.reply_text("Option number should be 1, 2, 3, or 4. Please try again.")
                return

            # Retrieve order details from context.user_data
            ordered_quantity = context.user_data.pop("ordered_quantity", None)
            total_cost = context.user_data.pop("total_cost", None)
            
            # Clear other relevant flags that might have been set by payment handler
            context.user_data.pop("current_plan_type", None)
            context.user_data.pop("is_x_poll_order", None) # Clear specific order flag

            if not ordered_quantity or not total_cost:
                logger.error(f"Missing data for X Poll order completion for user {user_id}. Context: {context.user_data}")
                await update.message.reply_text("An error occurred with your order details. Please contact support.")
                await menu_handler(update, context) # Redirect to main menu
                return

            # Notify admin about X Poll order
            admin_message = (
                f"🚀 *New X Poll Order!* 🚀\n\n"
                f"👤 User: {update.effective_user.mention_markdown_v2()} (ID: `{user_id}`)\n"
                f"🔗 Poll Link: `{escape_markdown_v2(x_poll_link)}`\n"
                f"🔢 Option Number: `{option_number}`\n"
                f"📦 Quantity: `{ordered_quantity}` votes\n"
                f"💰 Total Cost: `${total_cost:.2f}`\n\n"
                f"Status: *Paid (Manual Process Required)*"
            )
            await notify_admin(user_id, admin_message)

            await update.message.reply_text(
                "Thank you! Your X Poll order has been received. "
                "We've sent the details to our team and they will process it shortly."
            )
            await menu_handler(update, context) # Redirect to main menu
            return
        else:
            await update.message.reply_text(
                "Invalid format. Please send the X poll link and option number separated by a comma (e.g., `https://x.com/status/12345/polls/abcdef, 1`)."
            )
            return

    # --- 4) Post-Payment Details: Direct Add Followers Link ---
    if context.user_data.pop("awaiting_direct_add_link_input", None):
        logger.info(f"User {user_id} is inputting Direct Add link: {text}")
        x_profile_link = text.strip()

        if not (x_profile_link.startswith("https://x.com/") or x_profile_link.startswith("https://twitter.com/")):
            await update.message.reply_text("That doesn't look like a valid X (Twitter) profile link. Please send a correct link (e.g., `https://x.com/username`).")
            return

        # Retrieve order details from context.user_data
        ordered_quantity = context.user_data.pop("ordered_quantity", None)
        total_cost = context.user_data.pop("total_cost", None)
        
        # Clear other relevant flags
        context.user_data.pop("current_plan_type", None)
        context.user_data.pop("is_direct_add_order", None)

        if not ordered_quantity or not total_cost:
            logger.error(f"Missing data for Direct Add order completion for user {user_id}. Context: {context.user_data}")
            await update.message.reply_text("An error occurred with your order details. Please contact support.")
            await menu_handler(update, context)
            return

        # Notify admin about Direct Add order with link
        admin_message = (
            f"🚀 *New Direct Add Followers Order!* 🚀\n\n"
            f"👤 User: {update.effective_user.mention_markdown_v2()} (ID: `{user_id}`)\n"
            f"🔗 X Profile Link: `{escape_markdown_v2(x_profile_link)}`\n"
            f"📦 Quantity: `{ordered_quantity}` followers\n"
            f"💰 Total Cost: `${total_cost:.2f}`\n\n"
            f"Status: *Paid (Manual Process Required)*"
        )
        await notify_admin(user_id, admin_message)

        await update.message.reply_text(
            "Thank you! Your Direct Add Followers order has been received. "
            "We've sent the details to our team and they will process it shortly."
        )
        await menu_handler(update, context) # Redirect to main menu
        return

    # --- 5) Post-Payment Details: Slow Push - Profile Link ---
    if context.user_data.pop("awaiting_slow_push_profile_link", None):
        logger.info(f"User {user_id} is inputting Slow Push profile link: {text}")
        x_profile_link = text.strip()

        if not (x_profile_link.startswith("https://x.com/") or x_profile_link.startswith("https://twitter.com/")):
            await update.message.reply_text("That doesn't look like a valid X (Twitter) profile link. Please send a correct link (e.g., `https://x.com/username`).")
            return

        context.user_data["profile_link_for_slow_push"] = x_profile_link # Store the link
        context.user_data["awaiting_slow_push_days_input"] = True # Now set the next flag
        await update.message.reply_text("Got it! Now, how many *days* should this order run for (e.g., `7`)?")
        return

    # --- 6) Post-Payment Details: Slow Push - Number of Days ---
    if context.user_data.pop("awaiting_slow_push_days_input", None):
        logger.info(f"User {user_id} is inputting Slow Push days: {text}")
        try:
            num_days = context.user_data.pop("days", None)
            # Retrieve order details from context.user_data
            ordered_quantity = context.user_data.pop("ordered_quantity", None)
            total_cost = context.user_data.pop("total_cost", None)
            user_profile_link = context.user_data.pop("profile_link_for_slow_push", None) # Retrieve stored link

            # Clear other relevant flags
            context.user_data.pop("current_plan_type", None)
            context.user_data.pop("is_slow_push_order", None)

            if not user_profile_link or not ordered_quantity or not total_cost:
                 logger.error(f"Missing data for Slow Push order completion for user {user_id}. Context: {context.user_data}")
                 await update.message.reply_text("An error occurred with your order details. Please contact support.")
                 await menu_handler(update, context)
                 return

            # Notify admin about Slow Push order with days
            admin_message = (
                f"🚀 *New Slow Push Followers Order!* 🚀\n\n"
                f"👤 User: {update.effective_user.mention_markdown_v2()} (ID: `{user_id}`)\n"
                f"🔗 X Profile Link: `{escape_markdown_v2(user_profile_link)}`\n"
                f"📦 Quantity: `{ordered_quantity}` followers\n"
                f"📅 Over Days: `{num_days}` days\n"
                f"💰 Total Cost: `${total_cost:.2f}`\n\n"
                f"Status: *Paid (Manual Process Required)*"
            )
            await notify_admin(user_id, admin_message)

            await update.message.reply_text(
                "Thank you! Your Slow Push Followers order has been received. "
                "We've sent the details to our team and they will process it shortly."
            )
            await menu_handler(update, context) # Redirect to main menu
            return

        except ValueError:
            await update.message.reply_text("Invalid number of days. Please enter a whole number.")
            return

    # --- 7) TG Channel prompt (Original functionality, re-indexed) ---
    if context.user_data.pop("awaiting_tg_channel_username", None):
        logger.info(f"User {user_id} is inputting TG channel username: {text}")
        members_amount = context.user_data.get("qty")
        channel = text

        if not members_amount:
            await update.message.reply_text(
                "Something went wrong. Please contact support"
            )
            logger.error(f"User {user_id} didn't get the amount of members for TG channel.")
            return

        admin_message = (
            f" *NEW MEMBERS REQUEST!* \n\n"
            f"Amount: {escape_markdown_v2(str(members_amount))}\n"
            f"Channel Name: {escape_markdown_v2(channel)}\n"
            f"Requested by: [{escape_markdown_v2(user_first_name)}](tg://user?id={user_id})"
            f"{f' \\(@{escape_markdown_v2(user_username)}\\)' if user_username else ''}\n"
        )
        await notify_admin(user_id, admin_message) # Using the centralized notify_admin

        reply_text = (
            f"✅ Your request for {escape_markdown_v2(str(members_amount))} MEMBERS has been sent and "
            "is being processed"
        )
        await update.message.reply_text(reply_text, parse_mode=ParseMode.MARKDOWN_V2)
        await menu_handler(update, context) # Redirect to main menu
        return

    # --- 8) Withdraw quantity prompt ---
    if context.user_data.pop("withdraw_order", None):
        logger.info(f"User {user_id} is inputting withdrawal quantity: {text}")
        is_affiliate_withdrawal = context.user_data.get("is_affiliate_withdrawal", False)
        rate = get_usd_to_ngn_rate()

        balance_usd = 0
        if is_affiliate_withdrawal:
            ref_balance = context.user_data.get("ref_balance")
            balance_usd = ref_balance
        else:
            # Assuming get_total_amount returns USD for post earnings
            balance_usd = get_total_amount(user_id)
        try:
            qnty_requested = float(text)
            if qnty_requested <= 0:
                raise ValueError("Withdrawal amount must be greater than zero.")
            
            if qnty_requested > balance_usd:
                raise ValueError(f"You requested ${qnty_requested:.2f}, but you only have ${balance_usd:.2f}. You exceeded the available amount.")
        except ValueError as e:
            await update.message.reply_text(f"❌ Invalid quantity: {escape_markdown_v2(str(e))}", parse_mode=ParseMode.MARKDOWN_V2)
            return
        
        # --- FIX STARTS HERE ---
        # Ensure `withdrawal_amount_ngn` is always defined
        if is_affiliate_withdrawal:
            withdrawal_amount_ngn = qnty_requested * rate
            back_callback = "affiliate_balance"
        else:
            withdrawal_amount_ngn = qnty_requested
            back_callback = "reply_guys_panel" # Assuming this is the correct callback for non-affiliate withdrawals

        context.user_data["withdrawal_amount_usd"] = qnty_requested
        context.user_data["withdrawal_amount_ngn"] = withdrawal_amount_ngn
        # Add payment mode support (default to automatic for backwards compatibility)
        context.user_data["payment_mode"] = context.user_data.get("payment_mode", "automatic")
        context.user_data["awaiting_bank_details"] = True

        # Display payment mode info to user
        payment_mode_text = ""
        if context.user_data["payment_mode"] == "manual":
            payment_mode_text = "\n\n⚠️ *Manual processing mode* - Your request will require admin approval before funds are transferred\\."
        
        reply_text = (
            f"Please submit your bank details in this format: "
            f"Account Name, Account Number, Bank Name \\(Full Name NOT Abbreviated\\)\\.\n\n"
            f"We will process your withdrawal of *₦{int(withdrawal_amount_ngn)}*{payment_mode_text}"
        )
        
        # Define keyboard unconditionally before `InlineKeyboardMarkup` is called
        keyboard = [
            [InlineKeyboardButton("Back", callback_data=back_callback)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(reply_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
        return

    # --- 9) Bank Details prompt for withdrawal - UPDATED TO USE NEW WITHDRAWAL SERVICE ---
    if context.user_data.pop("awaiting_bank_details", None):
        logger.info(f"User {user_id} is inputting bank details for withdrawal.")
        
        # Import new withdrawal service
        from utils.withdrawal_service import get_withdrawal_service, PaymentMode
        withdrawal_service = get_withdrawal_service()
        
        withdrawal_amount_usd = context.user_data.get("withdrawal_amount_usd")
        withdrawal_amount_ngn = context.user_data.get("withdrawal_amount_ngn")
        is_affiliate_withdrawal = context.user_data.get("is_affiliate_withdrawal", False)
        payment_mode_enum = get_withdrawal_mode()
        bank_details_raw_input = text # Keep original user input for storage

        if withdrawal_amount_ngn is None:
            await update.message.reply_text(
                "Something went wrong\. Please try initiating the withdrawal again\."
            )
            logger.error(f"withdrawal_amount_ngn not found for user {user_id} during bank details submission.")
            return

        # Check for existing pending withdrawals for this user
        user_withdrawals = withdrawal_service.get_user_withdrawals(user_id, limit=5)
        pending_withdrawal = None
        for wd in user_withdrawals:
            if wd.status.value in ['pending'] or (wd.payment_mode == PaymentMode.MANUAL and wd.admin_approval_state and wd.admin_approval_state.value == 'pending'):
                pending_withdrawal = wd
                break
        
        if pending_withdrawal:
            await update.message.reply_text(
                "⌛ You already have a pending withdrawal request in progress\. "
                "\n\nPlease wait for your previous request to be completed or rejected "
                "before making a new one\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            logger.info(f"User {user_id} tried to create multiple withdrawal requests while one is pending (Request ID: {pending_withdrawal.id}).")
            return # Stop processing if a pending request exists

        # --- 2. Check user's current balance ---
        user_current_balance_ngn = get_total_amount(user_id) # Call your balance function
        # print(user_current_balance_ngn)

        if withdrawal_amount_ngn > user_current_balance_ngn:
            await update.message.reply_text(
                f"🚫 Insufficient Balance\! \n\nYou are trying to withdraw *₦{int(withdrawal_amount_ngn)}*, "
                f"but your current available balance is only *₦{int(user_current_balance_ngn)}*\.\n\n "
                "Please enter an amount within your available balance\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            logger.warning(f"User {user_id} attempted withdrawal (₦{withdrawal_amount_ngn}) with insufficient balance (₦{user_current_balance_ngn}).")
            # Clear related user_data
            context.user_data.pop("withdrawal_amount_usd", None)
            context.user_data.pop("withdrawal_amount_ngn", None)
            context.user_data.pop("is_affiliate_withdrawal", None)
            context.user_data.pop("payment_mode", None)
            return

        # Validate bank details format
        cleaned_parts = [
            part.strip()
            for line in bank_details_raw_input.splitlines()
            for part in line.split(',')
            if part.strip()
        ]

        if len(cleaned_parts) == 3:
            account_name = cleaned_parts[0]
            account_number = cleaned_parts[1]
            bank_name = cleaned_parts[2]
        else:
            await update.message.reply_text(
                "❌ Invalid Bank Details! \n\nMake sure your details are in this format: "
                "Account Name, Account Number, Bank Name (Full Name NOT Abbreviated).",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return

        # Convert payment mode string to enum
        try:
            payment_mode = PaymentMode.from_withdrawal(payment_mode_enum)
            print(payment_mode)
        except ValueError:
            payment_mode = PaymentMode.AUTOMATIC  # Default fallback
        
        # Create withdrawal using new service
        try:
            withdrawal = withdrawal_service.create_withdrawal(
                user_id=user_id,
                amount_usd=withdrawal_amount_usd,
                amount_ngn=withdrawal_amount_ngn,
                account_name=account_name,
                account_number=account_number,
                bank_name=bank_name,
                bank_details_raw=bank_details_raw_input,
                is_affiliate_withdrawal=is_affiliate_withdrawal,
                payment_mode=payment_mode
            )
            
            logger.info(f"Withdrawal {withdrawal.id} created for user {user_id} in {payment_mode.value} mode")
            
            # Handle automatic vs manual processing
            if payment_mode == PaymentMode.AUTOMATIC:
                # Process automatically with Flutterwave
                success = withdrawal_service.process_automatic_withdrawal(withdrawal)
                
                if success:
                    await update.message.reply_text(
                        f"✅ *Withdrawal Processed Successfully\\!*\n\n"
                        f"Amount: *₦{int(withdrawal_amount_ngn)}*\n"
                        f"Your balance has been updated and the transfer has been initiated\\.",
                        parse_mode=ParseMode.MARKDOWN_V2
                    )
                else:
                    await update.message.reply_text(
                        "❌ *Withdrawal Processing Failed*\n\n"
                        "There was an issue processing your withdrawal\\. "
                        "Please contact support if this continues\\.",
                        parse_mode=ParseMode.MARKDOWN_V2
                    )
            
            else:  # Manual processing
                # Notify admin for manual approval
                escaped_bank_details_for_display = escape_markdown_v2(bank_details_raw_input)
                
                admin_approval_message = (
                    f"🔔 *NEW MANUAL WITHDRAWAL REQUEST\\!* 🔔\n\n"
                    f"User: [{escape_markdown_v2(user_first_name)}](tg://user?id={user_id})"
                    f"{f' \\(@{escape_markdown_v2(user_username)}\\)' if user_username else ''}\n"
                    f"Withdrawal Type: {escape_markdown_v2('Affiliate' if is_affiliate_withdrawal else 'Standard')}\n"
                    f"Amount: *₦{int(withdrawal_amount_ngn)}*\n"
                    f"Bank Details:\n`{escaped_bank_details_for_display}`\n\n"
                    f"Request ID: `{withdrawal.id}`\n\n"
                    f"⚠️ *Manual processing* \\- Balance will be deducted only upon approval\\."
                )

                # Use new admin approval buttons
                approval_keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Approve", callback_data=f"admin_approve_withdrawal_{withdrawal.id}")],
                    [InlineKeyboardButton("❌ Reject", callback_data=f"admin_reject_withdrawal_{withdrawal.id}")]
                ])

                await notify_admin(user_id, admin_approval_message, reply_markup=approval_keyboard)

                await update.message.reply_text(
                    f"✅ Your manual withdrawal request for *₦{int(withdrawal_amount_ngn)}* has been submitted "
                    "and is awaiting admin approval\. We will notify you once it's processed\."
                    , parse_mode=ParseMode.MARKDOWN_V2
                )
            
            # Clear user data
            context.user_data.pop("withdrawal_amount_usd", None)
            context.user_data.pop("withdrawal_amount_ngn", None)
            context.user_data.pop("is_affiliate_withdrawal", None)
            context.user_data.pop("payment_mode", None)
            
        except Exception as e:
            logger.error(f"Failed to create withdrawal for user {user_id}: {str(e)}")
            await update.message.reply_text(
                "❌ *System Error*\n\n"
                "Failed to create withdrawal request\\. Please try again or contact support\\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return

        keyboard = [
            [InlineKeyboardButton("Back to Panel", callback_data="reply_guys_panel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text("Navigate back to your panel:", reply_markup=reply_markup)
        return


    if context.user_data.pop("submit_replies_order", None):
        logger.info(f"User {user_id} is inputting replies order details.")
        text = update.message.text # Get the user's input

        # Define a threshold for what you consider a "close enough" match
        # A score of 80-85 is often a good starting point, adjust as needed.
        similarity_threshold = 75 # You can adjust this value

        # Access and initialize pending_replies_orders and next_replies_order_id from bot_data
        if "pending_replies_orders" not in context.bot_data:
            context.bot_data["pending_replies_orders"] = {}
        if "next_replies_order_id" not in context.bot_data:
            context.bot_data["next_replies_order_id"] = 1

        pending_replies_orders = context.bot_data["pending_replies_orders"]
        next_replies_order_id = context.bot_data["next_replies_order_id"]

        # --- 1. Check for existing pending replies orders from this user ---
        for req_id, order_data in pending_replies_orders.items():
            if order_data["user_id"] == user_id:
                await update.message.reply_text(
                    "⌛ You already have a pending replies order request in progress\\. "
                    "\n\nPlease wait for your previous request to be completed or rejected "
                    "before making a new one\\.",
                    parse_mode=ParseMode.MARKDOWN_V2
                )
                logger.info(f"User {user_id} tried to create multiple replies orders while one is pending (Request ID: {req_id}).")
                return # Stop processing if a pending request exists

        # --- 2. Parse and Validate User Input ---
        # Expected format: "Number of replies, Day of the week" e.g., "50, Monday"
        parts = [p.strip() for p in text.split(',')]

        if len(parts) == 2:
            try:
                num_replies = int(parts[0])
                # Use the raw input for fuzzy matching, then capitalize the *result*
                # This prevents issues if the user types "monday" but closest match is "Monday"
                input_day_str = parts[1]
                day_of_week = input_day_str.capitalize() # Initial capitalization for consistency

                # Basic validation for num_replies
                if num_replies <= 0:
                    await update.message.reply_text(
                        "❌ Invalid number of replies\\. Please enter a positive number of replies\\."
                    )
                    return

                # Basic validation for day of week (you can make this more robust)
                valid_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

                # Determine the final day_of_week to use
                final_day_of_week = None # Initialize to None

                if day_of_week in valid_days:
                    # If an exact match, use it directly
                    final_day_of_week = day_of_week
                    escaped_day = escape_markdown_v2(final_day_of_week)
                    await update.message.reply_text(f"✅ Understood\\. You selected *{escaped_day}*\\.", parse_mode=ParseMode.MARKDOWN_V2)
                else:
                    # If not an exact match, try fuzzy matching
                    closest_match, score = process.extractOne(input_day_str, valid_days) # Use raw input for fuzzy match

                    if score >= similarity_threshold:
                        # If a close enough match is found, automatically use it
                        original_input_escaped = escape_markdown_v2(input_day_str) # Escape the *original* input
                        corrected_day_escaped = escape_markdown_v2(closest_match)

                        await update.message.reply_text(
                            f"💡 I didn't recognize '{original_input_escaped}'\\. Assuming you meant *{corrected_day_escaped}*\\.\n\n"
                            f"Proceeding with *{corrected_day_escaped}*\\."
                            , parse_mode=ParseMode.MARKDOWN_V2
                        )
                        final_day_of_week = closest_match # Set the corrected day
                    else:
                        # If no close enough match is found, then genuinely tell them it's invalid
                        await update.message.reply_text(
                            f"❌ Invalid Day of the Week\\. Please enter a valid day "
                            f"\(e\\.g\\., Monday, Tuesday, etc\\.\\)\\."
                            , parse_mode=ParseMode.MARKDOWN_V2
                        )
                        return # Stop execution because the input is invalid

                # --- IMPORTANT: Now, use final_day_of_week for the rest of your logic ---
                # --- 3. Store the pending order and notify admin ---
                request_id = next_replies_order_id
                pending_replies_orders[request_id] = {
                    "user_id": user_id,
                    "user_first_name": user_first_name,
                    "user_username": user_username,
                    "num_replies": num_replies,
                    "day_of_week": final_day_of_week, # Use the validated/corrected day here
                    "timestamp": update.message.date.isoformat(),
                    "user_message_id": update.message.message_id
                }
                context.bot_data["next_replies_order_id"] += 1

                admin_approval_message = (
                    f"🔔 *NEW REPLIES ORDER REQUEST AWAITING APPROVAL\!* 🔔\n\n"
                    f"User: [{escape_markdown_v2(user_first_name)}](tg://user?id={user_id})"
                    f"{f' \\(@{escape_markdown_v2(user_username)}\\)' if user_username else ''}\n"
                    f"Requested Replies: *{num_replies}*\n"
                    f"Day of Week: *{escape_markdown_v2(final_day_of_week)}*\n\n" # Escape this too
                    f"Request ID: `{request_id}`\n\n"
                    f"Click 'Approve' to add this order to the user's database\."
                )

                approval_keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Approve Replies", callback_data=f"approve_replies_order_{request_id}")],
                    [InlineKeyboardButton("❌ Reject Replies", callback_data=f"reject_replies_order_{request_id}")]
                ])

                await notify_admin(user_id, admin_approval_message, reply_markup=approval_keyboard)

                await update.message.reply_text(
                    f"✅ Your replies order request for *{num_replies} replies on {escape_markdown_v2(final_day_of_week)}* " # Escape
                    "has been submitted and is awaiting admin approval\\. We will notify you once it's processed\\."
                    , parse_mode=ParseMode.MARKDOWN_V2
                )

                keyboard = [
                    [InlineKeyboardButton("Back to Panel", callback_data="reply_guys_panel")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await update.message.reply_text("Navigate back to your panel:", reply_markup=reply_markup)
                return

            except ValueError:
                await update.message.reply_text(
                    "❌ Invalid format for replies order\\. Please enter the number of replies and the day of the week "
                    "\(e\\.g\\., `5 Monday`\)\\. The number must be a whole number\\."
                    , parse_mode=ParseMode.MARKDOWN_V2 # Ensure consistent parse_mode
                )
                return
            except Exception as e:
                logger.exception(f"An unexpected error occurred in handle_replies_order_request: {e}")
                await update.message.reply_text(
                    "An unexpected error occurred\\. Please try again later or contact support\\."
                    , parse_mode=ParseMode.MARKDOWN_V2
                )
                return

        

    # --- Fallback: Not recognized, show main menu in private chat ---
    if chat_type == "private":
        await clear_bot_messages(update, context)
        id, username, referrer, affiliate_balance, is_admin = get_user(user_id)
        await update.message.reply_text(
            "❓ I didn’t understand that\. Use the menu buttons to navigate\.",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(main_menu_keyboard(is_admin)) # Show main menu
        )
    else:
        # For group chats, perhaps just log and ignore or send a subtle message
        logger.info(f"Unhandled message in group chat '{chat_type}' from user {user_id}: '{text}'")
        # You might choose to send a silent message or no message at all in groups to avoid spam.
        # await update.message.reply_text("I only respond to commands in group chats.")