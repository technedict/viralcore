#!/usr/bin/env python3
"""
Test for withdrawal approval state consistency fix.

This test ensures that when an admin approves a withdrawal, both the status
and admin_approval_state fields are updated atomically and consistently.

Bug: After admin approval, admin_approval_state was not being set to APPROVED,
causing data inconsistency in the audit trail.

Fix: Updated _approve_withdrawal_manual_mode and _approve_withdrawal_automatic_mode
to set withdrawal.admin_approval_state = AdminApprovalState.APPROVED
"""

import pytest
import tempfile
import os
from unittest.mock import Mock, MagicMock

# Add parent directory to path for imports
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.withdrawal_settings import WithdrawalMode, set_withdrawal_mode, init_withdrawal_settings_table
from utils.withdrawal_service import WithdrawalService, PaymentMode, AdminApprovalState, WithdrawalStatus
from utils.db_utils import init_main_db, create_user
from utils.balance_operations import atomic_deposit_operation, init_operations_ledger


class TestWithdrawalApprovalStateFix:
    """Test withdrawal approval state consistency."""
    
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
            
            # Set temp DB for all modules
            utils.db_utils.DB_FILE = path
            utils.withdrawal_service.DB_FILE = path
            utils.balance_operations.DB_FILE = path
            utils.withdrawal_settings.DB_FILE = path
            
            # Initialize database
            init_main_db()
            init_withdrawal_settings_table()
            init_operations_ledger()
            
            # Initialize withdrawals table - need to set DB_FILE for migration script too
            import scripts.migrate_database
            original_migrate_db = scripts.migrate_database.DB_FILE if hasattr(scripts.migrate_database, 'DB_FILE') else None
            
            # Temporarily patch migrate_database module
            if hasattr(scripts.migrate_database, 'DB_FILE'):
                scripts.migrate_database.DB_FILE = path
            
            from scripts.migrate_database import apply_withdrawals_migration
            apply_withdrawals_migration()
            
            # Restore migrate_database DB_FILE
            if original_migrate_db is not None:
                scripts.migrate_database.DB_FILE = original_migrate_db
            
            yield path
            
        finally:
            # Restore original DB_FILE for all modules
            if 'db_utils' in original_db_files:
                utils.db_utils.DB_FILE = original_db_files['db_utils']
            if 'withdrawal_service' in original_db_files:
                utils.withdrawal_service.DB_FILE = original_db_files['withdrawal_service']
            if 'balance_operations' in original_db_files:
                utils.balance_operations.DB_FILE = original_db_files['balance_operations']
            if 'withdrawal_settings' in original_db_files:
                utils.withdrawal_settings.DB_FILE = original_db_files['withdrawal_settings']
            
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
    
    def test_manual_mode_sets_admin_approval_state(self, withdrawal_service, test_user):
        """Test that manual mode approval sets admin_approval_state to APPROVED."""
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
            is_affiliate_withdrawal=True,
            payment_mode=PaymentMode.MANUAL
        )
        
        # Verify initial state
        assert withdrawal.status == WithdrawalStatus.PENDING
        assert withdrawal.admin_approval_state == AdminApprovalState.PENDING
        
        # Approve withdrawal
        success = withdrawal_service.approve_withdrawal_by_mode(
            withdrawal.id, admin_id=999, reason="Test approval"
        )
        assert success is True
        
        # Get updated withdrawal
        updated = withdrawal_service.get_withdrawal(withdrawal.id)
        
        # Verify both status and admin_approval_state are updated
        assert updated.status == WithdrawalStatus.COMPLETED, \
            "Status should be COMPLETED after manual approval"
        assert updated.admin_approval_state == AdminApprovalState.APPROVED, \
            "Admin approval state should be APPROVED (this was the bug)"
        assert updated.admin_id == 999, "Admin ID should be recorded"
        assert updated.approved_at is not None, "Approval timestamp should be set"
        assert updated.processed_at is not None, "Processing timestamp should be set"
    
    def test_automatic_mode_sets_admin_approval_state(self, withdrawal_service, test_user):
        """Test that automatic mode approval sets admin_approval_state to APPROVED."""
        # Set automatic mode
        set_withdrawal_mode(WithdrawalMode.AUTOMATIC, admin_id=999)
        
        # Mock Flutterwave API to return success
        mock_response = {
            'success': True,
            'trace_id': 'test_trace_123'
        }
        withdrawal_service.flutterwave_client.initiate_transfer = MagicMock(
            return_value=mock_response
        )
        
        # Create withdrawal
        withdrawal = withdrawal_service.create_withdrawal(
            user_id=test_user,
            amount_usd=40.0,
            amount_ngn=60000.0,
            account_name="Test User",
            account_number="1234567890",
            bank_name="Test Bank",
            bank_details_raw="Test Bank Details",
            is_affiliate_withdrawal=True,
            payment_mode=PaymentMode.AUTOMATIC
        )
        
        # Verify initial state
        assert withdrawal.status == WithdrawalStatus.PENDING
        assert withdrawal.admin_approval_state == AdminApprovalState.PENDING
        
        # Approve withdrawal
        success = withdrawal_service.approve_withdrawal_by_mode(
            withdrawal.id, admin_id=999, reason="Test approval"
        )
        assert success is True
        
        # Get updated withdrawal
        updated = withdrawal_service.get_withdrawal(withdrawal.id)
        
        # Verify both status and admin_approval_state are updated
        assert updated.status == WithdrawalStatus.COMPLETED, \
            "Status should be COMPLETED after successful automatic approval"
        assert updated.admin_approval_state == AdminApprovalState.APPROVED, \
            "Admin approval state should be APPROVED (this was the bug)"
        assert updated.admin_id == 999, "Admin ID should be recorded"
        assert updated.approved_at is not None, "Approval timestamp should be set"
        assert updated.processed_at is not None, "Processing timestamp should be set"
    
    def test_approved_withdrawal_not_in_pending_list(self, withdrawal_service, test_user):
        """Test that approved withdrawal does not appear in pending list."""
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
            is_affiliate_withdrawal=True,
            payment_mode=PaymentMode.MANUAL
        )
        
        # Verify it appears in pending list before approval
        pending_before = withdrawal_service.get_pending_withdrawals()
        assert len(pending_before) == 1
        assert pending_before[0].id == withdrawal.id
        
        # Approve withdrawal
        success = withdrawal_service.approve_withdrawal_by_mode(
            withdrawal.id, admin_id=999, reason="Test approval"
        )
        assert success is True
        
        # Verify it does NOT appear in pending list after approval
        pending_after = withdrawal_service.get_pending_withdrawals()
        assert len(pending_after) == 0, \
            "Approved withdrawal should not appear in pending list"
    
    def test_rejection_sets_admin_approval_state(self, withdrawal_service, test_user):
        """Test that rejection also sets admin_approval_state correctly."""
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
            is_affiliate_withdrawal=True,
            payment_mode=PaymentMode.MANUAL
        )
        
        # Reject withdrawal
        success = withdrawal_service.reject_withdrawal(
            withdrawal.id, admin_id=999, reason="Test rejection"
        )
        assert success is True
        
        # Get updated withdrawal
        updated = withdrawal_service.get_withdrawal(withdrawal.id)
        
        # Verify both status and admin_approval_state are updated
        assert updated.status == WithdrawalStatus.REJECTED
        assert updated.admin_approval_state == AdminApprovalState.REJECTED
        assert updated.admin_id == 999
    
    def test_idempotent_approval_maintains_state(self, withdrawal_service, test_user):
        """Test that re-approving an already approved withdrawal is idempotent."""
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
            is_affiliate_withdrawal=True,
            payment_mode=PaymentMode.MANUAL
        )
        
        # First approval
        success1 = withdrawal_service.approve_withdrawal_by_mode(
            withdrawal.id, admin_id=999, reason="First approval"
        )
        assert success1 is True
        
        # Get state after first approval
        after_first = withdrawal_service.get_withdrawal(withdrawal.id)
        assert after_first.status == WithdrawalStatus.COMPLETED
        assert after_first.admin_approval_state == AdminApprovalState.APPROVED
        
        # Second approval (should be idempotent)
        success2 = withdrawal_service.approve_withdrawal_by_mode(
            withdrawal.id, admin_id=888, reason="Second approval"
        )
        assert success2 is True
        
        # Get state after second approval
        after_second = withdrawal_service.get_withdrawal(withdrawal.id)
        
        # Should still be completed and approved (idempotent)
        assert after_second.status == WithdrawalStatus.COMPLETED
        assert after_second.admin_approval_state == AdminApprovalState.APPROVED
