#!/usr/bin/env python3
"""
Database Migration Script
Handles database schema migrations for ViralCore bot.
"""

import sys
import os
import argparse
import sqlite3
from datetime import datetime

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db_utils import get_connection, DB_FILE
from utils.balance_operations import init_operations_ledger
from viralmonitor.utils.db import init_reply_balance_db

def apply_balance_operations_migration():
    """Apply balance operations ledger migration."""
    print("Applying balance operations migration...")
    
    try:
        init_operations_ledger()
        print("✅ Balance operations ledger created/updated")
        return True
    except Exception as e:
        print(f"❌ Failed to apply balance operations migration: {e}")
        return False

def apply_reply_balance_migration():
    """Apply reply balance tracking migration."""
    print("Applying reply balance migration...")
    
    try:
        init_reply_balance_db()
        print("✅ Reply balance table created/updated")
        return True
    except Exception as e:
        print(f"❌ Failed to apply reply balance migration: {e}")
        return False

def apply_job_queue_migration():
    """Apply job queue migration."""
    print("Applying job queue migration...")
    
    try:
        from utils.graceful_shutdown import shutdown_manager
        shutdown_manager.init_job_queue()
        print("✅ Job queue table created/updated")
        return True
    except Exception as e:
        print(f"❌ Failed to apply job queue migration: {e}")
        return False

def apply_withdrawals_migration():
    """Apply withdrawals table migration with payment modes and admin approval."""
    print("Applying withdrawals migration...")
    
    try:
        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            
            # Create withdrawals table with new payment mode features
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
                    FOREIGN KEY (admin_id) REFERENCES users (id),
                    CHECK (payment_mode IN ('automatic', 'manual')),
                    CHECK (admin_approval_state IS NULL OR admin_approval_state IN ('pending', 'approved', 'rejected')),
                    CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'rejected'))
                );
            ''')
            
            # Create indexes for performance
            c.execute('CREATE INDEX IF NOT EXISTS idx_withdrawals_user_id ON withdrawals(user_id)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_withdrawals_status ON withdrawals(status)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_withdrawals_payment_mode ON withdrawals(payment_mode)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_withdrawals_admin_approval_state ON withdrawals(admin_approval_state)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_withdrawals_created_at ON withdrawals(created_at)')
            
            # Create withdrawal audit log table
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
                );
            ''')
            
            c.execute('CREATE INDEX IF NOT EXISTS idx_withdrawal_audit_withdrawal_id ON withdrawal_audit_log(withdrawal_id)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_withdrawal_audit_created_at ON withdrawal_audit_log(created_at)')
            
            conn.commit()
            
        print("✅ Withdrawals table and audit log created")
        return True
    except Exception as e:
        print(f"❌ Failed to apply withdrawals migration: {e}")
        return False

def apply_boosting_service_providers_migration():
    """Apply boosting service providers mapping migration."""
    print("Applying boosting service providers migration...")
    
    try:
        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            
            # Create boosting services table
            c.execute('''
                CREATE TABLE IF NOT EXISTS boosting_services (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    service_type TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                    CHECK (service_type IN ('likes', 'views', 'comments')),
                    CHECK (is_active IN (0, 1))
                );
            ''')
            
            # Create boosting service providers mapping table
            c.execute('''
                CREATE TABLE IF NOT EXISTS boosting_service_providers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    service_id INTEGER NOT NULL,
                    provider_name TEXT NOT NULL,
                    provider_service_id INTEGER NOT NULL,
                    created_by INTEGER DEFAULT NULL,
                    updated_by INTEGER DEFAULT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (service_id) REFERENCES boosting_services (id),
                    FOREIGN KEY (created_by) REFERENCES users (id),
                    FOREIGN KEY (updated_by) REFERENCES users (id),
                    UNIQUE(service_id, provider_name)
                );
            ''')
            
            # Create audit log for service provider changes
            c.execute('''
                CREATE TABLE IF NOT EXISTS boosting_service_audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    service_provider_id INTEGER NOT NULL,
                    admin_id INTEGER DEFAULT NULL,
                    action TEXT NOT NULL,
                    old_provider_service_id INTEGER DEFAULT NULL,
                    new_provider_service_id INTEGER DEFAULT NULL,
                    reason TEXT DEFAULT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (service_provider_id) REFERENCES boosting_service_providers (id),
                    FOREIGN KEY (admin_id) REFERENCES users (id)
                );
            ''')
            
            # Create indexes
            c.execute('CREATE INDEX IF NOT EXISTS idx_boosting_services_active ON boosting_services(is_active)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_boosting_service_providers_service_id ON boosting_service_providers(service_id)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_boosting_service_providers_provider ON boosting_service_providers(provider_name)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_boosting_service_audit_service_provider ON boosting_service_audit_log(service_provider_id)')
            
            # Seed initial data from current provider configuration
            c.execute('SELECT COUNT(*) FROM boosting_services')
            if c.fetchone()[0] == 0:
                # Insert default services
                c.execute('''
                    INSERT INTO boosting_services (name, service_type, is_active) 
                    VALUES 
                    ('Default Likes Service', 'likes', 1),
                    ('Default Views Service', 'views', 1)
                ''')
                
                # Get the inserted service IDs
                c.execute('SELECT id FROM boosting_services WHERE service_type = ?', ('likes',))
                likes_service_id = c.fetchone()[0]
                
                c.execute('SELECT id FROM boosting_services WHERE service_type = ?', ('views',))
                views_service_id = c.fetchone()[0]
                
                # Insert current provider mappings from boost_provider_utils.py
                providers = [
                    ('smmflare', 8646, 8381),  # like_service_id, view_service_id
                    ('plugsmms', 11023, 7750),
                    ('smmstone', 6662, 5480)
                ]
                
                for provider_name, like_id, view_id in providers:
                    c.execute('''
                        INSERT INTO boosting_service_providers 
                        (service_id, provider_name, provider_service_id, created_at, updated_at)
                        VALUES (?, ?, ?, datetime('now'), datetime('now'))
                    ''', (likes_service_id, provider_name, like_id))
                    
                    c.execute('''
                        INSERT INTO boosting_service_providers 
                        (service_id, provider_name, provider_service_id, created_at, updated_at)
                        VALUES (?, ?, ?, datetime('now'), datetime('now'))
                    ''', (views_service_id, provider_name, view_id))
            
            conn.commit()
            
        print("✅ Boosting service providers tables created and seeded")
        return True
    except Exception as e:
        print(f"❌ Failed to apply boosting service providers migration: {e}")
        return False

def check_migration_status():
    """Check which migrations have been applied."""
    print("Checking migration status...")
    
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        
        # Check for balance operations table
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='balance_operations'")
        balance_ops_exists = c.fetchone() is not None
        
        # Check for reply balance table
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='reply_balances'")
        reply_balance_exists = c.fetchone() is not None
        
        # Check for job queue table
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='job_queue'")
        job_queue_exists = c.fetchone() is not None
        
        # Check for withdrawals table
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='withdrawals'")
        withdrawals_exists = c.fetchone() is not None
        
        # Check for boosting service providers table
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='boosting_service_providers'")
        boosting_providers_exists = c.fetchone() is not None
        
        # Check for users table columns
        c.execute("PRAGMA table_info(users)")
        user_columns = [col[1] for col in c.fetchall()]
        has_affiliate_balance = 'affiliate_balance' in user_columns
        
        print("\nMigration Status:")
        print(f"  Balance Operations Ledger:     {'✅ Applied' if balance_ops_exists else '❌ Not Applied'}")
        print(f"  Reply Balance Tracking:        {'✅ Applied' if reply_balance_exists else '❌ Not Applied'}")
        print(f"  Job Queue System:              {'✅ Applied' if job_queue_exists else '❌ Not Applied'}")
        print(f"  User Affiliate Balance:        {'✅ Applied' if has_affiliate_balance else '❌ Not Applied'}")
        print(f"  Withdrawals System:            {'✅ Applied' if withdrawals_exists else '❌ Not Applied'}")
        print(f"  Boosting Service Providers:    {'✅ Applied' if boosting_providers_exists else '❌ Not Applied'}")
        
        return {
            'balance_operations': balance_ops_exists,
            'reply_balance': reply_balance_exists,
            'job_queue': job_queue_exists,
            'affiliate_balance': has_affiliate_balance,
            'withdrawals': withdrawals_exists,
            'boosting_providers': boosting_providers_exists
        }

def apply_all_migrations():
    """Apply all pending migrations."""
    print("Starting database migrations...")
    print("=" * 50)
    
    migrations_applied = 0
    migrations_failed = 0
    
    # Apply balance operations migration
    if apply_balance_operations_migration():
        migrations_applied += 1
    else:
        migrations_failed += 1
    
    # Apply reply balance migration
    if apply_reply_balance_migration():
        migrations_applied += 1
    else:
        migrations_failed += 1
    
    # Apply job queue migration
    if apply_job_queue_migration():
        migrations_applied += 1
    else:
        migrations_failed += 1
    
    # Apply withdrawals migration
    if apply_withdrawals_migration():
        migrations_applied += 1
    else:
        migrations_failed += 1
    
    # Apply boosting service providers migration
    if apply_boosting_service_providers_migration():
        migrations_applied += 1
    else:
        migrations_failed += 1
    
    print("\n" + "=" * 50)
    print(f"Migration Summary:")
    print(f"  Applied: {migrations_applied}")
    print(f"  Failed:  {migrations_failed}")
    
    if migrations_failed == 0:
        print("✅ All migrations completed successfully!")
        return True
    else:
        print("❌ Some migrations failed. Please check the errors above.")
        return False

def backup_database():
    """Create a backup of the database before migrations."""
    if not os.path.exists(DB_FILE):
        print("Database file does not exist, no backup needed.")
        return True
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"{DB_FILE}.backup_{timestamp}"
    
    try:
        # Simple file copy for SQLite
        import shutil
        shutil.copy2(DB_FILE, backup_file)
        print(f"✅ Database backed up to: {backup_file}")
        return True
    except Exception as e:
        print(f"❌ Failed to backup database: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Database Migration Tool')
    parser.add_argument('--check', action='store_true', help='Check migration status only')
    parser.add_argument('--backup', action='store_true', help='Create database backup before migration')
    parser.add_argument('--apply', action='store_true', help='Apply all pending migrations')
    parser.add_argument('--force', action='store_true', help='Force apply migrations even if they exist')
    
    args = parser.parse_args()
    
    print("ViralCore Database Migration Tool")
    print("=" * 40)
    
    # Check status first
    if args.check:
        check_migration_status()
        return 0
    
    # Create backup if requested
    if args.backup:
        if not backup_database():
            return 1
    
    # Apply migrations
    if args.apply:
        if not check_migration_status():
            print("\nChecking migration status failed!")
            return 1
        
        success = apply_all_migrations()
        return 0 if success else 1
    
    # Default: show status and prompt
    status = check_migration_status()
    
    pending_migrations = []
    if not status['balance_operations']:
        pending_migrations.append('Balance Operations Ledger')
    if not status['reply_balance']:
        pending_migrations.append('Reply Balance Tracking')
    if not status['job_queue']:
        pending_migrations.append('Job Queue System')
    if not status['withdrawals']:
        pending_migrations.append('Withdrawals System')
    if not status['boosting_providers']:
        pending_migrations.append('Boosting Service Providers')
    
    if pending_migrations:
        print(f"\nPending migrations: {', '.join(pending_migrations)}")
        print("\nTo apply migrations, run: python3 scripts/migrate_database.py --apply")
        print("To create a backup first: python3 scripts/migrate_database.py --backup --apply")
    else:
        print("\n✅ All migrations are up to date!")
    
    return 0

if __name__ == "__main__":
    exit(main())