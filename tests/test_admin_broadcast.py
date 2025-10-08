#!/usr/bin/env python3
"""
Tests for the admin broadcast functionality, particularly handling images.
"""

import sys
import os
import asyncio
from unittest.mock import Mock, AsyncMock, MagicMock, patch

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from telegram import Update, Message, User, Chat, PhotoSize
from telegram.ext import ContextTypes

# Mock the viralmonitor module before importing handlers
sys.modules['viralmonitor'] = MagicMock()
sys.modules['viralmonitor.utils'] = MagicMock()
sys.modules['viralmonitor.utils.db'] = MagicMock()


async def test_admin_broadcast_with_image():
    """Test that broadcasting with an image doesn't cause AttributeError."""
    from handlers.admin_message_handlers import admin_message_handler
    
    # Create mock objects
    mock_user = Mock(spec=User)
    mock_user.id = 12345
    mock_user.username = "testadmin"
    
    mock_chat = Mock(spec=Chat)
    mock_chat.id = 12345
    
    # Create a photo object
    mock_photo = Mock(spec=PhotoSize)
    mock_photo.file_id = "test_photo_file_id_123"
    
    # Create mock message with photo but no text
    mock_message = Mock(spec=Message)
    mock_message.text = None  # This is the key - text is None when sending image
    mock_message.caption = "Test broadcast caption"
    mock_message.photo = [mock_photo]  # Photo array
    mock_message.reply_text = AsyncMock()
    
    # Create mock update
    mock_update = Mock(spec=Update)
    mock_update.message = mock_message
    mock_update.effective_user = mock_user
    
    # Create mock context
    mock_context = Mock(spec=ContextTypes.DEFAULT_TYPE)
    mock_context.user_data = {"awaiting_broadcast": True}
    mock_context.bot = Mock()
    mock_context.bot.send_photo = AsyncMock()
    mock_context.bot.send_message = AsyncMock()
    
    # Mock the get_all_users function
    with patch('handlers.admin_message_handlers.get_all_users', return_value=[]):
        # This should NOT raise AttributeError
        try:
            await admin_message_handler(mock_update, mock_context)
            print("✓ Broadcast with image handled without AttributeError")
            return True
        except AttributeError as e:
            if "'NoneType' object has no attribute 'strip'" in str(e):
                print(f"✗ AttributeError occurred: {e}")
                raise
            else:
                # Some other AttributeError, re-raise
                raise


async def test_admin_broadcast_with_text_only():
    """Test that broadcasting with text only still works."""
    from handlers.admin_message_handlers import admin_message_handler
    
    # Create mock objects
    mock_user = Mock(spec=User)
    mock_user.id = 12345
    mock_user.username = "testadmin"
    
    mock_chat = Mock(spec=Chat)
    mock_chat.id = 12345
    
    # Create mock message with text but no photo
    mock_message = Mock(spec=Message)
    mock_message.text = "Test broadcast message"
    mock_message.caption = None
    mock_message.photo = None  # No photo
    mock_message.reply_text = AsyncMock()
    
    # Create mock update
    mock_update = Mock(spec=Update)
    mock_update.message = mock_message
    mock_update.effective_user = mock_user
    
    # Create mock context
    mock_context = Mock(spec=ContextTypes.DEFAULT_TYPE)
    mock_context.user_data = {"awaiting_broadcast": True}
    mock_context.bot = Mock()
    mock_context.bot.send_photo = AsyncMock()
    mock_context.bot.send_message = AsyncMock()
    
    # Mock the get_all_users function
    with patch('handlers.admin_message_handlers.get_all_users', return_value=[]):
        # This should work fine
        try:
            await admin_message_handler(mock_update, mock_context)
            print("✓ Broadcast with text only handled correctly")
            return True
        except Exception as e:
            print(f"✗ Unexpected error: {e}")
            raise


async def test_admin_broadcast_image_with_users():
    """Test broadcasting an image to multiple users."""
    from handlers.admin_message_handlers import admin_message_handler
    
    # Create mock objects
    mock_user = Mock(spec=User)
    mock_user.id = 12345
    mock_user.username = "testadmin"
    
    mock_chat = Mock(spec=Chat)
    mock_chat.id = 12345
    
    # Create a photo object
    mock_photo = Mock(spec=PhotoSize)
    mock_photo.file_id = "test_photo_file_id_123"
    
    # Create mock message with photo and caption
    mock_message = Mock(spec=Message)
    mock_message.text = None  # No text when sending image
    mock_message.caption = "Check out this announcement!"
    mock_message.photo = [mock_photo]
    mock_message.reply_text = AsyncMock()
    
    # Create mock update
    mock_update = Mock(spec=Update)
    mock_update.message = mock_message
    mock_update.effective_user = mock_user
    
    # Create mock context
    mock_context = Mock(spec=ContextTypes.DEFAULT_TYPE)
    mock_context.user_data = {"awaiting_broadcast": True}
    mock_context.bot = Mock()
    mock_context.bot.send_photo = AsyncMock()
    mock_context.bot.send_message = AsyncMock()
    
    # Mock get_all_users to return some test users
    test_users = [(111,), (222,), (333,)]
    
    with patch('handlers.admin_message_handlers.get_all_users', return_value=test_users):
        await admin_message_handler(mock_update, mock_context)
        
        # Verify send_photo was called for each user
        assert mock_context.bot.send_photo.call_count == 3
        print(f"✓ Broadcast image sent to {len(test_users)} users")
        
        # Verify the photo was sent with correct parameters
        for call in mock_context.bot.send_photo.call_args_list:
            args, kwargs = call
            assert 'photo' in kwargs
            assert kwargs['photo'] == "test_photo_file_id_123"
            assert 'caption' in kwargs
            assert kwargs['caption'] == "Check out this announcement!"
        
        print("✓ Photo broadcasts contained correct photo and caption")
        
        # Verify reply was sent
        assert mock_message.reply_text.called
        return True


async def test_admin_broadcast_image_without_caption():
    """Test broadcasting an image without a caption."""
    from handlers.admin_message_handlers import admin_message_handler
    
    # Create mock objects
    mock_user = Mock(spec=User)
    mock_user.id = 12345
    
    # Create a photo object
    mock_photo = Mock(spec=PhotoSize)
    mock_photo.file_id = "test_photo_file_id_456"
    
    # Create mock message with photo but NO caption
    mock_message = Mock(spec=Message)
    mock_message.text = None
    mock_message.caption = None  # No caption
    mock_message.photo = [mock_photo]
    mock_message.reply_text = AsyncMock()
    
    # Create mock update
    mock_update = Mock(spec=Update)
    mock_update.message = mock_message
    mock_update.effective_user = mock_user
    
    # Create mock context
    mock_context = Mock(spec=ContextTypes.DEFAULT_TYPE)
    mock_context.user_data = {"awaiting_broadcast": True}
    mock_context.bot = Mock()
    mock_context.bot.send_photo = AsyncMock()
    
    # Mock get_all_users to return one test user
    test_users = [(999,)]
    
    with patch('handlers.admin_message_handlers.get_all_users', return_value=test_users):
        await admin_message_handler(mock_update, mock_context)
        
        # Verify send_photo was called with empty caption
        mock_context.bot.send_photo.assert_called_once()
        args, kwargs = mock_context.bot.send_photo.call_args
        # Caption should be empty string or None (both are valid)
        assert kwargs['caption'] in ["", None]
        print("✓ Image without caption handled correctly (empty caption)")
        return True


def main():
    """Run all tests."""
    print("Starting admin broadcast tests...\n")
    
    async def run_all_tests():
        try:
            # Run tests
            await test_admin_broadcast_with_image()
            await test_admin_broadcast_with_text_only()
            await test_admin_broadcast_image_with_users()
            await test_admin_broadcast_image_without_caption()
            
            print("\n✅ All admin broadcast tests passed!")
            return 0
            
        except Exception as e:
            print(f"\n❌ Test failed: {e}")
            import traceback
            traceback.print_exc()
            return 1
    
    # Run async tests
    return asyncio.run(run_all_tests())


if __name__ == "__main__":
    exit(main())
