import os
import json
import uuid
import asyncio
import requests
import urllib3.util.connection as urllib3_cn
import logging
from typing import Optional, Dict, Any
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext
from utils.config import APIConfig
from utils.menu_utils import clear_bot_messages
from utils.messaging import escape_markdown_v2
from utils.db_utils import (
    get_referrer,
    update_affiliate_balance,
    save_purchase,
    mark_transaction_hash_as_processed,
    is_transaction_hash_processed
)
from utils.admin_utils import send_message_to_admin
from utils.bank_utils import get_bank_code_by_name_fuzzy


logger = logging.getLogger(__name__)

# Force requests/urllib3 to use IPv4 only
urllib3_cn.HAS_IPV6 = False

# Default display value for missing data
DEFAULT_NOT_AVAILABLE = 'N/A'

# -------------------------------
# Crypto Deposit Addresses
# -------------------------------
CRYPTO_DEPOSIT_ADDRESSES = {
    "bsc": os.getenv("BSC_DEPOSIT_ADDRESS", "0x7fF8c2F4510EdC4CcB74481588dca909730AEdF5"),
    "bnb": os.getenv("BSC_DEPOSIT_ADDRESS", "0x7fF8c2F4510EdC4CcB74481588dca909730AEdF5"),
    "sol": os.getenv("SOL_DEPOSIT_ADDRESS", "Gejh1bYCihLLk1BUwhnWKZEyurT7b8azBFXf44yy7MkB"),
    "trx": os.getenv("TRX_DEPOSIT_ADDRESS", "TGE9NvuxHGVWYpSoMYYszp8WjdKvRrUBv6"),
    "aptos": os.getenv("APTOS_DEPOSIT_ADDRESS", "0x45dbfe76bd52c159b096c2368a61836bedc3e3fe42a509f40bd09bded23aebb"),
}

def get_deposit_address(crypto_type: str = "bsc") -> str:
    """
    Returns the deposit address for the specified cryptocurrency.

    Args:
        crypto_type (str): The type of cryptocurrency (e.g., "bsc", "sol", "trx").

    Returns:
        str: The deposit address.

    Raises:
        ValueError: If the crypto type is unsupported.
    """
    key = crypto_type.lower()
    if key not in CRYPTO_DEPOSIT_ADDRESSES:
        raise ValueError(f"Unsupported crypto type: {crypto_type}")
    return CRYPTO_DEPOSIT_ADDRESSES[key]


# -------------------------------
# Coin-USD Conversions via CoinGecko
# -------------------------------
def convert_usd_to_crypto(usd_amount: float, crypto_id: str) -> Optional[float]:
    """
    Converts a USD amount to the specified cryptocurrency amount using CoinGecko's API.

    Args:
        usd_amount (float): The amount in USD.
        crypto_id (str): The CoinGecko ID of the cryptocurrency
                         (e.g., "binancecoin", "solana", "tron", "aptos").

    Returns:
        Optional[float]: The converted crypto amount, rounded to 8 decimal places,
                         or None if the conversion fails.
    """
    try:
        response = requests.get(
            f"https://api.coingecko.com/api/v3/simple/price",
            params={"ids": crypto_id, "vs_currencies": "usd"},
            timeout=10
        )
        response.raise_for_status()
        price = response.json().get(crypto_id, {}).get("usd")
        if price is None:
            print(f"Error: Could not get USD price for {crypto_id} from CoinGecko.")
            return None
        return round(usd_amount / price, 8)
    except requests.exceptions.RequestException as e:
        print(f"Network error during crypto to USD conversion for {crypto_id}: {e}")
        return None
    except json.JSONDecodeError:
        print(f"JSON decode error for CoinGecko response for {crypto_id}.")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during crypto to USD conversion for {crypto_id}: {e}")
        return None

def convert_crypto_to_usd(crypto_amount: float, crypto_id: str) -> Optional[float]:
    """
    Converts a cryptocurrency amount to USD using CoinGecko's API.

    Args:
        crypto_amount (float): The amount in cryptocurrency.
        crypto_id (str): The CoinGecko ID of the cryptocurrency.

    Returns:
        Optional[float]: The converted USD amount, rounded to 2 decimal places,
                         or None if the conversion fails.
    """
    try:
        response = requests.get(
            f"https://api.coingecko.com/api/v3/simple/price",
            params={"ids": crypto_id, "vs_currencies": "usd"},
            timeout=10
        )
        response.raise_for_status()
        price = response.json().get(crypto_id, {}).get("usd")
        if price is None:
            print(f"Error: Could not get USD price for {crypto_id} from CoinGecko.")
            return None
        return round(crypto_amount * price, 2)
    except requests.exceptions.RequestException as e:
        print(f"Network error during crypto to USD conversion for {crypto_id}: {e}")
        return None
    except json.JSONDecodeError:
        print(f"JSON decode error for CoinGecko response for {crypto_id}.")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during crypto to USD conversion for {crypto_id}: {e}")
        return None


# -------------------------------
# Transaction-Hash Timeout Handling
# -------------------------------
async def clear_transaction_hash_after_timeout(context: CallbackContext, timeout: int = 20 * 60):
    """
    After a specified timeout, clears the 'awaiting_transaction_hash' state
    for a user and updates the original payment message with a 'Main Menu' button.

    Args:
        context (CallbackContext): The context object for the Telegram bot.
        timeout (int): The duration in seconds after which the state should be cleared.
    """
    print(f"Clearing transaction hash after {timeout} seconds for user {context.user_data.get('user_id')}")
    await asyncio.sleep(timeout)

    user_id = context.user_data.get('user_id')
    if user_id and 'awaiting_transaction_hash' in context.user_data and context.user_data['awaiting_transaction_hash'] == user_id:
        context.user_data.pop('awaiting_transaction_hash', None)
        print(f"Cleared 'awaiting_transaction_hash' for user {user_id}")

        chat_id = context.chat_data.get("chat_id")
        msg_id = context.chat_data.get("payment_message_id")
        if chat_id and msg_id:
            keyboard = [[InlineKeyboardButton("Main Menu", callback_data="main_menu")]]
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text="⏰ Payment window expired. Please restart your purchase.",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                print(f"Edited payment message for user {user_id} due to timeout.")
            except Exception as e:
                print(f"Error editing message for user {user_id} after timeout: {e}")
    else:
        print(f"No active transaction hash awaiting for user {user_id} or flag mismatch. Not clearing.")


# -------------------------------
# Flutterwave Bank Transfers
# -------------------------------
def get_usd_to_ngn_rate() -> Optional[float]:
    """
    Fetches the USD to NGN exchange rate from exchangerate-api.com using the configured API key.

    Returns:
        Optional[float]: The USD to NGN conversion rate, or None if the request fails.
    """
    api_key = APIConfig.EXCHANGE_API_KEY
    if not api_key:
        print("EXCHANGE_API_KEY is not configured.")
        return None
    try:
        response = requests.get(
            f"https://v6.exchangerate-api.com/v6/{api_key}/latest/USD",
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        rate = data["conversion_rates"].get("NGN")
        if rate is None:
            print("Error: NGN conversion rate not found in API response.")
        return rate
    except requests.exceptions.RequestException as e:
        print(f"Network error fetching USD to NGN rate: {e}")
        return None
    except json.JSONDecodeError:
        print("JSON decode error fetching USD to NGN rate.")
        return None
    except Exception as e:
        print(f"An unexpected error occurred fetching USD to NGN rate: {e}")
        return None

def initiate_bank_transfer(
    amount: float,
    currency: str = "NGN",
    email: str = "chiiokevictoragu@gmail.com",
    phone_number: str = "09121121132405",
    meta: Optional[Dict[str, Any]] = None,
    is_permanent: bool = False,
    fullname: str = "Viral Core"
) -> Optional[Dict[str, Any]]:
    """
    Initiates a Flutterwave bank transfer charge to get temporary account details
    for a user to deposit into.

    Args:
        amount (float): The amount to be charged.
        currency (str): The currency of the charge (default: "NGN").
        email (str): The email of the customer.
        phone_number (str): The phone number of the customer.
        meta (Optional[Dict[str, Any]]): Additional metadata for the transaction.
        is_permanent (bool): Whether the generated account is permanent (default: False).
        fullname (str): The full name of the customer (default: "Viral Core").

    Returns:
        Optional[Dict[str, Any]]: A dictionary containing authorization details
                                   (e.g., transfer_account, transfer_bank, tx_ref)
                                   or None on failure.
    """
    _amount = int(amount)
    tx_ref = str(uuid.uuid4())
    payload = {
        "tx_ref": tx_ref,
        "amount": amount,
        "currency": currency,
        "email": email,
        "phone_number": phone_number,
        "fullname": fullname,
        "meta": meta or {},
        "is_permanent": is_permanent
    }
    headers = {
        "Authorization": f"Bearer {APIConfig.FLUTTERWAVE_API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(
            "https://api.flutterwave.com/v3/charges?type=bank_transfer",
            json=payload,
            headers=headers,
            timeout=10
        )
        response.raise_for_status()

        response_json = response.json()
        if response_json.get("status") == "success" and response_json.get("meta", {}).get("authorization"):
            authorization_details = response_json["meta"]["authorization"]
            authorization_details["tx_ref"] = tx_ref
            return authorization_details
        else:
            print(f"Flutterwave API returned non-success status for bank transfer initiation: "
                  f"{response_json.get('message', 'No message provided')}")
            return None
    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error during bank transfer initiation: {http_err} - Response: {response.text}")
        return None
    except requests.exceptions.ConnectionError as conn_err:
        print(f"Connection error during bank transfer initiation: {conn_err}")
        return None
    except requests.exceptions.Timeout as timeout_err:
        print(f"Timeout error during bank transfer initiation: {timeout_err}")
        return None
    except json.JSONDecodeError:
        print("JSON decode error for Flutterwave bank transfer initiation response.")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during bank transfer initiation: {e}")
        return None


async def poll_bank_payment_status(
    query_message: Any,
    update: Update,
    context: CallbackContext,
    tx_ref: str,
    total_cost_usd: float,
    user_id: int,
    username: Optional[str],
    timeout: int = 20 * 60,
    ordered_quantity: Optional[int] = None,
    current_plan_type: Optional[str] = None,
    interval: int = 20
) -> None:
    # ... (initial setup) ...
    start_time = asyncio.get_event_loop().time()
    flutterwave_api_key = APIConfig.FLUTTERWAVE_API_KEY
    user_username = update.effective_user.username if update.effective_user.username else str(user_id)

    # Check if this transaction hash has already been processed
    if is_transaction_hash_processed(tx_ref):
        await query_message.reply_text("This transaction has already been processed. Please check your balance or purchases.")
        return

    while True:
        elapsed_time = asyncio.get_event_loop().time() - start_time
        if elapsed_time > timeout:
            await query_message.reply_text("⏰ Bank payment timed out. Please try again.")
            context.user_data.pop('awaiting_bank_payment', None) # Clear the state
            break

        # Get the structured response from verify_transaction
        verification_result = verify_transaction(flutterwave_api_key, tx_ref)
        
        # Check the status from the structured response
        if verification_result["status"] == "success":
            tx_data = verification_result["data"] # Extract the data if successful
            print(f"Bank payment successful for tx_ref: {tx_ref}")

            # Mark transaction as processed FIRST to prevent double processing
            mark_transaction_hash_as_processed(tx_ref, user_id)
            print(f"Transaction {tx_ref} marked as processed for user {user_id}.")

            # The rate should ideally be fetched once per transaction, not in the loop,
            # but if it's dynamic, keep it here.
            # Assuming total_cost_usd is already in USD for saving the purchase.
            # If `total_cost` needs conversion from NGN, that should happen BEFORE
            # calling `poll_bank_payment_status`, and `total_cost_usd` should be the result.
            # The line `total_cost /= rate + 100` from your original snippet is commented out,
            # as it implies an NGN to USD conversion that's often better handled upstream
            # if `total_cost_usd` is truly representing USD.
            # If `total_cost` passed to this function *was* NGN, then reintroduce proper conversion.
            # For now, I'll assume total_cost_usd is already the USD value for recording.

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

            ordered_comments = 0
            if current_plan_type == "tg_custom":
                ordered_comments = context.user_data.get("tqty", 0)

            # Basic validation for plan_type and ordered_quantity
            if not current_plan_type or ordered_quantity is None:
                logger.error(f"Missing current_plan_type ({current_plan_type}) or ordered_quantity ({ordered_quantity}) for user {user_id} during payment processing.")
                await update.effective_chat.send_message("❌ Payment processed, but order details are unclear. Please contact support.")
                return
            
            # --- Process based on current_plan_type ---
            if current_plan_type == "tg_custom":
                tier = "tgt"
                context.user_data["awaiting_tg_username"] = True
                save_purchase(
                    user_id=user_id,
                    plan_type=tier,
                    comments=ordered_comments,
                    amount_paid_usd=total_cost_usd,
                    payment_method="Bank Transfer",
                    quantity=ordered_quantity,
                    transaction_ref=tx_ref,
                )
                await update.effective_chat.send_message(
                    r"Thank you for your Telegram Engagement order\! Send the Telegram Username associated with this payment\.",
                    parse_mode='MarkdownV2'
                )
            elif current_plan_type == "x_engagement":
                tier = context.user_data.get("tier", "x_custom_plan")
                print(f"Processing X Engagement for user {user_id} with tier {tier}, amount ${total_cost_usd:.2f}, hash {tx_ref}")
                context.user_data["awaiting_x_username"] = True
                save_purchase(
                    user_id=user_id,
                    plan_type=tier,
                    comments=ordered_comments, # Will be 0 for X custom, but kept for function signature consistency
                    amount_paid_usd=total_cost_usd,
                    payment_method="Bank Transfer",
                    quantity=ordered_quantity,
                    transaction_ref=tx_ref,
                )
                await update.effective_chat.send_message(
                    r"Thank you for your X \(Twitter\) Engagement order\! Send the Twitter Username associated with this payment\.",
                    parse_mode='MarkdownV2'
                )
            elif current_plan_type == "tg_automation":
                safe_username = escape_markdown_v2(user_username if user_username else DEFAULT_NOT_AVAILABLE)
                safe_tx_ref = escape_markdown_v2(tx_ref if tx_ref else DEFAULT_NOT_AVAILABLE)
                admin_message = (
                    f" *NEW TELEGRAM AUTOMATION REQUEST\\!* \n\n"
                    f"User ID: `{user_id}`\n"
                    f"Username: @{safe_username}\n"
                    f"Payment Confirmed: `${total_cost_usd:.2f}` via \\(TxRef: `{safe_tx_ref}`\\)"
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
                    amount_paid_usd=total_cost_usd,
                    payment_method="Bank Transfer",
                    quantity=ordered_quantity,
                    transaction_ref=tx_ref,
                )
                context.user_data["awaiting_x_poll_details"] = True
                await update.effective_chat.send_message(
                    r"Please send the X \(Twitter\) poll link and the option number "
                    r"you want to vote for, separated by a comma \(`https://x.com/status/1234567890/polls/abcdef, 1`\)",
                    parse_mode='MarkdownV2'
                )
            elif current_plan_type == "direct_add":
                save_purchase( # Assuming you want to save direct_add purchases
                    user_id=user_id,
                    plan_type="direct_add",
                    comments=0,
                    amount_paid_usd=total_cost_usd,
                    payment_method="Bank Transfer",
                    quantity=ordered_quantity,
                    transaction_ref=tx_ref,
                )
                context.user_data["awaiting_direct_add_link_input"] = True
                await update.effective_chat.send_message(
                    r"Please send the X \(Twitter\) profile link for your Direct Add Followers order \(e\.g\., `https://x.com/username`\)",
                    parse_mode='MarkdownV2'
                )
            elif current_plan_type == "slow_push":
                save_purchase( # Assuming you want to save slow_push purchases
                    user_id=user_id,
                    plan_type="slow_push",
                    comments=0,
                    amount_paid_usd=total_cost_usd,
                    payment_method="Bank Transfer",
                    quantity=ordered_quantity,
                    transaction_ref=tx_ref,
                )
                context.user_data["awaiting_slow_push_profile_link"] = True
                await update.effective_chat.send_message(
                    r"Please send the X \(Twitter\) profile link for your Slow Push Followers order \(e\.g\., `https://x.com/username`\)",
                    parse_mode='MarkdownV2'
                )
            else:
                # Default fallback for any other service, if no specific instructions
                save_purchase( # Consider if all other types should be saved universally
                    user_id=user_id,
                    plan_type=current_plan_type,
                    comments=ordered_comments,
                    amount_paid_usd=total_cost_usd,
                    payment_method="Bank Transfer",
                    quantity=ordered_quantity,
                    transaction_ref=tx_ref,
                )
                await update.effective_chat.send_message(
                    r"Your order has been placed and will be processed shortly\. Thank you\!",
                    parse_mode='MarkdownV2'
                )

            logger.info(f"Purchase saved and/or notification sent for user {user_id}: Plan '{current_plan_type}' x {ordered_quantity} via {"Bank Transfer",}. Amount: ${total_cost_usd:.2f}.")

            # --- Affiliate Bonus Logic (Applies to all confirmed payments) ---
            referrer = get_referrer(user_id)
            if referrer:
                bonus_amount = total_cost_usd * 0.1
                update_affiliate_balance(referrer['id'], bonus_amount)
                try:
                    username_to_display = username or f"User {user_id}"
                    await context.bot.send_message(
                        chat_id=referrer['id'],
                        text=f"💰 Your referral @{username_to_display} just made a payment of ${total_cost_usd:.2f}!\n"
                             f"You've earned a bonus of ${bonus_amount:.2f}."
                    )
                    print(f"Affiliate bonus of {bonus_amount} sent to referrer {referrer['id']}.")
                except Exception as e:
                    print(f"Error notifying referrer (ID: {referrer['id']}): {e}")

            # --- Clear All Payment-Related User Data Flags ---
            context.user_data.pop('awaiting_bank_payment', None)
            context.user_data.pop('total_cost', None)
            context.user_data.pop('posts', None)
            context.user_data.pop('tier', None)
            context.user_data.pop('tg_custom', None)
            context.user_data.pop('x_custom', None)
            context.user_data.pop('tg_premium', None)
            context.user_data.pop('x_poll', None)
            context.user_data.pop('tg_automation', None)
            context.user_data.pop('awaiting_transaction_hash', None) # Clear this general flag as well

            break # Exit the polling loop as payment is confirmed
        elif verification_result["status"] == "failed":
            # If the transaction explicitly failed (e.g., underpaid, refunded)
            await query_message.reply_text(f"❌ Bank payment failed: {verification_result['message']}. Please try again.")
            context.user_data.pop('awaiting_bank_payment', None) # Clear the state
            break # Exit loop on confirmed failure

        elif verification_result["status"] == "error":
            # If there was an API/network error during verification
            # You might want to retry for a bit longer or inform the user about a technical issue
            print(f"Error during bank payment verification for {tx_ref}: {verification_result['message']}. Retrying...")
            # Don't break here immediately, allow it to retry if it's a transient error.
            # However, you might want a separate counter for "error" retries to avoid infinite loops on persistent errors.
            pass # Continue loop

        elif verification_result["status"] == "pending":
            # This means the transaction is not found yet, which is expected during polling
            print(f"Bank payment for {tx_ref} is still pending: {verification_result['message']}")
            pass # Continue loop

        await asyncio.sleep(interval)


def initiate_flutterwave_transfer(
    account_bank: str,
    account_number: str,
    amount: float,
    beneficiary_name: str,
    reference: str = str(uuid.uuid4()),
    narration: str = "ViralCore Withdrawal",
    currency: str = "NGN",
    debit_subaccount: Optional[str] = None,
    beneficiary: Optional[int] = None,
    debit_currency: Optional[str] = None,
    destination_branch_code: Optional[str] = None
) -> Dict[str, Any]:
    """
    Initiates a Flutterwave Payout (transfer) to a bank account.

    Args:
        account_bank (str): The name of the beneficiary bank.
        account_number (str): The beneficiary's bank account number.
        amount (float): The amount to transfer.
        beneficiary_name (str): The name of the beneficiary.
        reference (str): A unique reference for the transaction (defaults to a UUID).
        narration (str): A short description of the transfer (default: "ViralCore Withdrawal").
        currency (str): The currency of the transfer (default: "NGN").
        debit_subaccount (Optional[str]): The ID of the subaccount to debit.
        beneficiary (Optional[int]): The ID of the beneficiary.
        debit_currency (Optional[str]): The currency of the debit account.
        destination_branch_code (Optional[str]): The branch code of the destination bank.

    Returns:
        Dict[str, Any]: A dictionary containing the transfer status and details.
                        Returns {"status": "error", "message": "..."} on failure.
    """
    url = "https://api.flutterwave.com/v3/transfers"
    flutterwave_secret_key = APIConfig.FLUTTERWAVE_API_KEY
    reference = f"{beneficiary_name.replace(' ', '-')}_{str(uuid.uuid4())}"

    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {flutterwave_secret_key}",
        "Content-Type": "application/json"
    }

    bank_code = get_bank_code_by_name_fuzzy(account_bank)
    if not bank_code:
        return {"status": "error", "message": f"Could not find bank code for '{account_bank}'."}

    payload = {
        "account_bank": bank_code,
        "account_number": account_number,
        "amount": amount,
        "currency": currency,
        "reference": reference,
        "beneficiary_name": beneficiary_name,
        "narration": narration
    }

    if debit_subaccount is not None:
        payload["debit_subaccount"] = debit_subaccount
    if beneficiary is not None:
        payload["beneficiary"] = beneficiary
    if debit_currency is not None:
        payload["debit_currency"] = debit_currency
    if destination_branch_code is not None:
        payload["destination_branch_code"] = destination_branch_code

    try:
        # Try to use new structured API client if available
        try:
            from utils.api_client import get_flutterwave_client, create_admin_error_message
            
            # Use structured API client
            client = get_flutterwave_client()
            
            result = client.initiate_transfer(
                amount=amount,
                beneficiary_name=beneficiary_name,
                account_number=account_number,
                account_bank=bank_code,
                reference=reference,
                narration=narration,
                currency=currency,
                debit_currency=debit_currency
            )
            
            # Log the result for admin diagnostics
            if result['success']:
                logger.info(f"Flutterwave transfer initiated successfully: {result['trace_id']}")
                return {
                    "status": "success",
                    "id": result['data'].get('id'),
                    "is_approved": result['data'].get('is_approved'),
                    "status_detail": result['data'].get('status'),
                    "created_at": result['data'].get('created_at'),
                    "amount": result['data'].get('amount'),
                    "fee": result['data'].get('fee'),
                    "reference": result['data'].get('reference'),
                    "trace_id": result['trace_id']
                }
            else:
                admin_error = create_admin_error_message(
                    error=result.get('error', 'Unknown error'),
                    operation="Flutterwave transfer"
                )
                logger.error(f"Flutterwave transfer failed: {admin_error}")
                return {
                    "status": "error",
                    "message": result.get('error', 'Unknown error'),
                    "trace_id": result.get('trace_id')
                }
                
        except ImportError:
            # Fall through to original implementation
            pass
        
        # Original implementation as fallback
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        response_data = response.json()

        if response_data.get("status") == "success" and "data" in response_data:
            data = response_data["data"]
            return {
                "status": response_data.get("status"),
                "id": data.get("id"),
                "is_approved": data.get("is_approved"),
                "status_detail": data.get("status"),
                "created_at": data.get("created_at"),
                "amount": data.get("amount"),
                "fee": data.get("fee"),
                "reference": data.get("reference")
            }
        else:
            return {"status": "error", "message": response_data.get("message", "Unknown error in API response")}
    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error during Flutterwave transfer: {http_err} - Response: {response.text}")
        return {"status": "error", "message": f"HTTP error: {http_err}. Details: {response.text}"}
    except requests.exceptions.ConnectionError as conn_err:
        print(f"Connection error during Flutterwave transfer: {conn_err}")
        return {"status": "error", "message": f"Connection error: {conn_err}"}
    except requests.exceptions.Timeout as timeout_err:
        print(f"Timeout error during Flutterwave transfer: {timeout_err}")
        return {"status": "error", "message": f"Timeout error: {timeout_err}"}
    except json.JSONDecodeError:
        print("Error decoding JSON response from Flutterwave API.")
        return {"status": "error", "message": "Invalid JSON response from API."}
    except KeyError as e:
        print(f"Missing expected key in Flutterwave API response: {e}")
        return {"status": "error", "message": f"Missing expected data in API response: {e}"}
    except Exception as e:
        print(f"An unexpected error occurred during Flutterwave transfer: {e}")
        return {"status": "error", "message": f"An unexpected error occurred: {e}"}


def verify_transaction(api_key: str, tx_ref: str) -> Dict[str, Any]: # Changed return type hint
    """
    Verifies a Flutterwave transaction by its `tx_ref`.

    Args:
        api_key (str): Your Flutterwave API secret key.
        tx_ref (str): The transaction reference to verify.

    Returns:
        Dict[str, Any]: A dictionary containing:
                        - "status": "success", "failed", "pending", or "error"
                        - "message": A descriptive message (for failed/pending/error)
                        - "data": The transaction data (for success)
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        response = requests.get(
            f"https://api.flutterwave.com/v3/transactions/verify_by_reference",
            params={"tx_ref": tx_ref},
            headers=headers,
            timeout=10
        )
        response.raise_for_status() # Raises HTTPError for bad responses (4xx or 5xx)
        body = response.json()
        
        # print(body) # Keep this for debugging if needed

        # Check the top-level API response status
        if body.get("status") == "success" and body.get("data") is not None:
            transaction_data = body["data"]
            transaction_status = transaction_data.get("status")
            processor_response = transaction_data.get("processor_response")

            if transaction_status in ["success", "completed", "successful"]: # Flutterwave uses "successful" or "completed" for success
                return {"status": "success", "data": transaction_data}
            else:
                # API call was successful, but the transaction itself has a non-success status
                message = processor_response if processor_response else f"Transaction status: {transaction_status}"
                print(f"Transaction verification failed for tx_ref {tx_ref}. "
                      f"API Status: success, Transaction Status: {transaction_status}, "
                      f"Processor Response: {processor_response}")
                return {"status": "failed", "message": f"Transaction not confirmed: {message}"}
        else:
            # Top-level API status is not "success" or 'data' is missing
            message = body.get("message", "Unknown error from Flutterwave API.")
            print(f"Flutterwave API response non-success for {tx_ref}: {message}")
            return {"status": "failed", "message": f"Flutterwave API error: {message}"}

    except requests.exceptions.HTTPError as http_err:
        # Catch specific "No transaction found" for pending status
        if response.status_code == 404 and 'No transaction was found for this id' in response.text:
            # print(f"Transaction {tx_ref} is not yet found or processed on Flutterwave (404).")
            return {"status": "pending", "message": f"Transaction {tx_ref} not found yet. Still waiting."}
        else:
            # print(f"HTTP error during transaction verification for {tx_ref}: {http_err} - Response: {response.text}")
            return {"status": "error", "message": f"HTTP error during verification: {http_err}. Full response: {response.text}"}
    except requests.exceptions.ConnectionError as conn_err:
        # print(f"Connection error during transaction verification for {tx_ref}: {conn_err}")
        return {"status": "error", "message": f"Connection error during verification: {conn_err}. Please check internet."}
    except requests.exceptions.Timeout as timeout_err:
        # print(f"Timeout error during transaction verification for {tx_ref}: {timeout_err}")
        return {"status": "error", "message": f"Verification timed out. Flutterwave API took too long to respond."}
    except json.JSONDecodeError:
        # print(f"JSON decode error for Flutterwave transaction verification response for {tx_ref}.")
        return {"status": "error", "message": "Invalid response from Flutterwave API. Please try again."}
    except Exception as e:
        # print(f"An unexpected error occurred during transaction verification for {tx_ref}: {e}")
        return {"status": "error", "message": f"An unexpected error occurred during verification: {e}."}

