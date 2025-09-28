#!/usr/bin/env python3
# tests/test_self.withdrawal_service.py
# Tests for withdrawal service with automatic vs manual payment modes

import unittest
import sqlite3
import os
import tempfile
import sys
from unittest.mock import patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set up test database path before imports
TEST_DB = tempfile.mktemp(suffix='.db')

# Mock the config module before imports
sys.modules['utils.config'] = MagicMock()
sys.modules['utils.api_client'] = MagicMock()

# Mock the DB_FILE constant
import utils.db_utils
utils.db_utils.DB_FILE = TEST_DB

from utils.withdrawal_service import (
    Withdrawal, 
    PaymentMode, 
    AdminApprovalState, 
    WithdrawalStatus,
    WithdrawalService
)
from utils.db_utils import get_connection


class TestWithdrawalService(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        """Set up test database with required tables."""
        # Create database and tables
        cls.db_file = TEST_DB
        
        # Create withdrawal service instance with mocked dependencies
        cls.withdrawal_service = WithdrawalService()  
        cls.withdrawal_service.flutterwave_client = MagicMock()
        
        with get_connection(cls.db_file) as conn:
            c = conn.cursor()
            
            # Create users table
            c.execute('''
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY,
                    username TEXT,
                    affiliate_balance REAL DEFAULT 0.0,
                    is_admin INTEGER DEFAULT 0
                )
            ''')
            
            # Create withdrawals table
            c.execute('''
                CREATE TABLE withdrawals (
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
                    FOREIGN KEY (admin_id) REFERENCES users (id),
                    CHECK (payment_mode IN ('automatic', 'manual')),
                    CHECK (admin_approval_state IS NULL OR admin_approval_state IN ('pending', 'approved', 'rejected')),
                    CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'rejected'))
                )
            ''')
            
            # Create withdrawal audit log table
            c.execute('''
                CREATE TABLE withdrawal_audit_log (
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
            
            # Create balance operations table for atomic operations
            c.execute('''
                CREATE TABLE balance_operations (
                    operation_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    balance_type TEXT NOT NULL,
                    amount REAL NOT NULL,
                    operation_type TEXT NOT NULL,
                    reason TEXT,
                    timestamp TEXT NOT NULL,
                    status TEXT DEFAULT 'completed'
                )
            ''')
            
            # Insert test users
            c.execute('INSERT INTO users (id, username, is_admin) VALUES (1, "testuser", 0)')
            c.execute('INSERT INTO users (id, username, is_admin) VALUES (2, "admin", 1)')
            
            conn.commit()
    
    @classmethod
    def tearDownClass(cls):
        """Clean up test database."""
        if os.path.exists(cls.db_file):
            os.unlink(cls.db_file)
    
    def setUp(self):
        """Reset database state for each test."""
        with get_connection(self.db_file) as conn:
            c = conn.cursor()
            c.execute('DELETE FROM withdrawals')
            c.execute('DELETE FROM withdrawal_audit_log')
            c.execute('DELETE FROM balance_operations')
            conn.commit()
    
    @patch('utils.self.withdrawal_service.atomic_withdraw_operation')
    def test_create_automatic_withdrawal(self, mock_atomic_withdraw):
        """Test creating an automatic withdrawal."""
        mock_atomic_withdraw.return_value = True
        
        withdrawal = self.self.withdrawal_service.create_withdrawal(
            user_id=1,
            amount_usd=50.0,
            amount_ngn=75000.0,
            account_name="Test User",
            account_number="1234567890",
            bank_name="Test Bank",
            bank_details_raw="Test User, 1234567890, Test Bank",
            is_affiliate_withdrawal=False,
            payment_mode=PaymentMode.AUTOMATIC
        )
        
        self.assertEqual(withdrawal.payment_mode, PaymentMode.AUTOMATIC)
        self.assertEqual(withdrawal.status, WithdrawalStatus.PENDING)
        self.assertIsNone(withdrawal.admin_approval_state)
        self.assertEqual(withdrawal.user_id, 1)
        self.assertEqual(withdrawal.amount_usd, 50.0)
        self.assertIsNotNone(withdrawal.id)
        self.assertIsNotNone(withdrawal.operation_id)
    
    def test_create_manual_withdrawal(self):
        """Test creating a manual withdrawal."""
        withdrawal = self.withdrawal_service.create_withdrawal(
            user_id=1,
            amount_usd=100.0,
            amount_ngn=150000.0,
            account_name="Test User",
            account_number="1234567890",
            bank_name="Test Bank",
            bank_details_raw="Test User, 1234567890, Test Bank",
            is_affiliate_withdrawal=True,
            payment_mode=PaymentMode.MANUAL
        )
        
        self.assertEqual(withdrawal.payment_mode, PaymentMode.MANUAL)
        self.assertEqual(withdrawal.status, WithdrawalStatus.PENDING)
        self.assertEqual(withdrawal.admin_approval_state, AdminApprovalState.PENDING)
        self.assertEqual(withdrawal.user_id, 1)
        self.assertEqual(withdrawal.amount_usd, 100.0)
        self.assertTrue(withdrawal.is_affiliate_withdrawal)
        self.assertIsNotNone(withdrawal.id)
    
    @patch('utils.self.withdrawal_service.atomic_withdraw_operation')
    def test_approve_manual_withdrawal(self, mock_atomic_withdraw):
        """Test approving a manual withdrawal."""
        mock_atomic_withdraw.return_value = True
        
        # Create manual withdrawal
        withdrawal = self.withdrawal_service.create_withdrawal(
            user_id=1,
            amount_usd=100.0,
            amount_ngn=150000.0,
            account_name="Test User",
            account_number="1234567890",
            bank_name="Test Bank",
            bank_details_raw="Test User, 1234567890, Test Bank",
            payment_mode=PaymentMode.MANUAL
        )
        
        # Approve the withdrawal
        success = self.withdrawal_service.approve_manual_withdrawal(
            withdrawal_id=withdrawal.id,
            admin_id=2,
            reason="Approved for testing"
        )
        
        self.assertTrue(success)
        
        # Verify withdrawal was updated
        updated_withdrawal = self.withdrawal_service.get_withdrawal(withdrawal.id)
        self.assertEqual(updated_withdrawal.admin_approval_state, AdminApprovalState.APPROVED)
        self.assertEqual(updated_withdrawal.status, WithdrawalStatus.COMPLETED)
        self.assertEqual(updated_withdrawal.admin_id, 2)
        self.assertIsNotNone(updated_withdrawal.approved_at)
        self.assertIsNotNone(updated_withdrawal.processed_at)
        
        # Verify atomic operation was called
        mock_atomic_withdraw.assert_called_once()
    
    def test_reject_manual_withdrawal(self):
        """Test rejecting a manual withdrawal."""
        # Create manual withdrawal
        withdrawal = self.withdrawal_service.create_withdrawal(
            user_id=1,
            amount_usd=100.0,
            amount_ngn=150000.0,
            account_name="Test User",
            account_number="1234567890",
            bank_name="Test Bank",
            bank_details_raw="Test User, 1234567890, Test Bank",
            payment_mode=PaymentMode.MANUAL
        )
        
        # Reject the withdrawal
        success = self.withdrawal_service.reject_manual_withdrawal(
            withdrawal_id=withdrawal.id,
            admin_id=2,
            reason="Rejected for testing"
        )
        
        self.assertTrue(success)
        
        # Verify withdrawal was updated
        updated_withdrawal = self.withdrawal_service.get_withdrawal(withdrawal.id)
        self.assertEqual(updated_withdrawal.admin_approval_state, AdminApprovalState.REJECTED)
        self.assertEqual(updated_withdrawal.status, WithdrawalStatus.REJECTED)
        self.assertEqual(updated_withdrawal.admin_id, 2)
        self.assertEqual(updated_withdrawal.failure_reason, "Rejected for testing")
        self.assertIsNotNone(updated_withdrawal.processed_at)
    
    def test_idempotent_approval(self):
        """Test that approval is idempotent."""
        with patch('utils.self.withdrawal_service.atomic_withdraw_operation') as mock_atomic_withdraw:
            mock_atomic_withdraw.return_value = True
            
            # Create manual withdrawal
            withdrawal = self.withdrawal_service.create_withdrawal(
                user_id=1,
                amount_usd=50.0,
                amount_ngn=75000.0,
                account_name="Test User",
                account_number="1234567890",
                bank_name="Test Bank",
                bank_details_raw="Test User, 1234567890, Test Bank",
                payment_mode=PaymentMode.MANUAL
            )
            
            # Approve twice
            success1 = self.withdrawal_service.approve_manual_withdrawal(withdrawal.id, 2)
            success2 = self.withdrawal_service.approve_manual_withdrawal(withdrawal.id, 2)
            
            self.assertTrue(success1)
            self.assertTrue(success2)  # Should still return True (idempotent)
            
            # Balance operation should only be called once
            self.assertEqual(mock_atomic_withdraw.call_count, 1)
    
    def test_get_pending_manual_withdrawals(self):
        """Test getting pending manual withdrawals."""
        # Create multiple withdrawals
        withdrawal1 = self.withdrawal_service.create_withdrawal(
            user_id=1, amount_usd=50.0, amount_ngn=75000.0,
            account_name="User 1", account_number="111", bank_name="Bank 1",
            bank_details_raw="User 1, 111, Bank 1", payment_mode=PaymentMode.MANUAL
        )
        
        withdrawal2 = self.withdrawal_service.create_withdrawal(
            user_id=1, amount_usd=100.0, amount_ngn=150000.0,
            account_name="User 1", account_number="222", bank_name="Bank 2",
            bank_details_raw="User 1, 222, Bank 2", payment_mode=PaymentMode.AUTOMATIC
        )
        
        withdrawal3 = self.withdrawal_service.create_withdrawal(
            user_id=1, amount_usd=25.0, amount_ngn=37500.0,
            account_name="User 1", account_number="333", bank_name="Bank 3",
            bank_details_raw="User 1, 333, Bank 3", payment_mode=PaymentMode.MANUAL
        )
        
        # Get pending manual withdrawals
        pending = self.withdrawal_service.get_pending_manual_withdrawals()
        
        # Should only return manual withdrawals that are pending
        self.assertEqual(len(pending), 2)
        pending_ids = [w.id for w in pending]
        self.assertIn(withdrawal1.id, pending_ids)
        self.assertIn(withdrawal3.id, pending_ids)
        self.assertNotIn(withdrawal2.id, pending_ids)  # Automatic withdrawal
    
    def test_audit_logging(self):
        """Test that audit events are logged."""
        withdrawal = self.withdrawal_service.create_withdrawal(
            user_id=1,
            amount_usd=50.0,
            amount_ngn=75000.0,
            account_name="Test User",
            account_number="1234567890",
            bank_name="Test Bank",
            bank_details_raw="Test User, 1234567890, Test Bank",
            payment_mode=PaymentMode.MANUAL
        )
        
        # Check that creation was logged
        with get_connection(self.db_file) as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM withdrawal_audit_log WHERE withdrawal_id = ?', (withdrawal.id,))
            audit_entries = c.fetchall()
            
            self.assertEqual(len(audit_entries), 1)
            entry = audit_entries[0]
            self.assertEqual(entry[3], "created")  # action column


if __name__ == '__main__':
    # Clean up any existing test database
    if os.path.exists(TEST_DB):
        os.unlink(TEST_DB)
    
    unittest.main()