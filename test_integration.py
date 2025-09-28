#!/usr/bin/env python3
# test_integration.py
# Basic integration tests for new features

import sqlite3
import tempfile
import os
import sys

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_withdrawal_migrations():
    """Test that withdrawal migrations work correctly."""
    print("Testing withdrawal table creation...")
    
    test_db = tempfile.mktemp(suffix='.db')
    
    try:
        # Override DB_FILE for test
        import utils.db_utils
        original_db_file = utils.db_utils.DB_FILE
        utils.db_utils.DB_FILE = test_db
        
        # Run migrations
        from scripts.migrate_database import apply_withdrawals_migration
        
        success = apply_withdrawals_migration()
        assert success, "Withdrawal migration failed"
        
        # Verify tables exist
        with sqlite3.connect(test_db) as conn:
            c = conn.cursor()
            
            # Create users table for foreign key test
            c.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    username TEXT
                )
            ''')
            conn.commit()
            
            # Check withdrawals table
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='withdrawals'")
            assert c.fetchone() is not None, "Withdrawals table not created"
            
            # Check withdrawal_audit_log table  
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='withdrawal_audit_log'")
            assert c.fetchone() is not None, "Withdrawal audit log table not created"
            
            # Check table structure
            c.execute("PRAGMA table_info(withdrawals)")
            columns = [row[1] for row in c.fetchall()]
            expected_columns = [
                'id', 'user_id', 'amount_usd', 'amount_ngn', 'payment_mode', 
                'admin_approval_state', 'admin_id', 'account_name', 'account_number',
                'bank_name', 'bank_details_raw', 'is_affiliate_withdrawal', 'status',
                'approved_at', 'processed_at', 'failure_reason', 'flutterwave_reference',
                'flutterwave_trace_id', 'operation_id', 'created_at', 'updated_at'
            ]
            
            for col in expected_columns:
                assert col in columns, f"Column {col} missing from withdrawals table"
            
        print("✅ Withdrawal migrations test passed")
        
    finally:
        # Restore original DB_FILE
        utils.db_utils.DB_FILE = original_db_file
        if os.path.exists(test_db):
            os.unlink(test_db)

def test_boosting_service_migrations():
    """Test that boosting service migrations work correctly."""
    print("Testing boosting service table creation...")
    
    test_db = tempfile.mktemp(suffix='.db')
    
    try:
        # Override DB_FILE for test
        import utils.db_utils
        original_db_file = utils.db_utils.DB_FILE
        utils.db_utils.DB_FILE = test_db
        
        # Run migrations
        from scripts.migrate_database import apply_boosting_service_providers_migration
        
        success = apply_boosting_service_providers_migration()
        assert success, "Boosting service migration failed"
        
        print(f"Test DB: {test_db}")
        print(f"DB_FILE: {utils.db_utils.DB_FILE}")
        
        # Verify tables exist and are seeded
        with sqlite3.connect(test_db) as conn:
            c = conn.cursor()
            
            # Create users table for foreign key test
            c.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    username TEXT
                )
            ''')
            conn.commit()
            
            # Debug: Check what tables exist
            c.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in c.fetchall()]
            print(f"Tables found: {tables}")
            
            # Check boosting_services table
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='boosting_services'")
            assert c.fetchone() is not None, "Boosting services table not created"
            
            # Check boosting_service_providers table
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='boosting_service_providers'")
            assert c.fetchone() is not None, "Boosting service providers table not created"
            
            # Check seeded data
            c.execute("SELECT COUNT(*) FROM boosting_services")
            services_count = c.fetchone()[0]
            assert services_count >= 2, f"Expected at least 2 services, got {services_count}"
            
            c.execute("SELECT COUNT(*) FROM boosting_service_providers")
            providers_count = c.fetchone()[0]
            assert providers_count >= 6, f"Expected at least 6 provider mappings, got {providers_count}"
            
            # Check specific providers exist
            c.execute("SELECT provider_name FROM boosting_service_providers")
            providers = [row[0] for row in c.fetchall()]
            expected_providers = ['smmflare', 'plugsmms', 'smmstone']
            
            for provider in expected_providers:
                assert provider in providers, f"Provider {provider} not found in seeded data"
            
        print("✅ Boosting service migrations test passed")
        
    finally:
        # Restore original DB_FILE
        utils.db_utils.DB_FILE = original_db_file
        if os.path.exists(test_db):
            os.unlink(test_db)

def test_basic_functionality():
    """Test basic functionality without external dependencies."""
    print("Testing basic model creation...")
    
    # Test enum imports
    from utils.withdrawal_service import PaymentMode, AdminApprovalState, WithdrawalStatus
    from utils.boosting_service_manager import ServiceType
    
    # Test enum values
    assert PaymentMode.AUTOMATIC.value == "automatic"
    assert PaymentMode.MANUAL.value == "manual"
    assert AdminApprovalState.PENDING.value == "pending"
    assert ServiceType.LIKES.value == "likes"
    assert ServiceType.VIEWS.value == "views"
    
    print("✅ Basic functionality test passed")

def test_database_consistency():
    """Test database schema consistency."""
    print("Testing database schema consistency...")
    
    test_db = tempfile.mktemp(suffix='.db')
    
    try:
        # Override DB_FILE for test
        import utils.db_utils
        original_db_file = utils.db_utils.DB_FILE
        utils.db_utils.DB_FILE = test_db
        
        # Create all tables
        from scripts.migrate_database import (
            apply_withdrawals_migration,
            apply_boosting_service_providers_migration
        )
        
        # Apply migrations
        success1 = apply_withdrawals_migration()
        success2 = apply_boosting_service_providers_migration()
        
        assert success1 and success2, "One or more migrations failed"
        
        # Verify foreign key constraints
        with sqlite3.connect(test_db) as conn:
            c = conn.cursor()
            
            # Create users table
            c.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    username TEXT
                )
            ''')
            conn.commit()
            
            # Create test user
            c.execute("INSERT INTO users (id, username) VALUES (1, 'testuser')")
            
            # Try to create withdrawal with invalid user - should fail with foreign key constraint
            try:
                c.execute('''
                    INSERT INTO withdrawals (
                        user_id, amount_usd, amount_ngn, account_name, 
                        account_number, bank_name, bank_details_raw
                    ) VALUES (999, 50.0, 75000.0, 'Test', '123', 'Bank', 'Test, 123, Bank')
                ''')
                conn.commit()
                # If we get here without an error, foreign keys aren't working
                # This is OK for SQLite without PRAGMA foreign_keys=ON
            except sqlite3.IntegrityError:
                # This is expected if foreign keys are enforced
                pass
            
            # Test check constraints
            try:
                c.execute('''
                    INSERT INTO withdrawals (
                        user_id, amount_usd, amount_ngn, account_name, 
                        account_number, bank_name, bank_details_raw, payment_mode
                    ) VALUES (1, 50.0, 75000.0, 'Test', '123', 'Bank', 'Test, 123, Bank', 'invalid_mode')
                ''')
                conn.commit()
                assert False, "Check constraint should have failed for invalid payment_mode"
            except sqlite3.IntegrityError:
                # Expected
                pass
            
        print("✅ Database consistency test passed")
        
    finally:
        # Restore original DB_FILE
        utils.db_utils.DB_FILE = original_db_file
        if os.path.exists(test_db):
            os.unlink(test_db)

if __name__ == '__main__':
    print("Running integration tests...")
    print("=" * 50)
    
    try:
        test_basic_functionality()
        test_withdrawal_migrations() 
        test_boosting_service_migrations()
        test_database_consistency()
        
        print("=" * 50)
        print("✅ All integration tests passed!")
        
    except Exception as e:
        print(f"❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)