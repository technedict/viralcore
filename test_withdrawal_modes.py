#!/usr/bin/env python3
# test_withdrawal_modes.py
# Test script for new withdrawal modes functionality

import sys
import logging
from utils.withdrawal_settings import init_withdrawal_settings_table, get_withdrawal_mode, set_withdrawal_mode, WithdrawalMode
from utils.withdrawal_service import get_withdrawal_service
from utils.db_utils import init_main_db, create_user

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_withdrawal_settings():
    """Test withdrawal settings functionality."""
    print("=== Testing Withdrawal Settings ===")
    
    # Initialize tables
    init_main_db()
    init_withdrawal_settings_table()
    
    # Test default mode
    default_mode = get_withdrawal_mode()
    print(f"Default withdrawal mode: {default_mode.value}")
    assert default_mode == WithdrawalMode.AUTOMATIC, f"Expected AUTOMATIC, got {default_mode}"
    
    # Test setting manual mode
    success = set_withdrawal_mode(WithdrawalMode.MANUAL, admin_id=123)
    assert success, "Failed to set manual mode"
    
    # Test reading manual mode
    current_mode = get_withdrawal_mode()
    print(f"Current withdrawal mode: {current_mode.value}")
    assert current_mode == WithdrawalMode.MANUAL, f"Expected MANUAL, got {current_mode}"
    
    # Test setting back to automatic
    success = set_withdrawal_mode(WithdrawalMode.AUTOMATIC, admin_id=123)
    assert success, "Failed to set automatic mode"
    
    current_mode = get_withdrawal_mode()
    print(f"Final withdrawal mode: {current_mode.value}")
    assert current_mode == WithdrawalMode.AUTOMATIC, f"Expected AUTOMATIC, got {current_mode}"
    
    print("✅ Withdrawal settings tests passed!")

def test_user_creation():
    """Test user creation functionality."""
    print("\n=== Testing User Creation ===")
    
    # Initialize main database
    init_main_db()
    
    # Create a test user
    test_user_id = 999999
    test_username = "test_user"
    
    create_user(test_user_id, test_username)
    
    # Verify user was created with correct defaults
    from utils.db_utils import get_user
    user = get_user(test_user_id)
    
    assert user is not None, "User was not created"
    assert user[0] == test_user_id, f"User ID mismatch: {user[0]} != {test_user_id}"
    assert user[1] == test_username, f"Username mismatch: {user[1]} != {test_username}"
    assert user[4] == 0, f"User should not be admin by default: {user[4]}"  # is_admin should be 0
    
    print(f"✅ User created successfully: ID={user[0]}, username={user[1]}, is_admin={user[4]}")

def test_withdrawal_service():
    """Test withdrawal service functionality."""
    print("\n=== Testing Withdrawal Service ===")
    
    service = get_withdrawal_service()
    
    # Test getting pending withdrawals
    pending = service.get_pending_withdrawals()
    print(f"Found {len(pending)} pending withdrawals")
    
    # Test getting pending manual withdrawals
    pending_manual = service.get_pending_manual_withdrawals()
    print(f"Found {len(pending_manual)} pending manual withdrawals")
    
    print("✅ Withdrawal service tests passed!")

if __name__ == "__main__":
    try:
        test_withdrawal_settings()
        test_user_creation()
        test_withdrawal_service()
        print("\n🎉 All tests passed!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)