#!/usr/bin/env python3
"""
End-to-end test for withdrawal approval bug fix.

This test reproduces the exact bug scenario described in the problem statement:
1. User creates a withdrawal
2. Admin approves the withdrawal
3. User should be able to create a new withdrawal (not blocked by "pending" check)

Bug: After approval, the withdrawal remained listed as pending, blocking new withdrawals.
Fix: Both manual and automatic approval now correctly set admin_approval_state to APPROVED
      and status to COMPLETED/PROCESSING, removing them from the pending list.
"""

import pytest
import tempfile
import os
from unittest.mock import Mock

# Add parent directory to path for imports
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.withdrawal_settings import WithdrawalMode, set_withdrawal_mode, init_withdrawal_settings_table
from utils.withdrawal_service import WithdrawalService, PaymentMode, AdminApprovalState, WithdrawalStatus
from utils.db_utils import init_main_db, create_user
from utils.balance_operations import atomic_deposit_operation, init_operations_ledger


class TestWithdrawalEndToEnd:
    """End-to-end test for withdrawal approval flow."""
    
    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing."""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        
        # Patch DB_FILE to use temp database
        original_db_files = {}
        try:
            # Save original DB_FILE for all modules
            import utils.db_utils
            import utils.withdrawal_service
            import utils.balance_operations
            import utils.withdrawal_settings
            
            original_db_files['db_utils'] = utils.db_utils.DB_FILE
            original_db_files['withdrawal_service'] = utils.withdrawal_service.DB_FILE
            original_db_files['balance_operations'] = utils.balance_operations.DB_FILE
            original_db_files['withdrawal_settings'] = utils.withdrawal_settings.DB_FILE
            
            # Set all to use temp DB
            utils.db_utils.DB_FILE = path
            utils.withdrawal_service.DB_FILE = path
            utils.balance_operations.DB_FILE = path
            utils.withdrawal_settings.DB_FILE = path
            
            # Initialize database
            init_main_db()
            init_operations_ledger()
            init_withdrawal_settings_table()
            
            yield path
            
        finally:
            # Restore original DB_FILE
            utils.db_utils.DB_FILE = original_db_files.get('db_utils', utils.db_utils.DB_FILE)
            utils.withdrawal_service.DB_FILE = original_db_files.get('withdrawal_service', utils.withdrawal_service.DB_FILE)
            utils.balance_operations.DB_FILE = original_db_files.get('balance_operations', utils.balance_operations.DB_FILE)
            utils.withdrawal_settings.DB_FILE = original_db_files.get('withdrawal_settings', utils.withdrawal_settings.DB_FILE)
            
            # Clean up
            try:
                os.unlink(path)
            except:
                pass
    
    @pytest.fixture
    def withdrawal_service(self, temp_db):
        """Create withdrawal service with mocked Flutterwave client."""
        service = WithdrawalService()
        
        # Mock the Flutterwave client
        mock_client = Mock()
        mock_client.initiate_transfer.return_value = {
            'success': True,
            'trace_id': 'test_trace_123'
        }
        service.flutterwave_client = mock_client
        
        return service
    
    @pytest.fixture
    def test_user(self, temp_db):
        """Create test user with balance."""
        user_id = create_user(
            telegram_id=12345,
            username="testuser",
            first_name="Test",
            last_name="User"
        )
        
        # Add some affiliate balance
        atomic_deposit_operation(
            user_id=user_id,
            amount=100.0,
            balance_type="affiliate",
            reason="Test deposit"
        )
        
        return user_id
    
    def test_user_can_create_new_withdrawal_after_manual_approval(self, withdrawal_service, test_user):
        """
        End-to-end test: User creates withdrawal → Admin approves → User creates new withdrawal.
        
        This is the exact scenario from the bug report:
        "When a user has a withdrawal approved and then tries to submit a new withdrawal, 
        the UI blocks them with... 'You already have a pending withdrawal request in progress'"
        """
        # Set manual mode
        set_withdrawal_mode(WithdrawalMode.MANUAL, admin_id=999)
        
        # === STEP 1: User creates first withdrawal ===
        withdrawal1 = withdrawal_service.create_withdrawal(
            user_id=test_user,
            amount_usd=20.0,
            amount_ngn=30000.0,
            account_name="Test User",
            account_number="1234567890",
            bank_name="Test Bank",
            bank_details_raw="Test Bank Details",
            is_affiliate_withdrawal=True,
            payment_mode=PaymentMode.MANUAL
        )
        
        assert withdrawal1 is not None, "First withdrawal should be created"
        assert withdrawal1.status == WithdrawalStatus.PENDING
        assert withdrawal1.admin_approval_state == AdminApprovalState.PENDING
        
        # Verify it appears in user's withdrawals as pending
        user_withdrawals = withdrawal_service.get_user_withdrawals(test_user, limit=5)
        assert len(user_withdrawals) == 1
        
        # Simulate the check that blocks new withdrawals
        has_pending = False
        for wd in user_withdrawals:
            if (wd.status.value in ['pending'] or 
                (wd.payment_mode == PaymentMode.MANUAL and 
                 wd.admin_approval_state and 
                 wd.admin_approval_state.value == 'pending')):
                has_pending = True
                break
        
        assert has_pending, "User should have a pending withdrawal before approval"
        
        # === STEP 2: Admin approves the withdrawal ===
        success = withdrawal_service.approve_withdrawal_by_mode(
            withdrawal1.id, admin_id=999, reason="Approved for testing"
        )
        assert success is True, "Approval should succeed"
        
        # Verify the withdrawal is updated correctly
        updated_withdrawal1 = withdrawal_service.get_withdrawal(withdrawal1.id)
        assert updated_withdrawal1.status == WithdrawalStatus.COMPLETED, \
            "Status should be COMPLETED after manual approval"
        assert updated_withdrawal1.admin_approval_state == AdminApprovalState.APPROVED, \
            "Admin approval state should be APPROVED (this was the bug)"
        
        # === STEP 3: Check if user can create a new withdrawal ===
        # Simulate the same check that happens in custom_order_handlers.py
        user_withdrawals_after = withdrawal_service.get_user_withdrawals(test_user, limit=5)
        has_pending_after = False
        for wd in user_withdrawals_after:
            if (wd.status.value in ['pending'] or 
                (wd.payment_mode == PaymentMode.MANUAL and 
                 wd.admin_approval_state and 
                 wd.admin_approval_state.value == 'pending')):
                has_pending_after = True
                break
        
        assert not has_pending_after, \
            "User should NOT have a pending withdrawal after approval (BUG FIX VERIFICATION)"
        
        # === STEP 4: User creates second withdrawal ===
        # This should succeed now that the first withdrawal is no longer pending
        withdrawal2 = withdrawal_service.create_withdrawal(
            user_id=test_user,
            amount_usd=15.0,
            amount_ngn=22500.0,
            account_name="Test User",
            account_number="1234567890",
            bank_name="Test Bank",
            bank_details_raw="Test Bank Details",
            is_affiliate_withdrawal=True,
            payment_mode=PaymentMode.MANUAL
        )
        
        assert withdrawal2 is not None, \
            "User should be able to create a new withdrawal after previous one is approved"
        assert withdrawal2.id != withdrawal1.id, "Should be a different withdrawal"
        assert withdrawal2.status == WithdrawalStatus.PENDING, "New withdrawal should be pending"
        
        # Verify we now have 2 withdrawals total
        all_withdrawals = withdrawal_service.get_user_withdrawals(test_user, limit=10)
        assert len(all_withdrawals) == 2, "User should have 2 withdrawals total"
        
        # One approved, one pending
        statuses = [w.status for w in all_withdrawals]
        assert WithdrawalStatus.COMPLETED in statuses
        assert WithdrawalStatus.PENDING in statuses
    
    def test_user_can_create_new_withdrawal_after_automatic_approval(self, withdrawal_service, test_user):
        """
        End-to-end test for automatic mode: User creates withdrawal → Auto-approved → User creates new withdrawal.
        """
        # Set automatic mode
        set_withdrawal_mode(WithdrawalMode.AUTOMATIC, admin_id=999)
        
        # === STEP 1: User creates first withdrawal ===
        withdrawal1 = withdrawal_service.create_withdrawal(
            user_id=test_user,
            amount_usd=20.0,
            amount_ngn=30000.0,
            account_name="Test User",
            account_number="1234567890",
            bank_name="Test Bank",
            bank_details_raw="Test Bank Details",
            is_affiliate_withdrawal=True,
            payment_mode=PaymentMode.AUTOMATIC
        )
        
        assert withdrawal1 is not None
        
        # === STEP 2: Admin approves the withdrawal (automatic mode) ===
        success = withdrawal_service.approve_withdrawal_by_mode(
            withdrawal1.id, admin_id=999, reason="Auto-approved for testing"
        )
        assert success is True
        
        # Verify the withdrawal is updated correctly
        updated_withdrawal1 = withdrawal_service.get_withdrawal(withdrawal1.id)
        # Automatic mode sets status to COMPLETED after Flutterwave success
        assert updated_withdrawal1.status in [WithdrawalStatus.PROCESSING, WithdrawalStatus.COMPLETED], \
            "Status should be PROCESSING or COMPLETED after automatic approval"
        assert updated_withdrawal1.admin_approval_state == AdminApprovalState.APPROVED, \
            "Admin approval state should be APPROVED"
        
        # === STEP 3: Verify no pending withdrawals ===
        user_withdrawals_after = withdrawal_service.get_user_withdrawals(test_user, limit=5)
        has_pending_after = False
        for wd in user_withdrawals_after:
            if (wd.status.value in ['pending'] or 
                (wd.payment_mode == PaymentMode.AUTOMATIC and 
                 wd.admin_approval_state and 
                 wd.admin_approval_state.value == 'pending')):
                has_pending_after = True
                break
        
        assert not has_pending_after, \
            "User should NOT have a pending withdrawal after automatic approval"
        
        # === STEP 4: User creates second withdrawal ===
        withdrawal2 = withdrawal_service.create_withdrawal(
            user_id=test_user,
            amount_usd=15.0,
            amount_ngn=22500.0,
            account_name="Test User",
            account_number="1234567890",
            bank_name="Test Bank",
            bank_details_raw="Test Bank Details",
            is_affiliate_withdrawal=True,
            payment_mode=PaymentMode.AUTOMATIC
        )
        
        assert withdrawal2 is not None, \
            "User should be able to create a new withdrawal after previous one is approved (automatic mode)"
    
    def test_rejection_flow_still_works(self, withdrawal_service, test_user):
        """Verify that rejection flow is not affected by the fix."""
        # Set manual mode
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
            is_affiliate_withdrawal=True,
            payment_mode=PaymentMode.MANUAL
        )
        
        # Reject it
        success = withdrawal_service.reject_withdrawal(
            withdrawal.id, admin_id=999, reason="Test rejection"
        )
        assert success is True
        
        # Verify state
        updated = withdrawal_service.get_withdrawal(withdrawal.id)
        assert updated.status == WithdrawalStatus.REJECTED
        assert updated.admin_approval_state == AdminApprovalState.REJECTED
        
        # User should be able to create new withdrawal
        user_withdrawals = withdrawal_service.get_user_withdrawals(test_user, limit=5)
        has_pending = False
        for wd in user_withdrawals:
            if (wd.status.value in ['pending'] or 
                (wd.payment_mode == PaymentMode.MANUAL and 
                 wd.admin_approval_state and 
                 wd.admin_approval_state.value == 'pending')):
                has_pending = True
                break
        
        assert not has_pending, "User should not have pending withdrawal after rejection"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
