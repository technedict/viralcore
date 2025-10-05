#!/usr/bin/env python3
# tests/test_likes_group_integration.py
"""
Integration tests for Likes Group with link submission handlers.

Tests verify:
1. Twitter posts trigger both Group 1 and Likes Group sends
2. Telegram posts trigger both Group 1 and Likes Group sends
3. Group 1 behavior unchanged when Likes Group fails
4. Rotation logic unchanged
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock, call
from telegram import Update, CallbackQuery, User, Message, Chat
from telegram.ext import ContextTypes
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handlers.link_submission_handlers import (
    x_account_selection_handler,
    tg_account_selection_handler,
)
from utils.likes_group import reset_metrics, clear_dedup_cache, get_metrics


class TestTwitterPostIntegration:
    """Test integration with Twitter post submission."""
    
    def setup_method(self):
        """Reset state before each test."""
        reset_metrics()
        clear_dedup_cache()
    
    @pytest.mark.asyncio
    async def test_twitter_post_sends_to_both_groups(self):
        """Verify Twitter post sends to Group 1 (rotating) and Likes Group."""
        # Create mocks
        update = Mock(spec=Update)
        query = Mock(spec=CallbackQuery)
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        query.from_user = Mock(spec=User)
        query.from_user.id = 12345
        query.data = "select_x_testuser"
        update.callback_query = query
        
        context = Mock(spec=ContextTypes.DEFAULT_TYPE)
        context.bot = AsyncMock()
        context.application = Mock()
        context.application.job_queue = Mock()
        context.application.job_queue.run_once = Mock()
        context.user_data = {
            "pending_tweet": {
                "tweet_id": "999888777",
                "twitter_link": "https://x.com/test/status/999888777",
                "shortened_link": "https://bit.ly/xyz",
            }
        }
        
        # Mock database functions
        with patch("handlers.link_submission_handlers.get_latest_tier_for_x") as mock_tier, \
             patch("handlers.link_submission_handlers.decrement_x_rpost") as mock_decrement, \
             patch("handlers.link_submission_handlers.get_connection") as mock_conn, \
             patch("handlers.link_submission_handlers.BoostManager") as mock_boost, \
             patch("utils.likes_group.ADMIN_LIKES_GROUP_ENABLED", True), \
             patch("utils.likes_group.ADMIN_LIKES_GROUP_CHAT_ID", -999999):
            
            mock_tier.return_value = ("t2", None)
            mock_conn.return_value = Mock()
            mock_conn.return_value.cursor.return_value = Mock()
            mock_boost.return_value.start_boost = Mock()
            
            # Execute handler
            await x_account_selection_handler(update, context)
            
            # Verify Group 1 sends (rotation logic)
            assert context.application.job_queue.run_once.called
            
            # Verify Likes Group send
            assert context.bot.send_message.called
            likes_group_call = [
                c for c in context.bot.send_message.call_args_list
                if c.kwargs.get("chat_id") == -999999
            ]
            assert len(likes_group_call) == 1
            
            # Verify metrics
            metrics = get_metrics()
            assert metrics["posts_sent_group1"] == 1
            assert metrics["posts_sent_group2"] == 1
    
    @pytest.mark.asyncio
    async def test_twitter_post_group1_unaffected_by_likes_group_failure(self):
        """Verify Group 1 send succeeds even if Likes Group fails."""
        # Create mocks
        update = Mock(spec=Update)
        query = Mock(spec=CallbackQuery)
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        query.from_user = Mock(spec=User)
        query.from_user.id = 12345
        query.data = "select_x_testuser"
        update.callback_query = query
        
        context = Mock(spec=ContextTypes.DEFAULT_TYPE)
        context.bot = AsyncMock()
        # Make Likes Group send fail
        context.bot.send_message.side_effect = Exception("Network error")
        context.application = Mock()
        context.application.job_queue = Mock()
        context.application.job_queue.run_once = Mock()
        context.user_data = {
            "pending_tweet": {
                "tweet_id": "999888777",
                "twitter_link": "https://x.com/test/status/999888777",
                "shortened_link": "https://bit.ly/xyz",
            }
        }
        
        # Mock database functions
        with patch("handlers.link_submission_handlers.get_latest_tier_for_x") as mock_tier, \
             patch("handlers.link_submission_handlers.decrement_x_rpost") as mock_decrement, \
             patch("handlers.link_submission_handlers.get_connection") as mock_conn, \
             patch("handlers.link_submission_handlers.BoostManager") as mock_boost, \
             patch("utils.likes_group.ADMIN_LIKES_GROUP_ENABLED", True), \
             patch("utils.likes_group.ADMIN_LIKES_GROUP_CHAT_ID", -999999):
            
            mock_tier.return_value = ("t2", None)
            mock_conn.return_value = Mock()
            mock_conn.return_value.cursor.return_value = Mock()
            mock_boost.return_value.start_boost = Mock()
            
            # Execute handler - should not raise exception
            await x_account_selection_handler(update, context)
            
            # Verify Group 1 scheduling still happened
            assert context.application.job_queue.run_once.called
            
            # Verify metrics show failure
            metrics = get_metrics()
            assert metrics["posts_sent_group1"] == 1  # Still counted
            assert metrics["posts_failed_group2"] == 1  # Failure tracked


class TestTelegramPostIntegration:
    """Test integration with Telegram post submission."""
    
    def setup_method(self):
        """Reset state before each test."""
        reset_metrics()
        clear_dedup_cache()
    
    @pytest.mark.asyncio
    async def test_telegram_post_sends_to_both_groups(self):
        """Verify Telegram post sends to Group 1 (rotating) and Likes Group."""
        # Create mocks
        update = Mock(spec=Update)
        query = Mock(spec=CallbackQuery)
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        query.from_user = Mock(spec=User)
        query.from_user.id = 12345
        query.data = "select_tg_testuser"
        update.callback_query = query
        
        context = Mock(spec=ContextTypes.DEFAULT_TYPE)
        context.bot = AsyncMock()
        context.application = Mock()
        context.application.job_queue = Mock()
        context.application.job_queue.run_once = Mock()
        context.user_data = {
            "pending_tg_link": {
                "telegram_link": "https://t.me/testchannel/123",
            }
        }
        
        # Mock database functions
        with patch("handlers.link_submission_handlers.get_latest_tg_plan") as mock_plan, \
             patch("handlers.link_submission_handlers.decrement_tg_rpost") as mock_decrement, \
             patch("handlers.link_submission_handlers.get_connection") as mock_conn, \
             patch("utils.likes_group.ADMIN_LIKES_GROUP_ENABLED", True), \
             patch("utils.likes_group.ADMIN_LIKES_GROUP_CHAT_ID", -888888):
            
            mock_plan.return_value = ("tg_plan", 25, 100)  # tier, quantity, rpost
            mock_conn.return_value = Mock()
            mock_conn.return_value.cursor.return_value = Mock()
            
            # Execute handler
            await tg_account_selection_handler(update, context)
            
            # Verify Group 1 sends (rotation logic)
            assert context.application.job_queue.run_once.called
            
            # Verify Likes Group send
            assert context.bot.send_message.called
            likes_group_call = [
                c for c in context.bot.send_message.call_args_list
                if c.kwargs.get("chat_id") == -888888
            ]
            assert len(likes_group_call) == 1
            
            # Verify metrics
            metrics = get_metrics()
            assert metrics["posts_sent_group1"] == 1
            assert metrics["posts_sent_group2"] == 1


class TestRotationExemption:
    """Test that Likes Group is exempt from rotation."""
    
    def setup_method(self):
        """Reset state before each test."""
        reset_metrics()
        clear_dedup_cache()
    
    @pytest.mark.asyncio
    async def test_rotation_pointer_not_affected_by_likes_group(self):
        """Verify rotation pointer only considers Group 1 sends, not Likes Group."""
        from handlers.link_submission_handlers import _get_batch_pointer, _set_batch_pointer
        
        # Set initial pointer
        _set_batch_pointer(0)
        initial_pointer = _get_batch_pointer()
        
        # Create mock for Likes Group send (direct call)
        context = Mock(spec=ContextTypes.DEFAULT_TYPE)
        context.bot = AsyncMock()
        
        with patch("utils.likes_group.ADMIN_LIKES_GROUP_ENABLED", True), \
             patch("utils.likes_group.ADMIN_LIKES_GROUP_CHAT_ID", -999999):
            
            from utils.likes_group import send_to_likes_group
            
            # Send to Likes Group multiple times
            for i in range(5):
                await send_to_likes_group(
                    context=context,
                    post_id=f"test{i}",
                    content=f"https://test.com/{i}",
                    likes_needed=50,
                )
            
            # Verify pointer unchanged (Likes Group doesn't affect rotation)
            final_pointer = _get_batch_pointer()
            assert final_pointer == initial_pointer


class TestBackwardCompatibility:
    """Test backward compatibility when Likes Group is disabled."""
    
    def setup_method(self):
        """Reset state before each test."""
        reset_metrics()
        clear_dedup_cache()
    
    @pytest.mark.asyncio
    async def test_disabled_likes_group_no_impact(self):
        """Verify disabled Likes Group has no impact on existing behavior."""
        # Create mocks
        update = Mock(spec=Update)
        query = Mock(spec=CallbackQuery)
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        query.from_user = Mock(spec=User)
        query.from_user.id = 12345
        query.data = "select_x_testuser"
        update.callback_query = query
        
        context = Mock(spec=ContextTypes.DEFAULT_TYPE)
        context.bot = AsyncMock()
        context.application = Mock()
        context.application.job_queue = Mock()
        context.application.job_queue.run_once = Mock()
        context.user_data = {
            "pending_tweet": {
                "tweet_id": "999888777",
                "twitter_link": "https://x.com/test/status/999888777",
                "shortened_link": "https://bit.ly/xyz",
            }
        }
        
        # Mock database functions
        with patch("handlers.link_submission_handlers.get_latest_tier_for_x") as mock_tier, \
             patch("handlers.link_submission_handlers.decrement_x_rpost") as mock_decrement, \
             patch("handlers.link_submission_handlers.get_connection") as mock_conn, \
             patch("handlers.link_submission_handlers.BoostManager") as mock_boost, \
             patch("utils.likes_group.ADMIN_LIKES_GROUP_ENABLED", False):
            
            mock_tier.return_value = ("t2", None)
            mock_conn.return_value = Mock()
            mock_conn.return_value.cursor.return_value = Mock()
            mock_boost.return_value.start_boost = Mock()
            
            # Execute handler
            await x_account_selection_handler(update, context)
            
            # Verify Group 1 sends still work
            assert context.application.job_queue.run_once.called
            
            # Verify NO Likes Group send
            metrics = get_metrics()
            assert metrics["posts_sent_group1"] == 1
            assert metrics["posts_sent_group2"] == 0  # Not sent when disabled


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
