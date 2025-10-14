# handlers/payment_handler.py

import re
import uuid
import asyncio
import logging, time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple

import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes # Corrected from CallbackContext for modern PTB

from utils.config import APIConfig
from utils.admin_utils import send_message_to_admin
from utils.payment_utils import (
    get_deposit_address,
    convert_usd_to_crypto,
    poll_bank_payment_status,
    convert_crypto_to_usd,
    initiate_bank_transfer,
    get_usd_to_ngn_rate
)
from utils.db_utils import (
    get_referrer,
    update_affiliate_balance,
    save_purchase,
    is_transaction_hash_processed,
    mark_transaction_hash_as_processed,
    get_user_x_username, 
)
from utils.menu_utils import clear_bot_messages # Added escape_markdown_v2_v2 for MarkdownV2
from utils.messaging import escape_markdown_v2 # Added for MarkdownV2 escaping

logger = logging.getLogger(__name__)

class PaymentHandler:
    """
    Handles crypto & bank payments, on-chain verifications, and affiliate bonuses.
    """
    # --- Configuration Constants ---
    TX_HASH_TIMEOUT = 20 * 60  # 20 minutes for crypto hash submission
    BANK_POLL_INTERVAL = 10    # seconds
    BANK_POLL_TIMEOUT  = 4 * 60  # 4 minutes

    # --- Constructor ---
    def __init__(self):
        self.session = requests.Session()
        # API keys are best accessed directly from APIConfig
        # or passed if the handler is initialized per-request context (less common for singletons)

    def _log_verification_attempt(
        self,
        tx_hash: str,
        expected_address: str,
        expected_amount_usd: float,
        crypto_type: str,
        expected_token: Optional[str],
        correlation_id: Optional[str] = None
    ) -> None:
        """Log structured verification attempt details."""
        logger.info(
            "Payment verification attempt",
            extra={
                "correlation_id": correlation_id or f"verify_{tx_hash[:8]}",
                "tx_hash": tx_hash,
                "expected_address": expected_address,
                "expected_amount_usd": expected_amount_usd,
                "crypto_type": crypto_type,
                "expected_token": expected_token,
                "timestamp": datetime.utcnow().isoformat()
            }
        )

    def _log_verification_result(
        self,
        tx_hash: str,
        status: str,
        received_amount: Optional[float] = None,
        received_amount_usd: Optional[float] = None,
        from_address: Optional[str] = None,
        to_address: Optional[str] = None,
        confirmations: Optional[int] = None,
        message: Optional[str] = None,
        correlation_id: Optional[str] = None
    ) -> None:
        """Log structured verification result."""
        logger.info(
            f"Payment verification result: {status}",
            extra={
                "correlation_id": correlation_id or f"verify_{tx_hash[:8]}",
                "tx_hash": tx_hash,
                "status": status,
                "received_amount": received_amount,
                "received_amount_usd": received_amount_usd,
                "from_address": from_address,
                "to_address": to_address,
                "confirmations": confirmations,
                "message": message,
                "timestamp": datetime.utcnow().isoformat()
            }
        )

    # --- Public Payment Initiation Methods ---

    async def initiate_crypto_payment_flow(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE, # Use ContextTypes.DEFAULT_TYPE
        crypto_type: str,
        callback_query: Optional[Any] = None # Can be Update.callback_query or None
    ) -> None:
        """
        Initiates the crypto payment flow by presenting an address and
        setting up a transaction hash awaiting state with a timeout.
        """
        user_id = update.effective_user.id
        total_cost_usd = context.user_data.get("total_cost", 0.0)
        ct_lower = crypto_type.lower()

        # Input validation
        if total_cost_usd <= 0:
            await self._reply_or_edit_message(update, callback_query, "❌ Payment amount is invalid.")
            return

        # Map USDT networks to base crypto and token symbol for display/lookup
        usdt_networks = {
            "usdt_bep20": {"base_crypto": "bnb", "token_symbol": "USDT", "decimals": 18}, # Common for native BNB, but USDT-BEP20 is typically 18 or 6. Confirm this.
            "usdt_trc20": {"base_crypto": "trx", "token_symbol": "USDT", "decimals": 6},
            "usdt_sol":   {"base_crypto": "sol", "token_symbol": "USDT", "decimals": 6},
            "usdt_aptos": {"base_crypto": "aptos", "token_symbol": "USDT", "decimals": 6}
        }

        display_name: str
        crypto_symbol: str
        expected_token_symbol: Optional[str] = None
        crypto_amount: float
        token_decimals: int = 18 # Default for native ETH/BSC/etc. Adjust per token.

        if ct_lower.startswith("usdt_"):
            network_info = usdt_networks.get(ct_lower)
            if not network_info:
                await self._reply_or_edit_message(update, callback_query, "❌ Invalid USDT network selected\.")
                return
            
            base_crypto = network_info["base_crypto"]
            expected_token_symbol = network_info["token_symbol"]
            token_decimals = network_info["decimals"] # Use specific token decimals if provided

            display_name = f"*USDT* on *{base_crypto.upper()}*"
            crypto_symbol = "USDT" # Display symbol
            crypto_amount = total_cost_usd # USDT amount is directly total_cost_usd
            addy = get_deposit_address(base_crypto) # Get address for the base crypto's network
        else:
            # Native crypto (BTC, ETH, etc.)
            base_crypto = ct_lower
            display_name = f"*{base_crypto.upper()}* Payment"
            crypto_symbol = base_crypto.upper()
            expected_token_symbol = None # No specific token expected for native crypto
            
            # Convert USD to native crypto amount
            coin_id = APIConfig.COINGECKO_IDS.get(base_crypto)
            if not coin_id:
                await self._reply_or_edit_message(update, callback_query, f"❌ Configuration error for {base_crypto.upper()}\.")
                return

            crypto_amount = convert_usd_to_crypto(total_cost_usd, coin_id)
            if crypto_amount is None:
                await self._reply_or_edit_message(update, callback_query, "❌ Failed to calculate crypto amount\. Try again later\.")
                return
            
            addy = get_deposit_address(base_crypto) # Get address for native crypto

        if not addy:
            await self._reply_or_edit_message(update, callback_query, "❌ Failed to get deposit address\. Please try again later\.")
            return

        invoice_id = self.generate_invoice_id(user_id) # Generate unique invoice ID
        context.user_data["current_invoice_id"] = invoice_id
        
        payment_instructions_message = (
            f"{display_name} \n\n"
            f"Send `{escape_markdown_v2(f'{crypto_amount:.6f}')}` {escape_markdown_v2(crypto_symbol)} to:\n"
            f"`{escape_markdown_v2(addy)}`\n\n"
            f"Network: *{escape_markdown_v2(base_crypto.upper())}*\n" # Clearly state the network
            f"Your order ID: `{escape_markdown_v2(invoice_id)}`\n\n"
            f"After sending, please reply with your transaction hash to confirm payment\.\n" # Escaped '.'
            f"_This payment window expires in {self.TX_HASH_TIMEOUT//60} minutes\._" # Escaped '.'
        )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Main Menu", callback_data="main_menu")]
        ])

        # Clear any old messages from the bot
        await clear_bot_messages(update, context)

        # Send the payment prompt
        target_message = callback_query.message if callback_query else update.message
        if target_message:
            msg = await target_message.reply_text(
                payment_instructions_message, parse_mode="MarkdownV2", reply_markup=keyboard
            )
        else:
            # Fallback if no message context (shouldn't happen with typical callback queries/commands)
            msg = await update.effective_chat.send_message(
                payment_instructions_message, parse_mode="MarkdownV2", reply_markup=keyboard
            )

        # Save awaiting state for transaction hash processing
        context.user_data["awaiting_transaction_hash"] = {
            "invoice_id": invoice_id,
            "crypto_type": base_crypto, # e.g., 'bnb', 'trx', 'sol', 'aptos'
            "expected_token": expected_token_symbol, # e.g., 'USDT' or None
            "expected_amount_usd": total_cost_usd, # Original USD cost
            "expected_crypto_amount": crypto_amount, # Expected amount in crypto
            "deposit_address": addy,
            "token_decimals": token_decimals # Pass decimals for accurate checking
        }

        # Schedule timeout for the transaction hash
        if "transaction_timeout_task" in context.user_data and context.user_data["transaction_timeout_task"].done():
             # If a previous task exists and is done, don't cancel, just overwrite or let it finish
             pass
        elif "transaction_timeout_task" in context.user_data:
             context.user_data["transaction_timeout_task"].cancel() # Cancel any existing task
             logger.info("Cancelled previous crypto payment timeout task.")

        context.user_data["transaction_timeout_task"] = asyncio.create_task(
            self._crypto_payment_timeout_handler(update, msg, context, user_id)
        )
        logger.info(f"Crypto payment flow initiated for user {user_id} for ${total_cost_usd:.2f} in {crypto_type}\.")


    async def initiate_bank_payment_flow(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE, # Use ContextTypes.DEFAULT_TYPE
        currency: str,
        callback_query: Optional[Any] = None
    ) -> None:
        """
        Initiates a bank transfer flow, displays instructions, and starts polling for payment.
        """
        user_id = update.effective_user.id
        total_cost_usd = context.user_data.get("total_cost", 0.0)
        currency_upper = currency.upper()

        if total_cost_usd <= 0:
            await self._reply_or_edit_message(update, callback_query, "❌ Payment amount is invalid.")
            return

        amount_to_transfer_ngn = total_cost_usd # Start with USD, convert if needed

        # Convert USD to NGN if the target currency is NGN
        if currency_upper == "NGN":
            usd_to_ngn_rate = get_usd_to_ngn_rate()
            if usd_to_ngn_rate is None:
                await self._reply_or_edit_message(update, callback_query, "❌ Failed to fetch NGN exchange rate.")
                return
            # Add a small buffer/fee for NGN transfers if desired, e.g., 100 NGN
            amount_to_transfer_ngn = total_cost_usd * (usd_to_ngn_rate + 100) # Example fixed fee
            logger.info(f"Converted ${total_cost_usd:.2f} USD to NGN: ₦{amount_to_transfer_ngn:,.2f} (Rate: {usd_to_ngn_rate})")
        else:
            # If not NGN, we assume total_cost_usd is already in the target currency or use as is
            # This part needs careful design if you support other fiat currencies directly for bank transfer.
            # For simplicity, this example assumes NGN is the primary bank transfer currency.
            await self._reply_or_edit_message(update, callback_query, "❌ Only NGN bank transfers are supported at the moment\.")
            return

        # Initiate the bank transfer to get account details
        transfer_details = initiate_bank_transfer(
            amount=amount_to_transfer_ngn,
            currency=currency_upper
        )

        if not transfer_details:
            await self._reply_or_edit_message(update, callback_query, "❌ Failed to generate bank details\. Please try again later\.")
            return

        tx_ref = transfer_details.get("tx_ref")
        account_number = transfer_details.get("transfer_account")
        bank_name = transfer_details.get("transfer_bank")
        transfer_amount_display = transfer_details.get("transfer_amount") # This is amount in NGN
        transfer_note = transfer_details.get("transfer_note")
        integer_amount = int(float(transfer_amount_display))
        # Assuming 'expires_at' is a string or can be formatted into one
        expires_str = transfer_details.get("account_expiration") # Ensure this is a string
        payment_note = transfer_note # This note was problematic in your traceback


        bank_instructions_message = (
            f"🏦 *BANK TRANSFER*\n\n"
            f"Please transfer *₦{escape_markdown_v2(f'{float(transfer_amount_display)}')}* to the following account:\n\n"
            f"Bank: `{escape_markdown_v2(bank_name)}`\n" # Escape bank name
            f"Account Number: `{escape_markdown_v2(account_number)}`\n" # Escape account number
            f"Expires: `{escape_markdown_v2(expires_str)}`\n\n" # Escape expires string
            f"Please send the *exact amount*\\.\n\n" # The period here needs manual escape (or ensure escape_markdown_v2 handles it)
            f"Note: `{escape_markdown_v2(payment_note)}`\n\n" # Escape the payment note
            f"You will be notified once payment is confirmed\\." # The period here needs manual escape
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Main Menu", callback_data="main_menu")]
        ])

        await clear_bot_messages(update, context) # Clear any old messages

        # Send the payment instructions
        await self._reply_or_edit_message(update, callback_query, bank_instructions_message, keyboard)

        # Start background polling for payment confirmation
        if "bank_poll_task" in context.user_data and context.user_data["bank_poll_task"].done():
            pass # No need to cancel if already done
        elif "bank_poll_task" in context.user_data:
            context.user_data["bank_poll_task"].cancel() # Cancel any existing polling task
            logger.info("Cancelled previous bank payment polling task.")

        context.user_data["bank_poll_task"] = asyncio.create_task(
            poll_bank_payment_status(
                tx_ref=tx_ref,
                update=update,
                context=context, # Pass context for access to user_data, bot_data, etc.
                total_cost_usd=total_cost_usd, # Original USD cost
                user_id=user_id,
                username=update.effective_user.username,
                # Pass a Message object for replies, or just chat_id/bot_instance
                # For simplicity here, poll_bank_payment_status will rely on context for replies
                query_message=callback_query.message if callback_query else update.message # Original message to potentially edit
            )
        )
        logger.info(f"Bank payment flow initiated for user {user_id} for ₦{amount_to_transfer_ngn:,.2f} (USD: ${total_cost_usd:.2f}).")


    async def handle_transaction_hash_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Processes a received crypto transaction hash from the user.
        This function should be mapped to a MessageHandler with filters.TEXT & filters.ChatType.PRIVATE.
        """
        user_id = update.effective_user.id
        tx_hash = update.message.text.strip()

        # Check if an awaiting state exists
        awaiting_data = context.user_data.get("awaiting_transaction_hash")
        if not awaiting_data:
            await update.message.reply_text("❌ No crypto payment is currently in progress for you.")
            return

        # Cancel the timeout task immediately as we've received a hash
        if "transaction_timeout_task" in context.user_data:
            context.user_data["transaction_timeout_task"].cancel()
            context.user_data.pop("transaction_timeout_task", None)
            logger.info(f"Cancelled crypto payment timeout task for user {user_id} due to hash submission.")

        # Basic validation for the hash format
        crypto_type = awaiting_data["crypto_type"]
        if not self._validate_tx_hash_format(tx_hash, crypto_type):
            attempts = context.user_data.get("tx_attempts", 0) + 1
            context.user_data["tx_attempts"] = attempts
            if attempts < 3:
                await update.message.reply_text(
                    f"❌ Invalid {escape_markdown_v2(crypto_type.upper())} transaction hash format\. "
                    f"Please double-check and resend\. Attempts left: `{3-attempts}`\.",
                    parse_mode='MarkdownV2'
                )
                return
            else:
                await update.message.reply_text("❌ Too many invalid attempts. Crypto payment cancelled.")
                context.user_data.pop("awaiting_transaction_hash", None)
                context.user_data.pop("tx_attempts", None)
                return

        # Check if hash was already processed (DB lookup)
        if is_transaction_hash_processed(tx_hash):
            await update.message.reply_text("❌ This transaction hash has already been used.")
            context.user_data.pop("awaiting_transaction_hash", None) # Clear state
            return

        # Clear awaiting state as processing begins
        context.user_data.pop("awaiting_transaction_hash", None)
        context.user_data.pop("tx_attempts", None)

        await update.message.reply_text("⏳ Verifying your transaction on the blockchain... This may take a moment.")

        # Verify on-chain and process payment
        verification_result = self._check_transaction_on_chain(
            tx_hash=tx_hash,
            expected_address=awaiting_data["deposit_address"],
            expected_amount_usd=awaiting_data["expected_amount_usd"],
            crypto_type=awaiting_data["crypto_type"],
            expected_token_symbol=awaiting_data["expected_token"],
            token_decimals=awaiting_data["token_decimals"]
        )

        if verification_result.get("status") == "success":
            transaction_data = verification_result["transaction"]
            received_amount_crypto = transaction_data["value"] # Amount in crypto units (e.g., SOL, BNB, USDT)

            # Convert received crypto amount to USD for internal logic consistency
            # If expected_token_symbol is USDT, received_amount_crypto is already USD equivalent.
            # Otherwise, convert native crypto to USD.
            if awaiting_data["expected_token"] == "USDT":
                received_amount_usd = received_amount_crypto # Already USD equivalent
            else:
                received_amount_usd = convert_crypto_to_usd(
                    received_amount_crypto,
                    APIConfig.COINGECKO_IDS.get(awaiting_data["crypto_type"]) # Get CoinGecko ID
                )
            
            if received_amount_usd is None:
                logger.error(f"Failed to convert received crypto amount {received_amount_crypto} {awaiting_data['crypto_type'].upper()} to USD.")
                await update.message.reply_text("❌ Failed to process payment: Could not determine USD value. Please contact support.")
                return

            await self._verify_and_process_payment(
                update=update,
                context=context,
                payment_type="crypto",
                transaction_hash=tx_hash,
                received_amount_usd=received_amount_usd,
                invoice_id=awaiting_data["invoice_id"] # Pass invoice_id from awaiting_data
            )
        else:
            error_msg = verification_result.get("message", "Unknown verification error.")
            await update.message.reply_text(f"❌ Crypto payment verification failed: {escape_markdown_v2(error_msg)}\n"
                                             "Please ensure you sent the correct amount to the correct address, "
                                             "and replied with the correct hash\.", parse_mode='MarkdownV2')
            logger.warning(f"Crypto verification failed for user {user_id}, hash {tx_hash}: {error_msg}")


    # --- Internal Helpers ---

    async def _reply_or_edit_message(self, update: Update, callback_query: Optional[Any], text: str, reply_markup: Optional[InlineKeyboardMarkup] = None) -> None:
        """Helper to reply to message or edit callback query message."""
        if callback_query:
            try:
                await callback_query.message.edit_text(text, reply_markup=reply_markup, parse_mode='MarkdownV2')
            except Exception as e:
                logger.warning(f"Failed to edit message via callback_query: {e}. Attempting reply.")
                await update.effective_chat.send_message(text, reply_markup=reply_markup, parse_mode='MarkdownV2')
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='MarkdownV2')

    async def _crypto_payment_timeout_handler(self, update: Update, msg: Any, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
        """Handler for crypto transaction hash submission timeout."""
        await asyncio.sleep(self.TX_HASH_TIMEOUT)
        if context.user_data.get("awaiting_transaction_hash"):
            context.user_data.pop("awaiting_transaction_hash", None)
            context.user_data.pop("tx_attempts", None)
            try:
                await msg.edit_text("⏰ Payment window expired\. Please try again\.", reply_markup=None, parse_mode='MarkdownV2')
                logger.info(f"Crypto payment window expired for user {user_id}\.")
            except Exception as e:
                logger.warning(f"Failed to edit timeout message for user {user_id}: {e}")
                # Fallback to sending a new message if editing failed
                try:
                    await update.effective_chat.send_message("⏰ Payment window expired\\. Please try again\\.", parse_mode='MarkdownV2')
                except Exception as e:
                    logger.error(f"Failed to send new timeout message for user {user_id}: {e}")


    def generate_invoice_id(self, user_id: int) -> str:
        """Generates a unique invoice ID."""
        return f"INV-{user_id}-{uuid.uuid4().hex[:8].upper()}"

    def _normalize_address(self, address: str, crypto_type: str) -> str:
        """
        Normalize blockchain address for comparison.
        For EVM chains (BSC, Ethereum), convert to lowercase for case-insensitive comparison.
        For other chains, return as-is.
        """
        if crypto_type in ["bnb", "bsc", "eth", "aptos"]:
            # EVM-style addresses - use lowercase for comparison
            return address.lower().strip()
        elif crypto_type == "sol":
            # Solana addresses are case-sensitive, return as-is
            return address.strip()
        elif crypto_type == "trx":
            # Tron addresses are case-sensitive, return as-is
            return address.strip()
        else:
            return address.lower().strip()

    def _validate_tx_hash_format(self, tx_hash: str, crypto_type: str) -> bool:
        """Performs basic regex validation for transaction hash format."""
        h = tx_hash.strip()
        if crypto_type == "bnb" or crypto_type == "aptos":
            return bool(re.fullmatch(r"0x[0-9A-Fa-f]{64}", h))
        if crypto_type == "trx":
            return bool(re.fullmatch(r"[0-9A-Fa-f]{64}", h))
        if crypto_type == "sol":
            # Solana hashes are base58 encoded, length varies.
            # Typical transaction signatures are 88 chars. Public keys are 44.
            # A broad range for now.
            return 43 <= len(h) <= 90 and re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]{43,90}", h)
        return False

    def _check_transaction_on_chain(
        self,
        tx_hash: str,
        expected_address: str,
        expected_amount_usd: float,
        crypto_type: str,
        expected_token_symbol: Optional[str],
        token_decimals: int
    ) -> Dict[str, Any]:
        """
        Dispatches to network-specific verification methods (BSC, Solana, Tron, Aptos).
        Adds common logic for amount and age validation.
        """
        # Generate correlation ID for tracing
        correlation_id = f"verify_{tx_hash[:8]}_{uuid.uuid4().hex[:6]}"
        
        # Log verification attempt with structured data
        self._log_verification_attempt(
            tx_hash=tx_hash,
            expected_address=expected_address,
            expected_amount_usd=expected_amount_usd,
            crypto_type=crypto_type,
            expected_token=expected_token_symbol,
            correlation_id=correlation_id
        )
        
        now_unix_timestamp = int(datetime.now(timezone.utc).timestamp())
        max_tx_age_minutes = self.TX_HASH_TIMEOUT // 60 # Use the class-wide timeout for relevance

        try:
            if crypto_type == "bnb":
                result = self._check_bsc(tx_hash, expected_address, expected_amount_usd, now_unix_timestamp, max_tx_age_minutes, expected_token_symbol, token_decimals)
            elif crypto_type == "sol":
                result = self._check_solana(tx_hash, expected_address, expected_amount_usd, now_unix_timestamp, max_tx_age_minutes, expected_token_symbol)
            elif crypto_type == "trx":
                result = self._check_tron(tx_hash, expected_address, expected_amount_usd, now_unix_timestamp, max_tx_age_minutes, expected_token_symbol)
            elif crypto_type == "aptos":
                result = self._check_aptos(tx_hash, expected_address, expected_amount_usd, now_unix_timestamp, max_tx_age_minutes, expected_token_symbol)
            else:
                result = {"status": "error", "message": "Unsupported blockchain for verification."}
            
            # Log verification result
            tx_data = result.get("transaction", {})
            self._log_verification_result(
                tx_hash=tx_hash,
                status=result.get("status", "unknown"),
                received_amount=tx_data.get("value"),
                received_amount_usd=tx_data.get("value_usd"),
                from_address=tx_data.get("from"),
                to_address=tx_data.get("to"),
                confirmations=tx_data.get("confirmations"),
                message=result.get("message"),
                correlation_id=correlation_id
            )
            
            return result
        except Exception as e:
            logger.error(f"Blockchain verification error for {crypto_type} (hash: {tx_hash}): {e}", exc_info=True, extra={"correlation_id": correlation_id})
            return {"status": "error", "message": f"An internal error occurred during verification: {str(e)}"}

    # --- Private Blockchain Verification Methods (Keep as is, but ensure `APIConfig` usage) ---
    # These are mostly provided by the user, so ensuring they use APIConfig.XYZ_API_KEY
    # and handle exceptions gracefully.

    
    def _check_bsc(self, tx_hash: str, wallet: str, expected_amount_usd: float, now: int, max_age: int, expected_token: Optional[str], token_decimals: int = 18) -> Dict[str, Any]:
        """Check transaction on Binance Smart Chain (BSC)."""
        url = "https://api.etherscan.io/v2/api?chainid=56"
        
        # Normalize wallet address for comparison
        wallet_normalized = self._normalize_address(wallet, "bnb")
        tx_hash_normalized = tx_hash.lower().strip()
        
        # For USDT BEP20, action is 'tokentx' and address is the wallet itself (looking for incoming token transfers)
        # For native BNB, action is 'txlist'
        if expected_token == "USDT":
            params = {
                "module": "account",
                "action": "tokentx",
                "address": wallet,
                "page": 1,
                "offset": 10, # Check recent transactions
                "sort": "desc",
                "apikey": APIConfig.BSC_API_KEY # Use APIConfig
            }
        else: # Native BNB
            params = {
                "module": "account",
                "action": "txlist",
                "address": wallet,
                "page": 1,
                "offset": 10,
                "sort": "desc",
                "apikey": APIConfig.BSC_API_KEY # Use APIConfig
            }

        max_retries = 3
        delay_seconds = 15 # Delay between retries

        for attempt in range(max_retries):
            logger.debug(f"Attempt {attempt + 1}/{max_retries} to check BSC transaction for hash: {tx_hash}")
            try:
                response = self.session.get(url, params=params, timeout=15) # Increased timeout slightly
                response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
                data = response.json()

                if data.get("status") == "1":
                    transactions = data.get("result", [])
                    logger.info(f"Received {len(transactions)} transactions from BSCScan for wallet {wallet}")

                    # Flag to know if a matching transaction was found in this attempt
                    found_matching_tx = False
                    for tx in transactions:
                        # Filter for incoming transactions to our wallet
                        current_tx_hash = tx.get("hash", "").lower().strip()
                        current_tx_to_address = self._normalize_address(tx.get("to", ""), "bnb")

                        logger.debug(f"Comparing: {current_tx_hash} == {tx_hash_normalized} and {current_tx_to_address} == {wallet_normalized}")

                        if current_tx_hash == tx_hash_normalized and current_tx_to_address == wallet_normalized:
                            found_matching_tx = True
                            # For token transfers, ensure it's the expected token
                            # USDT on BSC can be "USDT", "BSC-USD", or other variations depending on the token contract
                            if expected_token == "USDT":
                                token_symbol = tx.get("tokenSymbol", "").upper()
                                # Accept common USDT symbols on BSC
                                if token_symbol not in ["USDT", "BSC-USD", "USD"]:
                                    logger.warning(f"Found transaction with matching hash but unexpected token symbol: {token_symbol} (expected USDT variants)")
                                    continue # Skip if not USDT, continue looking for others in the list

                            # Value is typically in smallest unit (e.g., wei for ETH/BNB, or 10^decimals for tokens)
                            tx_value_raw = int(tx.get("value", 0))
                            # Use the correct `token_decimals` for conversion
                            value_converted_crypto = tx_value_raw / (10 ** token_decimals)

                            # Time check
                            tx_timestamp_unix = int(tx.get("timeStamp", 0))
                            if (now - tx_timestamp_unix) // 60 > max_age:
                                return {"status": "expired", "message": "Transaction is too old."}

                            # Amount check (convert received crypto value to USD if needed)
                            # For USDT, value_converted_crypto is already USD equivalent.
                            if expected_token == "USDT":
                                received_amount_usd = value_converted_crypto
                            else:
                                # Convert native BNB amount to USD
                                received_amount_usd = convert_crypto_to_usd(value_converted_crypto, APIConfig.COINGECKO_IDS["bnb"])
                                if received_amount_usd is None:
                                    return {"status": "error", "message": "Could not get current BNB price."}

                            # Allow for slight variations (e.g., network fees affecting final received amount)
                            # We use 0.5 USD tolerance for both min and max around the expected USD amount
                            tolerance = 0.5
                            if not (expected_amount_usd - tolerance <= received_amount_usd <= expected_amount_usd + tolerance):
                                return {"status": "failed_amount", "message": f"Received amount ${received_amount_usd:.2f} USD does not match expected range (${expected_amount_usd-tolerance:.2f}-${expected_amount_usd+tolerance:.2f} USD)."}

                            logger.info(f"Transaction {tx_hash} successfully found and verified.")
                            return {
                                "status": "success",
                                "transaction": {
                                    "from": tx.get("from"),
                                    "to": tx.get("to"),
                                    "value": value_converted_crypto, # The amount in crypto units
                                    "value_usd": received_amount_usd, # The amount in USD equivalent
                                    "hash": tx.get("hash"),
                                    "timestamp": tx.get("timeStamp"),
                                    "tokenSymbol": tx.get("tokenSymbol", expected_token),
                                    "tokenName": tx.get("tokenName", "")
                                }
                            }
                    # If loop finishes and no matching transaction was found in this attempt
                    if not found_matching_tx and attempt < max_retries - 1:
                        logger.info(f"Transaction {tx_hash} not found on attempt {attempt + 1}. Retrying in {delay_seconds} seconds...")
                        time.sleep(delay_seconds)
                        continue # Go to the next attempt
                    elif not found_matching_tx and attempt == max_retries - 1:
                        logger.warning(f"Transaction {tx_hash} not found after {max_retries} attempts.")
                        return {"status": "not_found", "message": "No matching incoming transaction found on BSCScan after multiple attempts."}
                else: # API status is not "1"
                    if attempt < max_retries - 1:
                        logger.warning(f"BSCScan API returned status {data.get('status')} and message: {data.get('message')}. Retrying in {delay_seconds} seconds...")
                        time.sleep(delay_seconds)
                        continue
                    else:
                        logger.error(f"BSCScan API returned status {data.get('status')} and message: {data.get('message')} after {max_retries} attempts.")
                        return {"status": "error", "message": data.get("message", "Failed to fetch BSCScan data after multiple attempts.")}

            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    logger.warning(f"BSCScan API request failed on attempt {attempt + 1}: {e}. Retrying in {delay_seconds} seconds...")
                    time.sleep(delay_seconds)
                    continue
                else:
                    logger.error(f"BSCScan API request failed after {max_retries} attempts: {e}")
                    return {"status": "api_error", "message": f"Network error contacting BSCScan after multiple attempts: {str(e)}"}
            except Exception as e:
                logger.error(f"Error processing BSC transaction: {e}", exc_info=True)
                # For general unexpected errors, we might not want to retry as it might be a code issue
                return {"status": "internal_error", "message": f"Internal error during BSC verification: {str(e)}"}

        # This part should theoretically not be reached if all returns are handled within the loop,
        # but it's a fallback if all retries fail without a specific return.
        return {"status": "not_found", "message": "No matching incoming transaction found on BSCScan after all retries."}

    def _check_solana(self, tx_hash: str, wallet: str, expected_amount_usd: float, now: int, max_age: int, expected_token: Optional[str]) -> Dict[str, Any]:
        """Check transaction on Solana blockchain."""
        headers = {"accept": "application/json"}
        sol_url = f"https://api.solana.fm/v0/transfers/{tx_hash}"
        
        # Normalize wallet address for comparison (Solana addresses are case-sensitive but we trim whitespace)
        wallet_normalized = self._normalize_address(wallet, "sol")
        
        try:
            response = self.session.get(sol_url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()

            if response.status_code == 200 and data.get("status") == "success" and "result" in data and "data" in data["result"]:
                transactions = data["result"]["data"]

                for tx in transactions:
                    # Filter for incoming transfers to our wallet (normalize for comparison)
                    tx_destination = self._normalize_address(tx.get("destination", ""), "sol")
                    if tx_destination != wallet_normalized:
                        continue
                    
                    # For SOL, 'transfer' action for native SOL. For USDT, 'transferChecked'
                    if expected_token == "USDT":
                        if not (tx.get("action") == "transferChecked" and tx.get("tokenSymbol") == "USDT"):
                            continue
                        value_raw = int(tx.get("amount", 0)) # USDT on Solana has 6 decimals
                        value_converted_crypto = value_raw / (10 ** 6)
                    else: # Native SOL
                        if tx.get("action") != "transfer":
                            continue
                        value_raw = int(tx.get("amount", 0)) # SOL has 9 decimals
                        value_converted_crypto = value_raw / (10 ** 9)

                    # Time check
                    tx_timestamp_unix = int(tx.get("timestamp", 0)) # Already Unix seconds
                    if (now - tx_timestamp_unix) // 60 > max_age:
                        return {"status": "expired", "message": "Transaction is too old."}
                    
                    # Amount check (convert received crypto value to USD if needed)
                    if expected_token == "USDT":
                        received_amount_usd = value_converted_crypto # Already USD equivalent
                    else:
                        received_amount_usd = convert_crypto_to_usd(value_converted_crypto, APIConfig.COINGECKO_IDS["sol"])
                        if received_amount_usd is None:
                            return {"status": "error", "message": "Could not get current SOL price."}

                    tolerance = 0.5
                    if not (expected_amount_usd - tolerance <= received_amount_usd <= expected_amount_usd + tolerance):
                        return {"status": "failed_amount", "message": f"Received amount ${received_amount_usd:.2f} USD does not match expected range (${expected_amount_usd-tolerance:.2f}-${expected_amount_usd+tolerance:.2f} USD)."}

                    return {
                        "status": "success",
                        "transaction": {
                            "from": tx.get("source", ""),
                            "to": tx.get("destination", ""),
                            "value": value_converted_crypto, # The amount in crypto units
                            "value_usd": received_amount_usd, # The amount in USD equivalent
                            "hash": tx_hash,
                            "timestamp": tx.get("timestamp"),
                            "tokenSymbol": tx.get("tokenSymbol", expected_token if expected_token else "SOL"),
                        }
                    }
                return {"status": "not_found", "message": "No matching incoming transaction found on Solana.fm."}
            else:
                return {"status": "error", "message": data.get("message", "Failed to fetch Solana.fm data.")}
        except requests.exceptions.RequestException as e:
            logger.error(f"Solana.fm API request failed: {e}")
            return {"status": "api_error", "message": f"Network error contacting Solana.fm: {str(e)}"}
        except Exception as e:
            logger.error(f"Error processing Solana transaction: {e}", exc_info=True)
            return {"status": "internal_error", "message": f"Internal error during Solana verification: {str(e)}"}


    def _check_tron(self, tx_hash: str, wallet: str, expected_amount_usd: float, now: int, max_age: int, expected_token: Optional[str]) -> Dict[str, Any]:
        # For TRC20 tokens, use /transactions/trc20 endpoint
        if expected_token == "USDT":
            trx_url = f"https://api.trongrid.io/v1/accounts/{wallet}/transactions/trc20"
        else: # Native TRX
            trx_url = f"https://api.trongrid.io/v1/accounts/{wallet}/transactions"
        
        params = {
            "only_to": "true", # Only incoming transactions
            "limit": 10, # Check recent transactions
            "order_by": "block_timestamp,desc" if expected_token else "timestamp,desc" # Adjust sorting
        }
        headers = {"Accept": "application/json"} # TronGrid requires Accept header for some endpoints

        try:
            response = self.session.get(trx_url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()

            if response.status_code == 200 and data.get("success"):
                transactions = data.get("data", [])

                for tx in transactions:
                    # Check transaction hash match
                    current_tx_id = tx.get("transaction_id") if expected_token == "USDT" else tx.get("txID")
                    if current_tx_id.lower() != tx_hash.lower():
                        continue

                    # Extract amount and timestamp
                    if expected_token == "USDT":
                        token_info = tx.get("token_info", {})
                        decimals = token_info.get("decimals", 6) # USDT on Tron is typically 6 decimals
                        value_raw = tx.get("value")
                        if value_raw is None: continue
                        value_converted_crypto = int(value_raw) / (10 ** decimals)
                        tx_timestamp_unix = int(tx.get("block_timestamp", 0)) // 1000 # Convert milliseconds to seconds
                        from_address = tx.get("from")
                        to_address = tx.get("to")
                    else: # Native TRX
                        raw_data = tx.get("raw_data", {})
                        contracts = raw_data.get("contract", [])
                        contract_found = False
                        for contract in contracts:
                            if contract.get("type") == "TransferContract":
                                amount_sun = contract.get("parameter", {}).get("value", {}).get("amount")
                                if amount_sun is None: continue
                                value_converted_crypto = amount_sun / (10 ** 6) # TRX has 6 decimals (SUN is smallest unit)
                                tx_timestamp_unix = int(raw_data.get("timestamp", 0)) // 1000 # Convert milliseconds to seconds
                                from_address = contract.get("parameter", {}).get("value", {}).get("owner_address")
                                to_address = contract.get("parameter", {}).get("value", {}).get("to_address")
                                contract_found = True
                                break
                        if not contract_found: continue # Skip if no transfer contract found

                    # Final check for incoming to correct wallet
                    if to_address.lower() != wallet.lower():
                        continue

                    # Time check
                    if (now - tx_timestamp_unix) // 60 > max_age:
                        return {"status": "expired", "message": "Transaction is too old."}

                    # Amount check (convert received crypto value to USD if needed)
                    if expected_token == "USDT":
                        received_amount_usd = value_converted_crypto # Already USD equivalent
                    else:
                        received_amount_usd = convert_crypto_to_usd(value_converted_crypto, APIConfig.COINGECKO_IDS["trx"])
                        if received_amount_usd is None:
                            return {"status": "error", "message": "Could not get current TRX price."}

                    tolerance = 0.5
                    if not (expected_amount_usd - tolerance <= received_amount_usd <= expected_amount_usd + tolerance):
                        return {"status": "failed_amount", "message": f"Received amount ${received_amount_usd:.2f} USD does not match expected range (${expected_amount_usd-tolerance:.2f}-${expected_amount_usd+tolerance:.2f} USD)."}

                    return {
                        "status": "success",
                        "transaction": {
                            "from": from_address,
                            "to": to_address,
                            "value": value_converted_crypto,
                            "value_usd": received_amount_usd,
                            "hash": current_tx_id,
                            "timestamp": tx_timestamp_unix,
                            "tokenSymbol": expected_token if expected_token else "TRX",
                        }
                    }
                return {"status": "not_found", "message": "No matching incoming transaction found on TronGrid."}
            else:
                return {"status": "error", "message": data.get("message", "Failed to fetch TronGrid data.")}
        except requests.exceptions.RequestException as e:
            logger.error(f"TronGrid API request failed: {e}")
            return {"status": "api_error", "message": f"Network error contacting TronGrid: {str(e)}"}
        except Exception as e:
            logger.error(f"Error processing Tron transaction: {e}", exc_info=True)
            return {"status": "internal_error", "message": f"Internal error during Tron verification: {str(e)}"}

    def _check_aptos(self, tx_hash: str, wallet: str, expected_amount_usd: float, now: int, max_age: int, expected_token: Optional[str]) -> Dict[str, Any]:
        headers = {"accept": "application/json"}
        aptos_url = f"https://fullnode.mainnet.aptoslabs.com/v1/transactions/by_hash/{tx_hash}"
        try:
            response = self.session.get(aptos_url, headers=headers, timeout=10)
            response.raise_for_status()
            tx = response.json()

            if not tx.get("success", False):
                return {"status": "failed_tx", "message": "Aptos transaction failed on-chain (execution_status not success)."}

            payload = tx.get("payload", {})
            payload_function = payload.get("function", "")
            args = payload.get("arguments", [])

            # Determine amount and token based on payload function
            value_converted_crypto: float = 0.0
            token_symbol: str = "UNKNOWN"
            
            # Common functions for transfers in Aptos
            if "coin::transfer" in payload_function:
                # For native APT or other generic coin transfers (might vary)
                if len(args) >= 2:
                    if args[0].lower() == wallet.lower(): # Destination address check
                        try:
                            # Assume APT is 8 decimals if not specified by token_type
                            value_converted_crypto = int(args[1]) / (10 ** 8)
                            token_symbol = "APT"
                        except ValueError:
                            pass
            elif "coin::transfer_with_payload" in payload_function or "token::transfer" in payload_function:
                # For specific token transfers like USDT (adjust based on actual contract)
                # This needs to be precise for how your USDT token works on Aptos
                # Example: `0x1::coin::transfer_with_payload<0x...::usdt::USDT>`
                # arguments might be [recipient_address, amount_raw]
                if expected_token == "USDT":
                    # This logic depends highly on the specific USDT contract function.
                    # Assuming arguments: [recipient_address, amount_raw]
                    # and USDT on Aptos is 6 decimals.
                    if len(args) >= 2 and args[0].lower() == wallet.lower():
                        try:
                            value_converted_crypto = int(args[1]) / (10 ** 6)
                            token_symbol = "USDT"
                        except ValueError:
                            pass
                else:
                    # Add logic for other custom tokens if applicable
                    pass
            
            if value_converted_crypto == 0:
                return {"status": "not_found", "message": "No matching incoming transaction found with expected amount/token details."}

            # Convert the timestamp from microseconds to seconds (Aptos timestamps are in microseconds)
            tx_timestamp_us = int(tx.get("timestamp", "0"))
            tx_timestamp_unix = tx_timestamp_us // 1_000_000 # Convert microseconds to seconds
            
            # Time check
            if (now - tx_timestamp_unix) // 60 > max_age:
                return {"status": "expired", "message": "Transaction is too old."}

            # Amount check (convert received crypto value to USD if needed)
            if token_symbol == "USDT":
                received_amount_usd = value_converted_crypto # Already USD equivalent
            else:
                # Convert native APT amount to USD
                received_amount_usd = convert_crypto_to_usd(value_converted_crypto, APIConfig.COINGECKO_IDS["aptos"])
                if received_amount_usd is None:
                    return {"status": "error", "message": "Could not get current APTOS price."}

            tolerance = 0.5
            if not (expected_amount_usd - tolerance <= received_amount_usd <= expected_amount_usd + tolerance):
                return {"status": "failed_amount", "message": f"Received amount ${received_amount_usd:.2f} USD does not match expected range (${expected_amount_usd-tolerance:.2f}-${expected_amount_usd+tolerance:.2f} USD)."}

            return {
                "status": "success",
                "transaction": {
                    "from": tx.get("sender"),
                    "to": wallet,
                    "value": value_converted_crypto,
                    "value_usd": received_amount_usd,
                    "hash": tx.get("hash"),
                    "timestamp": tx_timestamp_unix,
                    "tokenSymbol": token_symbol
                }
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Aptos API request failed: {e}")
            return {"status": "api_error", "message": f"Network error contacting Aptos node: {str(e)}"}
        except Exception as e:
            logger.error(f"Error processing Aptos transaction: {e}", exc_info=True)
            return {"status": "internal_error", "message": f"Internal error during Aptos verification: {str(e)}"}

    # --- Common Payment Processing (Success Path) ---

    alogger = logging.getLogger(__name__)

    async def _verify_and_process_payment(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        payment_type: str,  # "crypto" or "bank"
        received_amount_usd: float,
        invoice_id: str,
        transaction_hash: Optional[str] = None,  # Only for crypto payments
        current_plan_type: Optional[str] = None,
        ordered_quantity: Optional[int] = None
    ) -> None:
        """
        Handles the final steps of a successful payment:
        - Marking transaction as processed in DB
        - Saving purchase details
        - Applying affiliate bonus
        - Notifying user about next steps (e.g., awaiting X username, poll details, etc.)
        """
        user_id = update.effective_user.id
        user_username = update.effective_user.username if update.effective_user.username else str(user_id)

        # Ensure plan type and quantity are available.
        if not current_plan_type:
            current_plan_type = context.user_data.get("current_plan_type")

        if not ordered_quantity:
            # Determine ordered_quantity based on plan type if not provided directly
            if current_plan_type == "tg_custom":
                ordered_quantity = context.user_data.get("qty")
            elif current_plan_type in ["x_engagement", "x_poll", "direct_add", "slow_push"]:
                ordered_quantity = context.user_data.get("posts")
            else:
                ordered_quantity = None # Default if not found or applicable

        print(f"Processing payment for user {user_id} with type {payment_type}, amount ${received_amount_usd:.2f}, invoice {invoice_id}, hash {transaction_hash}, current_plan_type {current_plan_type}, ordered_quantity {ordered_quantity}")
        

        ordered_comments = 0
        if current_plan_type == "tg_custom":
            ordered_comments = context.user_data.get("tqty", 0)

        # Basic validation for plan_type and ordered_quantity
        if not current_plan_type or ordered_quantity is None:
            logger.error(f"Missing current_plan_type ({current_plan_type}) or ordered_quantity ({ordered_quantity}) for user {user_id} during payment processing.")
            await update.effective_chat.send_message("❌ Payment processed, but order details are unclear. Please contact support.")
            return

        # 1. Mark transaction as processed in DB
        if payment_type == "crypto" and transaction_hash:
            mark_transaction_hash_as_processed(transaction_hash, user_id)
            logger.info(f"Crypto transaction hash {transaction_hash} marked as processed for user {user_id}.")
        elif payment_type == "bank":
            logger.info(f"Bank payment for invoice {invoice_id} processed for user {user_id}.")

        # --- Process based on current_plan_type ---
        if current_plan_type == "tg_custom":
            tier = "tgt"
            context.user_data["awaiting_tg_username"] = True
            save_purchase(
                user_id=user_id,
                plan_type=tier,
                comments=ordered_comments,
                amount_paid_usd=received_amount_usd,
                payment_method=payment_type,
                quantity=ordered_quantity,
                transaction_ref=transaction_hash,
            )
            await update.effective_chat.send_message(
                "Thank you for your Telegram Engagement order\! Send the Telegram Username associated with this payment\.",
                parse_mode='MarkdownV2'
            )
        elif current_plan_type == "x_engagement":
            tier = context.user_data.get("tier", "x_custom_plan")
            print(f"Processing X Engagement for user {user_id} with tier {tier}, amount ${received_amount_usd:.2f}, invoice {invoice_id}, hash {transaction_hash}")
            context.user_data["awaiting_x_username"] = True
            save_purchase(
                user_id=user_id,
                plan_type=tier,
                comments=ordered_comments, # Will be 0 for X custom, but kept for function signature consistency
                amount_paid_usd=received_amount_usd,
                payment_method=payment_type,
                quantity=ordered_quantity,
                transaction_ref=transaction_hash,
            )
            await update.effective_chat.send_message(
                "Thank you for your X \(Twitter\) Engagement order\! Send the Twitter Username associated with this payment\.",
                parse_mode='MarkdownV2'
            )
        elif current_plan_type == "tg_automation":
            admin_message = (
                f" *NEW TELEGRAM AUTOMATION REQUEST!* \n\n"
                f"User ID: `{user_id}`\n"
                f"Username: @{user_username if user_username else 'N/A'}\n"
                f"Payment Confirmed: `${received_amount_usd:.2f}` via {'Crypto' if payment_type == 'crypto' else 'Bank Transfer'} (TxRef: `{transaction_hash if transaction_hash else 'N/A'}`)"
            )
            await send_message_to_admin(admin_message=admin_message, context=context)
            await update.effective_chat.send_message("✅ Your request for TELEGRAM AUTOMATION has been sent to the admin and is being processed.")
        elif current_plan_type == "tg_premium":
            await update.effective_chat.send_message("✅ Payment confirmed! Your Telegram premium request is being processed.")
            context.user_data["awaiting_tg_channel_username"] = True
        elif current_plan_type == "x_poll":
            save_purchase( # Assuming you want to save x_poll purchases
                user_id=user_id,
                plan_type="x_poll",
                comments=0,
                amount_paid_usd=received_amount_usd,
                payment_method=payment_type,
                quantity=ordered_quantity,
                transaction_ref=transaction_hash,
            )
            context.user_data["awaiting_x_poll_details"] = True
            await update.effective_chat.send_message(
                "Please send the X \(Twitter\) poll link and the option number "
                "you want to vote for, separated by a comma \(`https://x.com/status/1234567890/polls/abcdef, 1`\)",
                parse_mode='MarkdownV2'
            )
        elif current_plan_type == "direct_add":
            save_purchase( # Assuming you want to save direct_add purchases
                user_id=user_id,
                plan_type="direct_add",
                comments=0,
                amount_paid_usd=received_amount_usd,
                payment_method=payment_type,
                quantity=ordered_quantity,
                transaction_ref=transaction_hash,
            )
            context.user_data["awaiting_direct_add_link_input"] = True
            await update.effective_chat.send_message(
                "Please send the X \(Twitter\) profile link for your Direct Add Followers order \(e.g., `https://x.com/username`\)",
                parse_mode='MarkdownV2'
            )
        elif current_plan_type == "slow_push":
            save_purchase( # Assuming you want to save slow_push purchases
                user_id=user_id,
                plan_type="slow_push",
                comments=0,
                amount_paid_usd=received_amount_usd,
                payment_method=payment_type,
                quantity=ordered_quantity,
                transaction_ref=transaction_hash,
            )
            context.user_data["awaiting_slow_push_profile_link"] = True
            await update.effective_chat.send_message(
                "Please send the X \(Twitter\) profile link for your Slow Push Followers order \(e.g., `https://x.com/username`\)",
                parse_mode='MarkdownV2'
            )
        else:
            # Default fallback for any other service, if no specific instructions
            save_purchase( # Consider if all other types should be saved universally
                user_id=user_id,
                plan_type=current_plan_type,
                comments=ordered_comments,
                amount_paid_usd=received_amount_usd,
                payment_method=payment_type,
                quantity=ordered_quantity,
                transaction_ref=transaction_hash,
            )
            await update.effective_chat.send_message(
                "Your order has been placed and will be processed shortly\. Thank you\!",
                parse_mode='MarkdownV2'
            )

        logger.info(f"Purchase saved and/or notification sent for user {user_id}: Plan '{current_plan_type}' x {ordered_quantity} via {payment_type}. Invoice: {invoice_id}, Amount: ${received_amount_usd:.2f}.")

        # --- Affiliate bonus handling ---
        referrer_id = get_referrer(user_id)
        if referrer_id:
            referral_bonus = received_amount_usd * 0.10  # Using 10% directly
            update_affiliate_balance(referrer_id, referral_bonus)
            try:
                referrer_x_username = get_user_x_username(referrer_id) # Consider if this is always needed or can be optimized
                referrer_notification_text = (
                    f"💰 Great news! Your referral "
                    f"[{escape_markdown_v2(user_username)}](tg://user?id={user_id}) "
                    f"has made a payment of *${received_amount_usd:.2f}*.\n"
                    f"You earned a bonus of *${referral_bonus:.2f}*!"
                )
                await context.bot.send_message(
                    referrer_id,
                    referrer_notification_text,
                    parse_mode='MarkdownV2'
                )
                logger.info(f"Affiliate bonus ${referral_bonus:.2f} granted to referrer {referrer_id}.")
            except Exception as e:
                logger.error(f"Failed to notify referrer {referrer_id} about bonus: {e}", exc_info=True)

        # --- General payment confirmation to user ---
        await update.effective_chat.send_message(
            f"✅ Payment confirmed\! Your order `{escape_markdown_v2(invoice_id)}` has been processed for *${escape_markdown_v2(str(received_amount_usd))}*",
            parse_mode='MarkdownV2'
        )

        # --- Set flags for post-payment details and guide user ---
        context.user_data["ordered_quantity"] = ordered_quantity
        context.user_data["total_cost"] = received_amount_usd
        context.user_data["current_plan_type"] = current_plan_type

        # Clear temporary payment-specific context data that are no longer needed
        context.user_data.pop("total_cost", None) # This was just set above, should it be popped immediately?
        context.user_data.pop("tier", None)
        context.user_data.pop("posts", None)
        context.user_data.pop("qty", None) # Changed from 'tqty' based on prior usage
        context.user_data.pop("tqty", None) # Keep both for robustness if keys vary
        context.user_data.pop("x_poll_link", None)
        context.user_data.pop("x_poll_vote_option", None)
        context.user_data.pop("tg_custom", None)
        context.user_data.pop("x_custom", None)
        context.user_data.pop("tg_premium", None)
        context.user_data.pop("x_poll", None)
        context.user_data.pop("tg_automation", None) # Added for completeness
        context.user_data.pop("direct_add", None) # Added for completeness
        context.user_data.pop("slow_push", None) # Added for completeness

        logger.info(f"Payment processing complete for user {user_id}, guiding to next step for plan: {current_plan_type}.")