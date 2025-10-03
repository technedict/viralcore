#!/usr/bin/env python3
"""
Test manual withdrawal deduction correctness.
"""

import os
import sys
import tempfile
import sqlite3

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_manual_withdrawal_deduction():
    """Test that manual withdrawal correctly deducts balance."""
    
    # Create temporary database
    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    
    try:
        # Override DB_FILE
        import utils.db_utils
        import utils.withdrawal_service
        import utils.balance_operations
        
        original_db_file = utils.db_utils.DB_FILE
        utils.db_utils.DB_FILE = db_path
        utils.withdrawal_service.DB_FILE = db_path
        utils.balance_operations.DB_FILE = db_path
        
        # Initialize database
        from utils.db_utils import init_main_db, get_connection
        from utils.balance_operations import init_operations_ledger, atomic_deposit_operation, get_balance_safely
        from utils.withdrawal_service import WithdrawalService, PaymentMode
        
        init_main_db()
        init_operations_ledger()
        
        # Create withdrawals table
        with get_connection(db_path) as conn:
            c = conn.cursor()
            c.execute('''
                CREATE TABLE IF NOT EXISTS withdrawals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    amount_usd REAL NOT NULL,
                    amount_ngn REAL NOT NULL,
                    payment_mode TEXT NOT NULL DEFAULT 'automatic',
                    admin_approval_state TEXT DEFAULT NULL,
                    admin_id INTEGER DEFAULT NULL,
                    account_name TEXT NOT NULL,
                    account_number TEXT NOT NULL,
                    bank_name TEXT NOT NULL,
                    bank_details_raw TEXT NOT NULL,
                    is_affiliate_withdrawal INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pending',
                    approved_at TEXT DEFAULT NULL,
                    processed_at TEXT DEFAULT NULL,
                    failure_reason TEXT DEFAULT NULL,
                    flutterwave_reference TEXT DEFAULT NULL,
                    flutterwave_trace_id TEXT DEFAULT NULL,
                    operation_id TEXT DEFAULT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (user_id) REFERENCES users (id),
                    FOREIGN KEY (admin_id) REFERENCES users (id)
                )
            ''')
            
            # Create audit log table
            c.execute('''
                CREATE TABLE IF NOT EXISTS withdrawal_audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    withdrawal_id INTEGER NOT NULL,
                    admin_id INTEGER DEFAULT NULL,
                    action TEXT NOT NULL,
                    old_status TEXT DEFAULT NULL,
                    new_status TEXT DEFAULT NULL,
                    old_approval_state TEXT DEFAULT NULL,
                    new_approval_state TEXT DEFAULT NULL,
                    reason TEXT DEFAULT NULL,
                    metadata TEXT DEFAULT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (withdrawal_id) REFERENCES withdrawals (id),
                    FOREIGN KEY (admin_id) REFERENCES users (id)
                )
            ''')
            
            conn.commit()
        
        # Test Case 1: Affiliate withdrawal
        print("\n=== Test Case 1: Affiliate Withdrawal ===")
        
        # Create user with affiliate balance
        user_id = 12345
        admin_id = 1
        initial_balance = 100.0
        withdrawal_amount = 50.0
        
        with get_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("INSERT INTO users (id, username, affiliate_balance) VALUES (?, ?, ?)",
                     (user_id, "test_user", initial_balance))
            c.execute("INSERT INTO users (id, username, is_admin) VALUES (?, ?, ?)",
                     (admin_id, "admin_user", 1))
            conn.commit()
        
        # Verify initial balance
        balance_before = get_balance_safely(user_id, "affiliate")
        print(f"Initial affiliate balance: ${balance_before}")
        assert balance_before == initial_balance, f"Expected {initial_balance}, got {balance_before}"
        
        # Create withdrawal service and withdrawal request
        service = WithdrawalService()
        os.environ["DISABLE_ADMIN_APPROVAL"] = "false"  # Enable admin approval
        
        withdrawal = service.create_withdrawal(
            user_id=user_id,
            amount_usd=withdrawal_amount,
            amount_ngn=withdrawal_amount * 1650,  # Mock exchange rate
            account_name="Test Account",
            account_number="1234567890",
            bank_name="Test Bank",
            bank_details_raw="Test Details",
            is_affiliate_withdrawal=True,
            payment_mode=PaymentMode.MANUAL
        )
        
        print(f"Created withdrawal ID: {withdrawal.id}")
        print(f"Withdrawal status: {withdrawal.status}")
        print(f"Admin approval state: {withdrawal.admin_approval_state}")
        
        # Approve withdrawal
        success = service.approve_manual_withdrawal(
            withdrawal_id=withdrawal.id,
            admin_id=admin_id,
            reason="Test approval"
        )
        
        print(f"Approval success: {success}")
        assert success, "Withdrawal approval should succeed"
        
        # Verify balance was deducted
        balance_after = get_balance_safely(user_id, "affiliate")
        expected_balance = initial_balance - withdrawal_amount
        
        print(f"Balance after withdrawal: ${balance_after}")
        print(f"Expected balance: ${expected_balance}")
        
        assert abs(balance_after - expected_balance) < 0.01, \
            f"Balance mismatch: expected {expected_balance}, got {balance_after}"
        
        # Verify withdrawal record
        withdrawal_after = service.get_withdrawal(withdrawal.id)
        assert withdrawal_after.status.value == "completed", \
            f"Withdrawal should be completed, got {withdrawal_after.status.value}"
        assert withdrawal_after.admin_id == admin_id, \
            f"Admin ID should be {admin_id}, got {withdrawal_after.admin_id}"
        
        print("✅ Test Case 1 PASSED: Affiliate withdrawal correctly deducted balance")
        
        # Test Case 2: Insufficient balance
        print("\n=== Test Case 2: Insufficient Balance ===")
        
        # Try to withdraw more than available
        large_withdrawal = service.create_withdrawal(
            user_id=user_id,
            amount_usd=200.0,  # More than remaining balance
            amount_ngn=200.0 * 1650,
            account_name="Test Account",
            account_number="1234567890",
            bank_name="Test Bank",
            bank_details_raw="Test Details",
            is_affiliate_withdrawal=True,
            payment_mode=PaymentMode.MANUAL
        )
        
        # Try to approve (should fail)
        success = service.approve_manual_withdrawal(
            withdrawal_id=large_withdrawal.id,
            admin_id=admin_id,
            reason="Should fail"
        )
        
        print(f"Large withdrawal approval success: {success}")
        assert not success, "Large withdrawal should fail due to insufficient balance"
        
        # Balance should remain unchanged
        balance_unchanged = get_balance_safely(user_id, "affiliate")
        print(f"Balance after failed withdrawal: ${balance_unchanged}")
        assert abs(balance_unchanged - expected_balance) < 0.01, \
            "Balance should not change after failed withdrawal"
        
        print("✅ Test Case 2 PASSED: Insufficient balance prevented withdrawal")
        
        # Test Case 3: Idempotency (double approval)
        print("\n=== Test Case 3: Idempotency ===")
        
        # Create another withdrawal
        second_withdrawal = service.create_withdrawal(
            user_id=user_id,
            amount_usd=10.0,
            amount_ngn=10.0 * 1650,
            account_name="Test Account",
            account_number="1234567890",
            bank_name="Test Bank",
            bank_details_raw="Test Details",
            is_affiliate_withdrawal=True,
            payment_mode=PaymentMode.MANUAL
        )
        
        # Approve once
        success1 = service.approve_manual_withdrawal(
            withdrawal_id=second_withdrawal.id,
            admin_id=admin_id,
            reason="First approval"
        )
        assert success1, "First approval should succeed"
        
        balance_after_first = get_balance_safely(user_id, "affiliate")
        print(f"Balance after first approval: ${balance_after_first}")
        
        # Try to approve again (idempotency test)
        success2 = service.approve_manual_withdrawal(
            withdrawal_id=second_withdrawal.id,
            admin_id=admin_id,
            reason="Second approval (should be idempotent)"
        )
        assert success2, "Second approval should succeed (idempotent)"
        
        balance_after_second = get_balance_safely(user_id, "affiliate")
        print(f"Balance after second approval: ${balance_after_second}")
        
        # Balance should be the same (not deducted twice)
        assert abs(balance_after_first - balance_after_second) < 0.01, \
            "Balance should not be deducted twice (idempotency)"
        
        print("✅ Test Case 3 PASSED: Idempotency prevents double deduction")
        
        print("\n" + "=" * 50)
        print("✅ ALL MANUAL WITHDRAWAL TESTS PASSED!")
        print("=" * 50)
        
        return True
        
    finally:
        # Cleanup
        try:
            os.unlink(db_path)
        except:
            pass
        
        # Restore original DB_FILE
        try:
            utils.db_utils.DB_FILE = original_db_file
            utils.withdrawal_service.DB_FILE = original_db_file
            utils.balance_operations.DB_FILE = original_db_file
        except:
            pass


if __name__ == "__main__":
    try:
        test_manual_withdrawal_deduction()
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
