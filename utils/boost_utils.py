import asyncio
import logging
import aiosqlite
import aiohttp
import time
import json
from typing import Dict, Optional, Any

from telegram import Bot

from utils.db_utils import GROUPS_TWEETS_DB_FILE
from utils.config import APIConfig
from utils.menu_utils import escape_md
from utils.boost_provider_utils import get_active_provider, ProviderConfig
from utils.notification import TARGET_NOTIFICATION_GROUP_ID_FROM_DB, get_group_id_from_db, notify_admin as admin_notify

# Configure logging
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

# --- Constants ---
# Intervals for phased boosting
FIRST_BOOST_INTERVAL_SECONDS = 15 * 60  # 15 minutes
SECOND_BOOST_INTERVAL_SECONDS = 45 * 60 # 45 minutes

# Retry configuration for ordering boosts
# >>> MISSING VALUES ADDED HERE <<<
MAX_ORDER_RETRIES = 10
ORDER_RETRY_DELAY_SECONDS = 30
# >>> END OF ADDED VALUES <<<

# Active order handling for boost services
ACTIVE_ORDER_CHECK_INTERVAL_SECONDS = 10 * 60   # 10 minutes
ACTIVE_ORDER_TIMEOUT_SECONDS = 2 * 60 * 60      # 2 hours

# Initialize Telegram Bot
bot = Bot(token=APIConfig.TELEGRAM_BOT_TOKEN)

# --- Boost Service API Interactions ---

async def get_boost_service_balance() -> Optional[Dict[str, Any]]:
    """
    Fetches the current balance from the active boost service provider.

    Returns:
        Optional[Dict[str, Any]]: A dictionary containing balance information
                                  (e.g., {'balance': 123.45, 'currency': 'USD'}),
                                  or None if fetching fails.
    """
    try:
        provider = get_active_provider()
        logger.info(f"[Boost] Attempting to fetch balance for provider: {provider.name}")

        payload = {
            "key": provider.api_key,
            "action": "balance"
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(provider.api_url, data=payload, timeout=15) as response:
                response.raise_for_status()
                balance_data = await response.json()
                logger.info(f"[Boost] Successfully fetched balance for {provider.name}: {balance_data}")
                return balance_data
    except aiohttp.ClientError as e:
        logger.error(f"[Boost] Network or HTTP error fetching balance for {provider.name}: {e}")
        return None
    except asyncio.TimeoutError:
        logger.error(f"[Boost] Timeout fetching balance for {provider.name}.")
        return None
    except json.JSONDecodeError:
        logger.error(f"[Boost] Invalid JSON response when fetching balance for {provider.name}.")
        return None
    except Exception as e:
        logger.error(f"[Boost] Unexpected error fetching balance for {provider.name}: {e}")
        return None

async def _order_boost(
    service_id: int,
    link: str,
    quantity: int,
) -> Optional[dict]:
    """
    Places an order for a boost service with retry logic and active order handling.

    Args:
        service_id (int): The ID of the boost service.
        link (str): The link to apply the boost to.
        quantity (int): The quantity of the boost.

    Returns:
        Optional[dict]: The response data from the boost service if successful, None otherwise.
    """
    provider = get_active_provider()
    payload = {
        "key": provider.api_key,
        "action": "add",
        "service": service_id,
        "link": link,
        "quantity": quantity
    }

    attempt = 1
    active_order_start_time = None

    while attempt <= MAX_ORDER_RETRIES: # Use the defined constant
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(provider.api_url, data=payload, timeout=30) as resp:
                    resp.raise_for_status()
                    data = await resp.json()

                    if isinstance(data, dict) and data.get("error", "").startswith("You have active order"):
                        now = time.time()
                        if active_order_start_time is None:
                            active_order_start_time = now
                            logger.info(f"[Boost] Active order detected for {link}. Retrying every "
                                        f"{ACTIVE_ORDER_CHECK_INTERVAL_SECONDS / 60:.0f}m up to "
                                        f"{ACTIVE_ORDER_TIMEOUT_SECONDS / 3600:.0f}h.")

                        elapsed = now - active_order_start_time
                        if elapsed >= ACTIVE_ORDER_TIMEOUT_SECONDS:
                            logger.error(f"[Boost] Timeout for active order {link} (service_id: {service_id}, qty: {quantity}). Notifying admin.")
                            await notify_admin(link, service_id, quantity, reason="Active order timeout")
                            return None

                        logger.info(f"[Boost] Waiting {ACTIVE_ORDER_CHECK_INTERVAL_SECONDS // 60:.0f}m for active order to clear (elapsed: {elapsed // 60:.1f} min)")
                        await asyncio.sleep(ACTIVE_ORDER_CHECK_INTERVAL_SECONDS)
                        continue

                    if "error" not in data:
                        logger.info(f"[Boost] Order successful for service={service_id}, link={link}, qty={quantity}. Response: {data}")
                        return data
                    else:
                        logger.warning(f"[Boost] Error for order {link} (service_id: {service_id}, qty: {quantity}): {data.get('error')}. Attempt {attempt}/{MAX_ORDER_RETRIES}.")
                        await asyncio.sleep(ORDER_RETRY_DELAY_SECONDS) # Use the defined constant
                        if data.get("error") == "Not enough funds on balance":
                            logger.error(f"[Boost] Insufficient balance for {link} (service_id: {service_id}, qty: {quantity}). Notifying admin.")
                            await notify_admin(link, service_id, quantity, reason="Insufficient balance")
                            return None
                        else:
                            attempt += 1
                            continue

        except aiohttp.ClientError as e:
            logger.warning(f"[Boost] Network/HTTP error on attempt {attempt}/{MAX_ORDER_RETRIES} for {link}: {e}")
            await asyncio.sleep(ORDER_RETRY_DELAY_SECONDS) # Use the defined constant
            attempt += 1
        except asyncio.TimeoutError:
            logger.warning(f"[Boost] Timeout on attempt {attempt}/{MAX_ORDER_RETRIES} for {link}.")
            await asyncio.sleep(ORDER_RETRY_DELAY_SECONDS) # Use the defined constant
            attempt += 1
        except json.JSONDecodeError:
            logger.warning(f"[Boost] Invalid JSON response on attempt {attempt}/{MAX_ORDER_RETRIES} for {link}.")
            await asyncio.sleep(ORDER_RETRY_DELAY_SECONDS) # Use the defined constant
            attempt += 1
        except Exception as e:
            logger.error(f"[Boost] Unexpected error on attempt {attempt}/{MAX_ORDER_RETRIES} for {link}: {e}")
            await asyncio.sleep(ORDER_RETRY_DELAY_SECONDS) # Use the defined constant
            attempt += 1

    logger.error(f"[Boost] FAILED to place order for {link} (service_id: {service_id}, qty: {quantity}) after {MAX_ORDER_RETRIES} attempts. Notifying admin.")
    await notify_admin(link, service_id, quantity, reason="Failed after max retries")
    return None

async def notify_admin(link: str, service_id: int, quantity: int, reason: str = "Unknown error"):
    """
    Sends a 'Boost Order Failed' notification to a specific group whose ID is
    retrieved from the GROUPS_TWEETS_DB_FILE.
    """
    message = (
        f"❗ *Boost Order Failed\!* ❗\n\n"
        f"🔗 *Link*: `{link}`\n"
        f"📢 *Provider*: `{get_active_provider().name}`\n"
        f"🛠️ *Service ID*: `{service_id}`\n"
        f"📦 *Quantity*: `{quantity}`\n"
        f"⚠️ *Reason*: _{reason}_"
    )

    try:
        # 1. Fetch the actual group chat ID from the database
        group_chat_id = await get_group_id_from_db(TARGET_NOTIFICATION_GROUP_ID_FROM_DB)

        if group_chat_id is None:
            logger.warning(f"[BoostNotify] Cannot send notification. Target group ID {TARGET_NOTIFICATION_GROUP_ID_FROM_DB} not found in {GROUPS_TWEETS_DB_FILE}.")
            return

        # 2. Send the message to the retrieved group chat ID
        try:
            # Note: MarkdownV2 is generally preferred for better control and escaping
            # Telegram's Markdown parsing has two modes: Markdown and MarkdownV2.
            # Using MarkdownV2 here. Ensure your `message` adheres to MarkdownV2 rules.
            await bot.send_message(chat_id=group_chat_id, text=message, parse_mode="MarkdownV2")
            logger.info(f"[BoostNotify] Group {group_chat_id} successfully notified about failed boost.")
        except Exception as e:
            logger.error(f"[BoostNotify] Failed to send notification to group {group_chat_id}: {e}")
    except Exception as e:
        logger.error(f"[BoostNotify] Unexpected error during group notification for failed boost: {e}", exc_info=True)



class BoostManager:
    def __init__(self):
        self._tasks: Dict[str, asyncio.Task] = {}

    def start_boost(self, link: str, likes: int = 100, views: int = 500, comments: int = 0, user_id: Optional[int] = None):
        """
        Start boost with enhanced service if available, otherwise fallback to legacy.
        
        Args:
            link: URL to boost
            likes: Number of likes requested
            views: Number of views requested  
            comments: Number of comments requested
            user_id: Optional user ID for tracking
        """
        # Try to use enhanced service first
        try:
            from utils.boost_utils_enhanced import enhanced_boost_service
            
            if enhanced_boost_service:
                return self._start_enhanced_boost(link, likes, views, comments, user_id)
        except ImportError:
            logger.debug("[BoostManager] Enhanced service not available, using legacy")
        except Exception as e:
            logger.warning(f"[BoostManager] Enhanced service failed, falling back to legacy: {e}")
        
        # Fallback to legacy implementation
        return self._start_legacy_boost(link, likes, views, comments)
    
    def _start_enhanced_boost(self, link: str, likes: int, views: int, comments: int, user_id: Optional[int]):
        """Start boost using enhanced service with job system."""
        if link in self._tasks and not self._tasks[link].done():
            logger.info(f"[BoostManager] Boost for {link} is already running.")
            return
        
        async def _enhanced_boost_task():
            try:
                from utils.boost_utils_enhanced import enhanced_boost_service
                from utils.logging import generate_correlation_id
                
                correlation_id = generate_correlation_id()
                
                # Use enhanced service which handles all error handling, retries, etc.
                response = await enhanced_boost_service.request_boost(
                    link=link,
                    likes=likes,
                    views=views,
                    comments=comments,
                    user_id=user_id,
                    correlation_id=correlation_id
                )
                
                logger.info(
                    f"[BoostManager] Enhanced boost completed for {link}: {response.status}",
                    extra={'job_id': response.job_id, 'correlation_id': correlation_id}
                )
            except Exception as e:
                logger.error(f"[BoostManager] Enhanced boost failed for {link}: {e}")
            finally:
                self._tasks.pop(link, None)
        
        task = asyncio.create_task(_enhanced_boost_task())
        self._tasks[link] = task
        logger.info(f"[BoostManager] Enhanced boost task for {link} scheduled.")
    
    def _start_legacy_boost(self, link: str, likes: int, views: int, comments: int):
        """Legacy boost implementation - kept for backward compatibility."""
        if link in self._tasks and not self._tasks[link].done():
            logger.info(f"[BoostManager] Boost for {link} is already running.")
            return

        async def _boost_sequence_task():
            try:
                current_balance = await get_boost_service_balance()
                if current_balance.get('currency', 'Units') == "USD":
                    MIN_BALANCE = 5.0 # Assuming balance is in USD
                else:
                    MIN_BALANCE = 5000.0  # Assuming balance is in units if not USD
                if float(current_balance['balance']) <= MIN_BALANCE:
                    logger.error(f"[BoostManager] Low balance for boosting {link}. Current balance: {current_balance}")
                    # Notify admin about insufficient balance
                    provider = get_active_provider()
                    admin_message = (
                        f"🔔 *Boost Service Balance Alert* 🔔\n\n"
                        f"Current balance on {provider.name} for boosting is low: {current_balance.get('currency', 'Units')} {escape_md(current_balance['balance'])}\n"
                        f"\nKindly top up your balance to continue boosting services\.\n\n"
                    )
                    logger.info(f"[BoostManager] Notifying admin about low balance for boosting {link}.")
                    await admin_notify(user_id=6030280354, message=admin_message)
            except Exception as e:
                logger.error(f"[BoostManager] Error fetching boost service balance: {e}")
            try:
                logger.info(f"[BoostManager] Initiating 1-hour phased boost for link: {link}")
                provider = get_active_provider()
                logger.debug(f"Provider View Service ID: {provider.view_service_id}, Like Service ID: {provider.like_service_id}")

                first_half_views = views // 2
                first_half_likes = (likes - comments) // 2

                if first_half_views > 0 or first_half_likes > 0:
                    logger.info(
                        f"[BoostManager] Waiting {FIRST_BOOST_INTERVAL_SECONDS//60}m before first batch for {link}"
                    )
                    await asyncio.sleep(FIRST_BOOST_INTERVAL_SECONDS)

                    # send both, if present
                    if first_half_views > 0:
                        await _order_boost(provider.view_service_id, link, first_half_views)
                    if first_half_likes > 0:
                        await _order_boost(provider.like_service_id, link, first_half_likes)

                    logger.info(
                        f"[BoostManager] First batch sent: {first_half_views} views, {first_half_likes} likes for {link}"
                    )
                else:
                    logger.info(f"[BoostManager] No first batch to send for {link} (0 quantity).")

                logger.info(f"[BoostManager] Waiting {SECOND_BOOST_INTERVAL_SECONDS // 60} minutes for second boost stage for {link}...")
                await asyncio.sleep(SECOND_BOOST_INTERVAL_SECONDS)

                remaining_views = max(views - first_half_views, 0)
                remaining_likes = max(likes - first_half_likes, 0)

                if remaining_views > 0:
                    await _order_boost(provider.view_service_id, link, remaining_views)
                    logger.info(f"[BoostManager] Remaining {remaining_views} views sent for {link}.")
                else:
                    logger.info(f"[BoostManager] No remaining views to send for {link} (quantity 0).")

                if remaining_likes > 0:
                    await _order_boost(provider.like_service_id, link, remaining_likes)
                    logger.info(f"[BoostManager] {remaining_likes} likes sent for {link}.")
                else:
                    logger.info(f"[BoostManager] No likes to send for {link} (quantity 0).")

                logger.info(f"[BoostManager] Successfully completed phased boost for {link}.")

            except asyncio.CancelledError:
                logger.info(f"[BoostManager] Boost task for {link} was cancelled.")
            except Exception as e:
                logger.error(f"[BoostManager] Unhandled error during boost for {link}: {e}", exc_info=True)
            finally:
                self._tasks.pop(link, None)
                logger.debug(f"[BoostManager] Task for {link} removed from manager.")

        task = asyncio.create_task(_boost_sequence_task())
        self._tasks[link] = task
        logger.info(f"[BoostManager] Boost task for {link} scheduled.")

    def cancel_boost(self, link: str):
        task = self._tasks.get(link)
        if task and not task.done():
            task.cancel()
            logger.info(f"[BoostManager] Attempting to cancel boost for {link}.")
        elif task and task.done():
            logger.info(f"[BoostManager] Boost for {link} already finished (status: {task.done()}).")
            self._tasks.pop(link, None)
        else:
            logger.info(f"[BoostManager] No active boost task found for {link} to cancel.")

    async def cancel_all(self):
        logger.info("[BoostManager] Cancelling all active boost tasks.")
        tasks_to_cancel = list(self._tasks.values())
        if not tasks_to_cancel:
            logger.info("[BoostManager] No active boost tasks to cancel.")
            return

        for task in tasks_to_cancel:
            if not task.done():
                task.cancel()
        
        await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
        self._tasks.clear()
        logger.info("[BoostManager] All boost tasks cancellation attempts completed.")


boost_manager = BoostManager()