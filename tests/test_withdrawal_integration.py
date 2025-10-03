#!/usr/bin/env python3
# tests/test_withdrawal_integration.py
# Integration test for complete withdrawal flow

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def test_basic_imports():
    """Test that all necessary modules can be imported."""
    from utils.withdrawal_service import WithdrawalService, PaymentMode, AdminApprovalState, WithdrawalStatus
    from utils.balance_operations import atomic_withdraw_operation, atomic_deposit_operation
    from utils.db_utils import get_connection
    
    print("✓ All imports successful")

def test_withdrawal_service_instantiation():
    """Test that WithdrawalService can be instantiated."""
    from utils.withdrawal_service import WithdrawalService
    from unittest.mock import Mock
    
    service = WithdrawalService()
    service.flutterwave_client = Mock()
    
    print("✓ WithdrawalService instantiated successfully")

def test_balance_operations_work():
    """Test basic balance operations."""
    import tempfile
    from utils.db_utils import init_main_db, create_user, get_connection
    from utils.balance_operations import atomic_deposit_operation, atomic_withdraw_operation, init_operations_ledger
    import utils.db_utils
    import utils.balance_operations
    
    # Create temp DB
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    
    try:
        # Patch DB paths
        original_db = utils.db_utils.DB_FILE
        utils.db_utils.DB_FILE = path
        utils.balance_operations.DB_FILE = path
        
        # Initialize
        init_main_db()
        init_operations_ledger()
        
        # Create user
        create_user(12345, "testuser")
        
        # Test deposit
        success = atomic_deposit_operation(
            user_id=12345,
            balance_type="affiliate",
            amount=100.0,
            reason="Test deposit"
        )
        assert success, "Deposit failed"
        
        # Test withdrawal
        success = atomic_withdraw_operation(
            user_id=12345,
            balance_type="affiliate",
            amount=50.0,
            reason="Test withdrawal"
        )
        assert success, "Withdrawal failed"
        
        # Verify balance
        with get_connection(path) as conn:
            c = conn.cursor()
            c.execute("SELECT affiliate_balance FROM users WHERE id = 12345")
            row = c.fetchone()
            balance = row['affiliate_balance'] if row else 0.0
            assert balance == 50.0, f"Expected balance 50.0, got {balance}"
        
        print("✓ Balance operations work correctly")
        
    finally:
        utils.db_utils.DB_FILE = original_db
        utils.balance_operations.DB_FILE = original_db
        try:
            os.unlink(path)
        except:
            pass

def test_approval_required_for_withdrawals():
    """Test that withdrawals require approval."""
    import tempfile
    from utils.db_utils import init_main_db, create_user, get_connection
    from utils.withdrawal_service import WithdrawalService, WithdrawalStatus, AdminApprovalState
    from utils.withdrawal_settings import init_withdrawal_settings_table, set_withdrawal_mode, WithdrawalMode
    from utils.balance_operations import atomic_deposit_operation, init_operations_ledger
    from unittest.mock import Mock
    import utils.db_utils
    import utils.balance_operations
    import utils.withdrawal_service
    import utils.withdrawal_settings
    
    # Create temp DB
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    
    try:
        # Patch DB paths
        original_db = utils.db_utils.DB_FILE
        utils.db_utils.DB_FILE = path
        utils.balance_operations.DB_FILE = path
        utils.withdrawal_service.DB_FILE = path
        utils.withdrawal_settings.DB_FILE = path
        
        # Initialize
        init_main_db()
        init_operations_ledger()
        init_withdrawal_settings_table()
        
        # Create withdrawals table
        with get_connection(path) as conn:
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
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            ''')
            
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
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            ''')
            conn.commit()
        
        # Create user with balance
        create_user(12345, "testuser")
        atomic_deposit_operation(12345, "affiliate", 1000.0, "Test balance")
        
        # Set automatic mode
        set_withdrawal_mode(WithdrawalMode.AUTOMATIC, admin_id=999)
        
        # Create service
        service = WithdrawalService()
        service.flutterwave_client = Mock()
        
        # Create withdrawal
        withdrawal = service.create_withdrawal(
            user_id=12345,
            amount_usd=100.0,
            amount_ngn=150000.0,
            account_name="Test User",
            account_number="1234567890",
            bank_name="Test Bank",
            bank_details_raw="Test Bank Details"
        )
        
        # Verify withdrawal state
        assert withdrawal.status == WithdrawalStatus.PENDING, "Withdrawal should be PENDING"
        assert withdrawal.admin_approval_state == AdminApprovalState.PENDING, "Should require approval"
        
        # Verify API was NOT called
        service.flutterwave_client.initiate_transfer.assert_not_called()
        
        print("✓ Withdrawals correctly require admin approval")
        
    finally:
        utils.db_utils.DB_FILE = original_db
        utils.balance_operations.DB_FILE = original_db
        utils.withdrawal_service.DB_FILE = original_db
        utils.withdrawal_settings.DB_FILE = original_db
        try:
            os.unlink(path)
        except:
            pass

if __name__ == "__main__":
    print("Running integration tests...")
    print()
    
    test_basic_imports()
    test_withdrawal_service_instantiation()
    test_balance_operations_work()
    test_approval_required_for_withdrawals()
    
    print()
    print("=" * 60)
    print("✅ All integration tests passed!")
    print("=" * 60)
