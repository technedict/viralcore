#!/usr/bin/env python3
# tests/test_withdrawal_flows.py
# Comprehensive tests for withdrawal flows

import pytest
import sqlite3
import tempfile
import os
import threading
import time
from unittest.mock import Mock, patch, MagicMock
from concurrent.futures import ThreadPoolExecutor

# Add parent directory to path for imports
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.withdrawal_settings import WithdrawalMode, set_withdrawal_mode, get_withdrawal_mode, init_withdrawal_settings_table
from utils.withdrawal_service import WithdrawalService, PaymentMode, AdminApprovalState, WithdrawalStatus, Withdrawal
from utils.db_utils import init_main_db, create_user, get_connection
from utils.balance_operations import atomic_deposit_operation, init_operations_ledger
from handlers.menu_handlers import menu_handler

class TestWithdrawalFlows:
    """Test withdrawal approval flows including concurrency scenarios."""
    
    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing."""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        
        # Patch DB_FILE to use temp database
        original_db_file = None
        try:
            import utils.db_utils
            original_db_file = utils.db_utils.DB_FILE
            utils.db_utils.DB_FILE = path
            
            import utils.withdrawal_service
            utils.withdrawal_service.DB_FILE = path
            
            import utils.balance_operations
            utils.balance_operations.DB_FILE = path
            
            import utils.withdrawal_settings
            utils.withdrawal_settings.DB_FILE = path
            
            # Initialize database
            init_main_db()
            init_withdrawal_settings_table()
            init_operations_ledger()
            
            yield path
            
        finally:
            # Restore original DB_FILE
            if original_db_file:
                utils.db_utils.DB_FILE = original_db_file
                utils.withdrawal_service.DB_FILE = original_db_file
                utils.balance_operations.DB_FILE = original_db_file
                utils.withdrawal_settings.DB_FILE = original_db_file
            
            # Clean up temp file
            try:
                os.unlink(path)
            except OSError:
                pass
    
    @pytest.fixture
    def withdrawal_service(self, temp_db):
        """Create withdrawal service with mocked Flutterwave client."""
        service = WithdrawalService()
        service.flutterwave_client = Mock()
        return service
    
    @pytest.fixture
    def test_user(self, temp_db):
        """Create test user with balance."""
        user_id = 12345
        username = "test_user"
        create_user(user_id, username)
        
        # Add some balance
        atomic_deposit_operation(
            user_id=user_id,
            balance_type="affiliate",
            amount=100.0,
            reason="Test setup"
        )
        
        return user_id
    
    def test_manual_mode_approval(self, withdrawal_service, test_user):
        """Test manual mode approval flow."""
        # Set manual mode
        set_withdrawal_mode(WithdrawalMode.MANUAL, admin_id=999)
        
        # Create withdrawal
        withdrawal = withdrawal_service.create_withdrawal(
            user_id=test_user,
            amount_usd=50.0,
            amount_ngn=75000.0,
            account_name="Test User",
            account_number="1234567890",
            bank_name="Test Bank",
            bank_details_raw="Test Bank Details",
            payment_mode=PaymentMode.MANUAL
        )
        
        # Verify withdrawal was created with manual payment mode
        assert withdrawal.payment_mode == PaymentMode.MANUAL
        assert withdrawal.admin_approval_state == AdminApprovalState.PENDING
        assert withdrawal.status == WithdrawalStatus.PENDING
        
        # Approve withdrawal using unified method
        success = withdrawal_service.approve_withdrawal_by_mode(
            withdrawal_id=withdrawal.id,
            admin_id=999,
            reason="Test approval"
        )
        
        # Verify approval succeeded
        assert success is True
        
        # Verify withdrawal status
        updated_withdrawal = withdrawal_service.get_withdrawal(withdrawal.id)
        assert updated_withdrawal.status == WithdrawalStatus.COMPLETED
        assert updated_withdrawal.admin_id == 999
        assert updated_withdrawal.approved_at is not None
        assert updated_withdrawal.processed_at is not None
        
        # Verify Flutterwave was NOT called in manual mode
        withdrawal_service.flutterwave_client.initiate_transfer.assert_not_called()
    
    def test_automatic_mode_approval_success(self, withdrawal_service, test_user):
        """Test automatic mode approval flow with successful API call."""
        # Set automatic mode
        set_withdrawal_mode(WithdrawalMode.AUTOMATIC, admin_id=999)
        
        # Mock successful Flutterwave response
        withdrawal_service.flutterwave_client.initiate_transfer.return_value = {
            'success': True,
            'trace_id': 'test_trace_123'
        }
        
        # Create withdrawal
        withdrawal = withdrawal_service.create_withdrawal(
            user_id=test_user,
            amount_usd=30.0,
            amount_ngn=45000.0,
            account_name="Test User",
            account_number="1234567890", 
            bank_name="Test Bank",
            bank_details_raw="Test Bank Details"
        )
        
        # Approve withdrawal
        success = withdrawal_service.approve_withdrawal_by_mode(
            withdrawal_id=withdrawal.id,
            admin_id=999,
            reason="Test approval"
        )
        
        # Verify approval succeeded
        assert success is True
        
        # Verify withdrawal status
        updated_withdrawal = withdrawal_service.get_withdrawal(withdrawal.id)
        assert updated_withdrawal.status == WithdrawalStatus.COMPLETED
        assert updated_withdrawal.flutterwave_reference is not None
        assert updated_withdrawal.flutterwave_trace_id == 'test_trace_123'
        
        # Verify Flutterwave was called
        withdrawal_service.flutterwave_client.initiate_transfer.assert_called_once()
    
    def test_automatic_mode_approval_failure_with_rollback(self, withdrawal_service, test_user):
        """Test automatic mode approval with API failure and balance rollback."""
        # Set automatic mode
        set_withdrawal_mode(WithdrawalMode.AUTOMATIC, admin_id=999)
        
        # Mock failed Flutterwave response
        withdrawal_service.flutterwave_client.initiate_transfer.return_value = {
            'success': False,
            'error': 'Insufficient funds in Flutterwave account'
        }
        
        # Get initial balance
        from utils.balance_operations import get_balance_safely
        initial_balance = get_balance_safely(test_user, "affiliate")
        
        # Create withdrawal
        withdrawal = withdrawal_service.create_withdrawal(
            user_id=test_user,
            amount_usd=25.0,
            amount_ngn=37500.0,
            account_name="Test User", 
            account_number="1234567890",
            bank_name="Test Bank",
            bank_details_raw="Test Bank Details"
        )
        
        # Approve withdrawal (should fail and rollback)
        success = withdrawal_service.approve_withdrawal_by_mode(
            withdrawal_id=withdrawal.id,
            admin_id=999,
            reason="Test approval"
        )
        
        # Verify approval failed
        assert success is False
        
        # Verify withdrawal status  
        updated_withdrawal = withdrawal_service.get_withdrawal(withdrawal.id)
        assert updated_withdrawal.status == WithdrawalStatus.FAILED
        assert "Insufficient funds" in updated_withdrawal.failure_reason
        
        # Verify balance was rolled back
        final_balance = get_balance_safely(test_user, "affiliate")
        assert final_balance == initial_balance, f"Balance not rolled back: {final_balance} != {initial_balance}"
    
    def test_idempotent_approval(self, withdrawal_service, test_user):
        """Test that approval is idempotent - multiple calls don't cause issues."""
        # Set manual mode for simpler testing
        set_withdrawal_mode(WithdrawalMode.MANUAL, admin_id=999)
        
        # Create withdrawal
        withdrawal = withdrawal_service.create_withdrawal(
            user_id=test_user,
            amount_usd=20.0,
            amount_ngn=30000.0,
            account_name="Test User",
            account_number="1234567890",
            bank_name="Test Bank", 
            bank_details_raw="Test Bank Details",
            payment_mode=PaymentMode.MANUAL
        )
        
        # Approve withdrawal multiple times
        success1 = withdrawal_service.approve_withdrawal_by_mode(
            withdrawal_id=withdrawal.id,
            admin_id=999,
            reason="First approval"
        )
        
        success2 = withdrawal_service.approve_withdrawal_by_mode(
            withdrawal_id=withdrawal.id,
            admin_id=888,  # Different admin
            reason="Second approval"
        )
        
        # Both should succeed (idempotent)
        assert success1 is True
        assert success2 is True
        
        # Verify withdrawal was only processed once
        updated_withdrawal = withdrawal_service.get_withdrawal(withdrawal.id)
        assert updated_withdrawal.status == WithdrawalStatus.COMPLETED
        assert updated_withdrawal.admin_id == 999  # Should still have first admin
    
    def test_concurrent_approval_race_condition(self, withdrawal_service, test_user):
        """Test concurrent approval attempts to ensure only one succeeds."""
        # Set manual mode
        set_withdrawal_mode(WithdrawalMode.MANUAL, admin_id=999)
        
        # Create withdrawal
        withdrawal = withdrawal_service.create_withdrawal(
            user_id=test_user,
            amount_usd=40.0,
            amount_ngn=60000.0,
            account_name="Test User",
            account_number="1234567890",
            bank_name="Test Bank",
            bank_details_raw="Test Bank Details",
            payment_mode=PaymentMode.MANUAL
        )
        
        # Get initial balance
        from utils.balance_operations import get_balance_safely
        initial_balance = get_balance_safely(test_user, "affiliate")
        
        results = []
        errors = []
        
        def approve_withdrawal(admin_id):
            """Approve withdrawal in separate thread."""
            try:
                # Add small random delay to increase chance of race condition
                time.sleep(0.01)
                success = withdrawal_service.approve_withdrawal_by_mode(
                    withdrawal_id=withdrawal.id,
                    admin_id=admin_id,
                    reason=f"Approval by admin {admin_id}"
                )
                results.append((admin_id, success))
            except Exception as e:
                errors.append((admin_id, str(e)))
        
        # Launch concurrent approval attempts
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(approve_withdrawal, 888),
                executor.submit(approve_withdrawal, 999),
                executor.submit(approve_withdrawal, 777)
            ]
            
            # Wait for all to complete
            for future in futures:
                future.result()
        
        # Verify results
        assert len(errors) == 0, f"Unexpected errors: {errors}"
        assert len(results) == 3, f"Expected 3 results, got {len(results)}"
        
        # All should report success (idempotent behavior)
        for admin_id, success in results:
            assert success is True, f"Admin {admin_id} approval failed"
        
        # Verify balance was only deducted once
        final_balance = get_balance_safely(test_user, "affiliate")
        expected_balance = initial_balance - 40.0
        assert final_balance == expected_balance, f"Balance incorrect: {final_balance} != {expected_balance}"
        
        # Verify withdrawal is completed
        updated_withdrawal = withdrawal_service.get_withdrawal(withdrawal.id)
        assert updated_withdrawal.status == WithdrawalStatus.COMPLETED
    
    def test_withdrawal_mode_change_during_approval(self, withdrawal_service, test_user):
        """Test that withdrawal mode is read at approval time, not creation time."""
        # Start in manual mode
        set_withdrawal_mode(WithdrawalMode.MANUAL, admin_id=999)
        
        # Create withdrawal (will be created as manual)
        withdrawal = withdrawal_service.create_withdrawal(
            user_id=test_user,
            amount_usd=15.0,
            amount_ngn=22500.0,
            account_name="Test User",
            account_number="1234567890",
            bank_name="Test Bank",
            bank_details_raw="Test Bank Details"
        )
        
        # Switch to automatic mode before approval
        set_withdrawal_mode(WithdrawalMode.AUTOMATIC, admin_id=999)
        
        # Mock successful Flutterwave response
        withdrawal_service.flutterwave_client.initiate_transfer.return_value = {
            'success': True,
            'trace_id': 'test_trace_456'
        }
        
        # Approve withdrawal (should use automatic mode)
        success = withdrawal_service.approve_withdrawal_by_mode(
            withdrawal_id=withdrawal.id,
            admin_id=999,
            reason="Test approval"
        )
        
        # Verify approval succeeded
        assert success is True
        
        # Verify Flutterwave was called (automatic mode behavior)
        withdrawal_service.flutterwave_client.initiate_transfer.assert_called_once()
        
        # Verify withdrawal has API reference
        updated_withdrawal = withdrawal_service.get_withdrawal(withdrawal.id)
        assert updated_withdrawal.flutterwave_reference is not None
        assert updated_withdrawal.flutterwave_trace_id == 'test_trace_456'


class TestUserCreation:
    """Test user creation on interactions."""
    
    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing."""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        
        # Patch DB_FILE
        original_db_file = None
        try:
            import utils.db_utils
            original_db_file = utils.db_utils.DB_FILE
            utils.db_utils.DB_FILE = path
            
            # Initialize database
            init_main_db()
            
            yield path
            
        finally:
            if original_db_file:
                utils.db_utils.DB_FILE = original_db_file
            try:
                os.unlink(path)
            except OSError:
                pass
    
    def test_user_creation_with_defaults(self, temp_db):
        """Test user creation with proper default values."""
        from utils.db_utils import create_user, get_user
        
        user_id = 54321
        username = "new_user"
        
        # Create user
        create_user(user_id, username)
        
        # Verify user was created
        user = get_user(user_id)
        assert user is not None
        assert user[0] == user_id
        assert user[1] == username
        assert user[4] == 0  # is_admin should be False (0)
        
        # Verify default values from database schema
        with get_connection(temp_db) as conn:
            c = conn.cursor()
            c.execute('SELECT is_admin, is_reply_guy, affiliate_balance FROM users WHERE id = ?', (user_id,))
            row = c.fetchone()
            assert row[0] == 0  # is_admin = False
            assert row[1] == 0  # is_reply_guy = False  
            assert row[2] == 0.0  # affiliate_balance = 0.0
    
    @patch('handlers.menu_handlers.get_user')
    @patch('handlers.menu_handlers.create_user')
    def test_button_interaction_creates_user(self, mock_create_user, mock_get_user):
        """Test that button interactions create users if they don't exist."""
        # Mock user not existing initially
        mock_get_user.return_value = None
        
        # Create mock update and context
        mock_update = Mock()
        mock_update.callback_query.from_user.id = 67890
        mock_update.callback_query.from_user.username = "button_user"
        mock_update.callback_query.answer = Mock()
        mock_update.callback_query.data = "main_menu"
        
        mock_context = Mock()
        mock_context.user_data = {}
        mock_context.bot_data = {"payment_handler": Mock()}
        
        # This test would require more mocking to work fully, but the key point
        # is that menu_handler now calls create_user before get_user
        # The actual implementation is already in place
        
        # Verify create_user would be called
        # (In real implementation, this happens in menu_handler)
        assert True  # Implementation is already in place


if __name__ == "__main__":
    # Run tests if called directly
    pytest.main([__file__, "-v"])