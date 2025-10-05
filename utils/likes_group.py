#!/usr/bin/env python3
# utils/likes_group.py
"""
Utility module for sending posts to the Likes Group.

The Likes Group is an independent admin group that:
- Receives every post (exempt from rotation)
- Gets a payload with likes_needed metric instead of comments/retweets
- Operates independently - failures don't affect Group 1 sends
"""

import logging
import time
import uuid
from typing import Optional, Dict, Any
from telegram.ext import ContextTypes

from settings.bot_settings import (
    ADMIN_LIKES_GROUP_ENABLED,
    ADMIN_LIKES_GROUP_CHAT_ID,
)

logger = logging.getLogger(__name__)

# Metrics counters (in-memory for now, can be extended to use proper metrics system)
METRICS = {
    "posts_sent_group1": 0,
    "posts_sent_group2": 0,
    "posts_failed_group2": 0,
    "posts_deduped_group2": 0,
}

# Track sent posts for deduplication (simple in-memory cache)
# In production, this should use Redis or database
_sent_posts_cache: Dict[str, float] = {}
_CACHE_TTL_SECONDS = 3600  # 1 hour


def _generate_correlation_id() -> str:
    """Generate a unique correlation ID for tracking."""
    return str(uuid.uuid4())


def _is_duplicate(post_id: str) -> bool:
    """
    Check if a post has already been sent to Likes Group.
    Uses simple TTL-based cache for deduplication.
    """
    now = time.time()
    
    # Clean up expired entries
    expired_keys = [k for k, v in _sent_posts_cache.items() if now - v > _CACHE_TTL_SECONDS]
    for k in expired_keys:
        del _sent_posts_cache[k]
    
    if post_id in _sent_posts_cache:
        return True
    
    return False


def _mark_as_sent(post_id: str):
    """Mark a post as sent to prevent duplicates."""
    _sent_posts_cache[post_id] = time.time()


def _build_likes_group_message(
    post_id: str,
    content: str,
    likes_needed: int,
    correlation_id: str,
) -> str:
    """
    Build the message payload for Likes Group.
    
    Format:
    🎯 New Post - Likes Needed 🎯
    
    🆔 ID: {post_id}
    🔗 {content}
    
    ❤️ Likes Needed: {likes_needed}
    
    🔍 Correlation ID: {correlation_id}
    ⏰ Timestamp: {timestamp}
    """
    from telegram.helpers import escape_markdown
    from datetime import datetime
    
    safe_content = escape_markdown(content, version=2)
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    
    message = (
        "🎯 *New Post \\- Likes Needed* 🎯\n\n"
        f"🆔 *ID:* `{post_id}`\n"
        f"🔗 {safe_content}\n\n"
        f"❤️ *Likes Needed:* `{likes_needed}`\n\n"
        f"🔍 *Correlation ID:* `{correlation_id}`\n"
        f"⏰ *Timestamp:* `{timestamp}`"
    )
    
    return message


async def send_to_likes_group(
    context: ContextTypes.DEFAULT_TYPE,
    post_id: str,
    content: str,
    likes_needed: int,
    post_type: str = "twitter",  # or "telegram"
) -> bool:
    """
    Send a post to the Likes Group with likes_needed metric.
    
    This function:
    - Is exempt from rotation (always sends)
    - Fails safely (doesn't affect Group 1)
    - Implements deduplication
    - Logs structured events
    - Tracks metrics
    
    Args:
        context: Telegram context
        post_id: Unique identifier for the post (tweet_id or tg_link hash)
        content: The post link/content to display
        likes_needed: Number of likes needed for this post
        post_type: Type of post ("twitter" or "telegram")
    
    Returns:
        True if sent successfully, False otherwise
    """
    # Check if feature is enabled
    if not ADMIN_LIKES_GROUP_ENABLED:
        logger.debug("[LikesGroup] Feature disabled, skipping send")
        return False
    
    # Validate configuration
    if not ADMIN_LIKES_GROUP_CHAT_ID:
        logger.error("[LikesGroup] ADMIN_LIKES_GROUP_CHAT_ID not configured")
        METRICS["posts_failed_group2"] += 1
        return False
    
    # Check for duplicates
    if _is_duplicate(post_id):
        logger.info(f"[LikesGroup] Duplicate post {post_id}, skipping send")
        METRICS["posts_deduped_group2"] += 1
        return False
    
    # Generate correlation ID for tracking
    correlation_id = _generate_correlation_id()
    
    # Build message
    try:
        message_text = _build_likes_group_message(
            post_id=post_id,
            content=content,
            likes_needed=likes_needed,
            correlation_id=correlation_id,
        )
    except Exception as e:
        logger.error(
            f"[LikesGroup] Failed to build message for post {post_id}: {e}",
            exc_info=True,
            extra={
                "post_id": post_id,
                "correlation_id": correlation_id,
                "error": str(e),
            }
        )
        METRICS["posts_failed_group2"] += 1
        return False
    
    # Send to Likes Group
    try:
        await context.bot.send_message(
            chat_id=ADMIN_LIKES_GROUP_CHAT_ID,
            text=message_text,
            parse_mode="MarkdownV2",
        )
        
        # Mark as sent to prevent duplicates
        _mark_as_sent(post_id)
        
        # Track success
        METRICS["posts_sent_group2"] += 1
        
        # Structured logging
        logger.info(
            f"[LikesGroup] Successfully sent post to Likes Group",
            extra={
                "post_id": post_id,
                "likes_needed": likes_needed,
                "correlation_id": correlation_id,
                "post_type": post_type,
                "chat_id": ADMIN_LIKES_GROUP_CHAT_ID,
                "status": "success",
            }
        )
        
        return True
        
    except Exception as e:
        # Log failure but don't raise - this is a fail-safe operation
        logger.error(
            f"[LikesGroup] Failed to send post {post_id} to Likes Group: {e}",
            exc_info=True,
            extra={
                "post_id": post_id,
                "likes_needed": likes_needed,
                "correlation_id": correlation_id,
                "post_type": post_type,
                "chat_id": ADMIN_LIKES_GROUP_CHAT_ID,
                "status": "failed",
                "error": str(e),
            }
        )
        
        METRICS["posts_failed_group2"] += 1
        
        # TODO: Implement retry logic with backoff
        # TODO: Surface error to admin alerts
        
        return False


def get_metrics() -> Dict[str, int]:
    """Get current metrics for monitoring."""
    return METRICS.copy()


def reset_metrics():
    """Reset metrics (useful for testing)."""
    global METRICS
    METRICS = {
        "posts_sent_group1": 0,
        "posts_sent_group2": 0,
        "posts_failed_group2": 0,
        "posts_deduped_group2": 0,
    }


def clear_dedup_cache():
    """Clear deduplication cache (useful for testing)."""
    global _sent_posts_cache
    _sent_posts_cache.clear()
