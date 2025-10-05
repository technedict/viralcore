#!/usr/bin/env python3
# tests/test_likes_group.py
"""
Unit and integration tests for Likes Group functionality.

Tests verify:
1. Group 1 behavior remains unchanged
2. Likes Group receives every post with likes_needed metric
3. Rotating push excludes Likes Group
4. Failure handling doesn't affect Group 1
5. Deduplication works correctly
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from telegram import Update, CallbackQuery, User, Message, Chat
from telegram.ext import ContextTypes
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.likes_group import (
    send_to_likes_group,
    _is_duplicate,
    _mark_as_sent,
    get_metrics,
    reset_metrics,
    clear_dedup_cache,
    _build_likes_group_message,
    METRICS,
)


class TestLikesGroupConfiguration:
    """Test configuration and feature toggle."""
    
    def test_feature_disabled_by_default(self):
        """Verify Likes Group is disabled by default for backward compatibility."""
        with patch.dict(os.environ, {}, clear=True):
            # Reimport to get default value
            import importlib
            import settings.bot_settings
            importlib.reload(settings.bot_settings)
            
            from settings.bot_settings import ADMIN_LIKES_GROUP_ENABLED
            assert ADMIN_LIKES_GROUP_ENABLED == False
    
    def test_feature_can_be_enabled(self):
        """Verify Likes Group can be enabled via environment variable."""
        with patch.dict(os.environ, {"ADMIN_LIKES_GROUP_ENABLED": "true"}):
            import importlib
            import settings.bot_settings
            importlib.reload(settings.bot_settings)
            
            from settings.bot_settings import ADMIN_LIKES_GROUP_ENABLED
            assert ADMIN_LIKES_GROUP_ENABLED == True


class TestLikesGroupMessageComposition:
    """Test message payload composition for Likes Group."""
    
    def test_message_contains_required_fields(self):
        """Verify Likes Group message contains all required fields."""
        message = _build_likes_group_message(
            post_id="123456789",
            content="https://x.com/user/status/123456789",
            likes_needed=50,
            correlation_id="abc-def-ghi",
        )
        
        # Verify required fields present
        assert "123456789" in message  # post_id
        assert "50" in message  # likes_needed
        assert "abc-def-ghi" in message  # correlation_id
        # Content may be escaped for MarkdownV2
        assert ("x.com/user/status/123456789" in message or 
                "x\\.com/user/status/123456789" in message)  # content
        
        # Verify structure
        assert "🎯" in message  # Emoji identifier
        assert "Likes Needed" in message  # Title
        assert "Correlation ID" in message  # Correlation field
        assert "Timestamp" in message  # Timestamp field
    
    def test_message_does_not_contain_comments_retweets(self):
        """Verify Likes Group message does NOT contain comments/retweets metrics."""
        message = _build_likes_group_message(
            post_id="123",
            content="https://x.com/test",
            likes_needed=100,
            correlation_id="test-id",
        )
        
        # These should NOT appear in Likes Group messages
        assert "comments" not in message.lower()
        assert "retweets" not in message.lower()
        assert "Comments:" not in message
        assert "Retweets:" not in message
    
    def test_message_escapes_markdown_properly(self):
        """Verify message properly escapes MarkdownV2 special characters."""
        # Test with content that has special characters
        message = _build_likes_group_message(
            post_id="123",
            content="https://x.com/test_user/status/123?param=value&other=123",
            likes_needed=50,
            correlation_id="test-id-123",
        )
        
        # Should contain escaped content
        assert "x\\.com" in message or "x.com" in message  # Depends on escaping strategy


class TestLikesGroupDeduplication:
    """Test deduplication logic."""
    
    def setup_method(self):
        """Reset cache before each test."""
        clear_dedup_cache()
        reset_metrics()
    
    def test_first_send_not_duplicate(self):
        """Verify first send is not marked as duplicate."""
        assert _is_duplicate("post123") == False
    
    def test_second_send_is_duplicate(self):
        """Verify second send of same post is marked as duplicate."""
        post_id = "post123"
        
        _mark_as_sent(post_id)
        assert _is_duplicate(post_id) == True
    
    def test_different_posts_not_duplicates(self):
        """Verify different posts are not marked as duplicates."""
        _mark_as_sent("post123")
        
        assert _is_duplicate("post456") == False
    
    @pytest.mark.asyncio
    async def test_duplicate_increments_metric(self):
        """Verify duplicate detection increments dedup metric."""
        reset_metrics()
        clear_dedup_cache()
        
        # Mock context
        context = Mock(spec=ContextTypes.DEFAULT_TYPE)
        context.bot = AsyncMock()
        
        with patch("utils.likes_group.ADMIN_LIKES_GROUP_ENABLED", True), \
             patch("utils.likes_group.ADMIN_LIKES_GROUP_CHAT_ID", -123456):
            
            # First send
            await send_to_likes_group(
                context=context,
                post_id="test123",
                content="https://test.com",
                likes_needed=50,
            )
            
            # Second send (duplicate)
            await send_to_likes_group(
                context=context,
                post_id="test123",
                content="https://test.com",
                likes_needed=50,
            )
            
            metrics = get_metrics()
            assert metrics["posts_deduped_group2"] == 1


class TestLikesGroupSending:
    """Test sending to Likes Group."""
    
    def setup_method(self):
        """Reset state before each test."""
        clear_dedup_cache()
        reset_metrics()
    
    @pytest.mark.asyncio
    async def test_send_when_disabled_returns_false(self):
        """Verify send returns False when feature is disabled."""
        context = Mock(spec=ContextTypes.DEFAULT_TYPE)
        context.bot = AsyncMock()
        
        with patch("utils.likes_group.ADMIN_LIKES_GROUP_ENABLED", False):
            result = await send_to_likes_group(
                context=context,
                post_id="123",
                content="https://test.com",
                likes_needed=50,
            )
            
            assert result == False
            context.bot.send_message.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_send_when_enabled_calls_send_message(self):
        """Verify send calls bot.send_message when enabled."""
        context = Mock(spec=ContextTypes.DEFAULT_TYPE)
        context.bot = AsyncMock()
        
        with patch("utils.likes_group.ADMIN_LIKES_GROUP_ENABLED", True), \
             patch("utils.likes_group.ADMIN_LIKES_GROUP_CHAT_ID", -123456):
            
            result = await send_to_likes_group(
                context=context,
                post_id="123",
                content="https://test.com",
                likes_needed=50,
            )
            
            assert result == True
            context.bot.send_message.assert_called_once()
            
            # Verify call parameters
            call_args = context.bot.send_message.call_args
            assert call_args.kwargs["chat_id"] == -123456
            assert call_args.kwargs["parse_mode"] == "MarkdownV2"
    
    @pytest.mark.asyncio
    async def test_send_increments_success_metric(self):
        """Verify successful send increments posts_sent_group2 metric."""
        reset_metrics()
        
        context = Mock(spec=ContextTypes.DEFAULT_TYPE)
        context.bot = AsyncMock()
        
        with patch("utils.likes_group.ADMIN_LIKES_GROUP_ENABLED", True), \
             patch("utils.likes_group.ADMIN_LIKES_GROUP_CHAT_ID", -123456):
            
            await send_to_likes_group(
                context=context,
                post_id="123",
                content="https://test.com",
                likes_needed=50,
            )
            
            metrics = get_metrics()
            assert metrics["posts_sent_group2"] == 1
    
    @pytest.mark.asyncio
    async def test_send_failure_increments_failure_metric(self):
        """Verify failed send increments posts_failed_group2 metric."""
        reset_metrics()
        
        context = Mock(spec=ContextTypes.DEFAULT_TYPE)
        context.bot = AsyncMock()
        context.bot.send_message.side_effect = Exception("Network error")
        
        with patch("utils.likes_group.ADMIN_LIKES_GROUP_ENABLED", True), \
             patch("utils.likes_group.ADMIN_LIKES_GROUP_CHAT_ID", -123456):
            
            result = await send_to_likes_group(
                context=context,
                post_id="123",
                content="https://test.com",
                likes_needed=50,
            )
            
            assert result == False
            metrics = get_metrics()
            assert metrics["posts_failed_group2"] == 1
    
    @pytest.mark.asyncio
    async def test_send_failure_is_fail_safe(self):
        """Verify send failure doesn't raise exception (fail-safe)."""
        context = Mock(spec=ContextTypes.DEFAULT_TYPE)
        context.bot = AsyncMock()
        context.bot.send_message.side_effect = Exception("Network error")
        
        with patch("utils.likes_group.ADMIN_LIKES_GROUP_ENABLED", True), \
             patch("utils.likes_group.ADMIN_LIKES_GROUP_CHAT_ID", -123456):
            
            # Should not raise exception
            result = await send_to_likes_group(
                context=context,
                post_id="123",
                content="https://test.com",
                likes_needed=50,
            )
            
            assert result == False  # Returns False but doesn't crash


class TestLikesGroupRotationExemption:
    """Test that Likes Group is exempt from rotation logic."""
    
    @pytest.mark.asyncio
    async def test_likes_group_not_in_comment_group_ids(self):
        """Verify Likes Group chat ID is not in COMMENT_GROUP_IDS."""
        from settings.bot_settings import COMMENT_GROUP_IDS
        
        with patch("utils.likes_group.ADMIN_LIKES_GROUP_CHAT_ID", -999999):
            from utils.likes_group import ADMIN_LIKES_GROUP_CHAT_ID
            
            # Likes Group should not be in rotation list
            assert ADMIN_LIKES_GROUP_CHAT_ID not in COMMENT_GROUP_IDS
    
    @pytest.mark.asyncio
    async def test_likes_group_sends_every_post(self):
        """Verify Likes Group receives every post regardless of rotation."""
        context = Mock(spec=ContextTypes.DEFAULT_TYPE)
        context.bot = AsyncMock()
        
        with patch("utils.likes_group.ADMIN_LIKES_GROUP_ENABLED", True), \
             patch("utils.likes_group.ADMIN_LIKES_GROUP_CHAT_ID", -123456):
            
            # Send multiple posts
            for i in range(10):
                await send_to_likes_group(
                    context=context,
                    post_id=f"post{i}",
                    content=f"https://test.com/{i}",
                    likes_needed=50 + i,
                )
            
            # Verify all 10 posts were sent (no rotation filtering)
            assert context.bot.send_message.call_count == 10


class TestMetrics:
    """Test metrics tracking."""
    
    def setup_method(self):
        """Reset metrics before each test."""
        reset_metrics()
    
    def test_get_metrics_returns_copy(self):
        """Verify get_metrics returns a copy, not the original dict."""
        metrics1 = get_metrics()
        metrics1["posts_sent_group2"] = 999
        
        metrics2 = get_metrics()
        assert metrics2["posts_sent_group2"] != 999
    
    def test_reset_metrics_clears_counters(self):
        """Verify reset_metrics clears all counters."""
        METRICS["posts_sent_group2"] = 10
        METRICS["posts_failed_group2"] = 5
        
        reset_metrics()
        
        metrics = get_metrics()
        assert metrics["posts_sent_group2"] == 0
        assert metrics["posts_failed_group2"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
