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
from ViralMonitor.utils.db import init_reply_balance_db

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
        
        # Check for users table columns
        c.execute("PRAGMA table_info(users)")
        user_columns = [col[1] for col in c.fetchall()]
        has_affiliate_balance = 'affiliate_balance' in user_columns
        
        print("\nMigration Status:")
        print(f"  Balance Operations Ledger: {'✅ Applied' if balance_ops_exists else '❌ Not Applied'}")
        print(f"  Reply Balance Tracking:    {'✅ Applied' if reply_balance_exists else '❌ Not Applied'}")
        print(f"  Job Queue System:          {'✅ Applied' if job_queue_exists else '❌ Not Applied'}")
        print(f"  User Affiliate Balance:    {'✅ Applied' if has_affiliate_balance else '❌ Not Applied'}")
        
        return {
            'balance_operations': balance_ops_exists,
            'reply_balance': reply_balance_exists,
            'job_queue': job_queue_exists,
            'affiliate_balance': has_affiliate_balance
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
    
    if pending_migrations:
        print(f"\nPending migrations: {', '.join(pending_migrations)}")
        print("\nTo apply migrations, run: python3 scripts/migrate_database.py --apply")
        print("To create a backup first: python3 scripts/migrate_database.py --backup --apply")
    else:
        print("\n✅ All migrations are up to date!")
    
    return 0

if __name__ == "__main__":
    exit(main())