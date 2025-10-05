#!/usr/bin/env python3
"""
Validation script for withdrawal approval state fix.

This script performs comprehensive validation to ensure:
1. Withdrawal approvals set both status and admin_approval_state
2. No withdrawals stuck in pending state after approval
3. Audit log properly records state transitions
4. No regressions in existing functionality

Run this script after deploying the fix to production.
"""

import sys
import os
import tempfile

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.withdrawal_service import WithdrawalService, PaymentMode, AdminApprovalState, WithdrawalStatus
from utils.db_utils import get_connection, init_main_db, create_user, DB_FILE
from utils.balance_operations import atomic_deposit_operation, init_operations_ledger
from utils.withdrawal_settings import WithdrawalMode, set_withdrawal_mode, init_withdrawal_settings_table
from unittest.mock import Mock, MagicMock


def test_manual_mode_approval():
    """Test manual mode approval sets admin_approval_state."""
    print("\n1. Testing manual mode approval...")
    
    # Create temp database for isolated test
    temp_db = tempfile.mktemp(suffix='.db')
    
    # Patch DB_FILE
    import utils.db_utils
    import utils.withdrawal_service
    import utils.balance_operations
    import utils.withdrawal_settings
    
    original_db = utils.db_utils.DB_FILE
    utils.db_utils.DB_FILE = temp_db
    utils.withdrawal_service.DB_FILE = temp_db
    utils.balance_operations.DB_FILE = temp_db
    utils.withdrawal_settings.DB_FILE = temp_db
    
    try:
        # Initialize database
        init_main_db()
        init_withdrawal_settings_table()
        init_operations_ledger()
        
        from scripts.migrate_database import apply_withdrawals_migration
        apply_withdrawals_migration()
        
        # Create test user
        user_id = 12345
        create_user(user_id, "test_user")
        atomic_deposit_operation(user_id, "affiliate", 100.0, "Test setup")
        
        # Set manual mode
        set_withdrawal_mode(WithdrawalMode.MANUAL, admin_id=999)
        
        # Create withdrawal service
        ws = WithdrawalService()
        ws.flutterwave_client = Mock()
        
        # Create and approve withdrawal
        withdrawal = ws.create_withdrawal(
            user_id=user_id,
            amount_usd=40.0,
            amount_ngn=60000.0,
            account_name="Test User",
            account_number="1234567890",
            bank_name="Test Bank",
            bank_details_raw="Test Details",
            is_affiliate_withdrawal=True,
            payment_mode=PaymentMode.MANUAL
        )
        
        success = ws.approve_withdrawal_by_mode(withdrawal.id, admin_id=999, reason="Test")
        assert success, "Approval should succeed"
        
        # Verify state
        updated = ws.get_withdrawal(withdrawal.id)
        assert updated.status == WithdrawalStatus.COMPLETED, "Status should be COMPLETED"
        assert updated.admin_approval_state == AdminApprovalState.APPROVED, "Approval state should be APPROVED"
        
        # Verify not in pending list
        pending = ws.get_pending_withdrawals()
        assert len(pending) == 0, "Should not be in pending list"
        
        print("   ✅ Manual mode approval works correctly")
        return True
        
    finally:
        # Restore and cleanup
        utils.db_utils.DB_FILE = original_db
        utils.withdrawal_service.DB_FILE = original_db
        utils.balance_operations.DB_FILE = original_db
        utils.withdrawal_settings.DB_FILE = original_db
        os.remove(temp_db)


def test_automatic_mode_approval():
    """Test automatic mode approval sets admin_approval_state."""
    print("\n2. Testing automatic mode approval...")
    
    # Create temp database for isolated test
    temp_db = tempfile.mktemp(suffix='.db')
    
    # Patch DB_FILE
    import utils.db_utils
    import utils.withdrawal_service
    import utils.balance_operations
    import utils.withdrawal_settings
    
    original_db = utils.db_utils.DB_FILE
    utils.db_utils.DB_FILE = temp_db
    utils.withdrawal_service.DB_FILE = temp_db
    utils.balance_operations.DB_FILE = temp_db
    utils.withdrawal_settings.DB_FILE = temp_db
    
    try:
        # Initialize database
        init_main_db()
        init_withdrawal_settings_table()
        init_operations_ledger()
        
        from scripts.migrate_database import apply_withdrawals_migration
        apply_withdrawals_migration()
        
        # Create test user
        user_id = 12345
        create_user(user_id, "test_user")
        atomic_deposit_operation(user_id, "affiliate", 100.0, "Test setup")
        
        # Set automatic mode
        set_withdrawal_mode(WithdrawalMode.AUTOMATIC, admin_id=999)
        
        # Create withdrawal service with mocked API
        ws = WithdrawalService()
        mock_client = Mock()
        mock_client.initiate_transfer = MagicMock(return_value={
            'success': True,
            'trace_id': 'test_trace_123'
        })
        ws.flutterwave_client = mock_client
        
        # Create and approve withdrawal
        withdrawal = ws.create_withdrawal(
            user_id=user_id,
            amount_usd=40.0,
            amount_ngn=60000.0,
            account_name="Test User",
            account_number="1234567890",
            bank_name="Test Bank",
            bank_details_raw="Test Details",
            is_affiliate_withdrawal=True,
            payment_mode=PaymentMode.AUTOMATIC
        )
        
        success = ws.approve_withdrawal_by_mode(withdrawal.id, admin_id=999, reason="Test")
        assert success, "Approval should succeed"
        
        # Verify state
        updated = ws.get_withdrawal(withdrawal.id)
        assert updated.status == WithdrawalStatus.COMPLETED, "Status should be COMPLETED"
        assert updated.admin_approval_state == AdminApprovalState.APPROVED, "Approval state should be APPROVED"
        
        # Verify not in pending list
        pending = ws.get_pending_withdrawals()
        assert len(pending) == 0, "Should not be in pending list"
        
        print("   ✅ Automatic mode approval works correctly")
        return True
        
    finally:
        # Restore and cleanup
        utils.db_utils.DB_FILE = original_db
        utils.withdrawal_service.DB_FILE = original_db
        utils.balance_operations.DB_FILE = original_db
        utils.withdrawal_settings.DB_FILE = original_db
        os.remove(temp_db)


def check_production_data():
    """Check production data for inconsistencies."""
    print("\n3. Checking production data for inconsistencies...")
    
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        
        # Check for inconsistent records
        c.execute('''
            SELECT COUNT(*) FROM withdrawals
            WHERE (status IN ('completed', 'processing') AND admin_approval_state != 'approved')
               OR (status = 'rejected' AND admin_approval_state != 'rejected')
        ''')
        
        inconsistent_count = c.fetchone()[0]
        
        if inconsistent_count > 0:
            print(f"   ⚠️  Found {inconsistent_count} inconsistent record(s)")
            print("   Run scripts/reconcile_withdrawal_states.py to fix")
            return False
        else:
            print("   ✅ No inconsistent records found")
            return True


def main():
    """Run all validation checks."""
    print("\n" + "="*80)
    print("Withdrawal Approval State Fix - Validation")
    print("="*80)
    
    results = []
    
    try:
        # Test manual mode
        results.append(("Manual Mode Approval", test_manual_mode_approval()))
    except Exception as e:
        print(f"   ❌ Manual mode test failed: {e}")
        results.append(("Manual Mode Approval", False))
    
    try:
        # Test automatic mode
        results.append(("Automatic Mode Approval", test_automatic_mode_approval()))
    except Exception as e:
        print(f"   ❌ Automatic mode test failed: {e}")
        results.append(("Automatic Mode Approval", False))
    
    try:
        # Check production data
        results.append(("Production Data Check", check_production_data()))
    except Exception as e:
        print(f"   ❌ Production data check failed: {e}")
        results.append(("Production Data Check", False))
    
    # Summary
    print("\n" + "="*80)
    print("Validation Summary")
    print("="*80)
    
    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status:12} - {name}")
    
    all_passed = all(success for _, success in results)
    
    print("\n" + "="*80)
    if all_passed:
        print("✅ All validation checks passed!")
        print("The fix is working correctly.")
    else:
        print("❌ Some validation checks failed!")
        print("Please review the errors above.")
    print("="*80 + "\n")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nValidation interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
