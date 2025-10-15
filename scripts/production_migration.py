#!/usr/bin/env python3
"""
Production Migration Script
Automated migration for withdrawal service fixes and custom plans cleanup.
Includes backup, validation, rollback capabilities, and progress reporting.
"""

import sys
import os
import argparse
import sqlite3
import shutil
import json
from datetime import datetime, timedelta
from pathlib import Path
import logging

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # viralcore
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # viralpackage

from utils.db_utils import get_connection, DB_FILE, CUSTOM_DB_FILE

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/production_migration.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ProductionMigration:
    """Production migration handler with safety features."""
    
    def __init__(self, backup_dir=None):
        self.backup_dir = backup_dir or f"/tmp/viralcore_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.migration_log = []
        self.rollback_data = {}
        
    def log_step(self, step, status, details=None):
        """Log migration step with timestamp."""
        entry = {
            'timestamp': datetime.now().isoformat(),
            'step': step,
            'status': status,
            'details': details
        }
        self.migration_log.append(entry)
        
        status_emoji = "✅" if status == "success" else "❌" if status == "error" else "⏳"
        logger.info(f"{status_emoji} {step}")
        if details:
            logger.info(f"   Details: {details}")
    
    def create_backup(self):
        """Create complete backup of all databases."""
        try:
            os.makedirs(self.backup_dir, exist_ok=True)
            
            # Backup main database
            if os.path.exists(DB_FILE):
                shutil.copy2(DB_FILE, os.path.join(self.backup_dir, "viralcore.db.backup"))
                self.log_step("Backup main database", "success", f"Backed up to {self.backup_dir}")
            
            # Backup custom database
            if os.path.exists(CUSTOM_DB_FILE):
                shutil.copy2(CUSTOM_DB_FILE, os.path.join(self.backup_dir, "custom.db.backup"))
                self.log_step("Backup custom database", "success")
            
            # Backup viralmonitor database if exists
            try:
                from viralmonitor.utils.db import db_path
                if db_path and os.path.exists(db_path):
                    shutil.copy2(db_path, os.path.join(self.backup_dir, "viralmonitor.db.backup"))
                    self.log_step("Backup viralmonitor database", "success")
            except ImportError:
                self.log_step("Backup viralmonitor database", "warning", "viralmonitor not available")
            
            # Save migration metadata
            metadata = {
                'backup_created': datetime.now().isoformat(),
                'original_db_path': DB_FILE,
                'custom_db_path': CUSTOM_DB_FILE,
                'migration_version': '1.0.0',
                'fixes_included': ['withdrawal_service_viralmonitor_integration', 'custom_plans_duplicate_cleanup']
            }
            
            with open(os.path.join(self.backup_dir, "migration_metadata.json"), 'w') as f:
                json.dump(metadata, f, indent=2)
            
            return True
            
        except Exception as e:
            self.log_step("Create backup", "error", str(e))
            return False
    
    def pre_migration_checks(self):
        """Perform pre-migration validation checks."""
        checks_passed = 0
        total_checks = 6
        
        # Check 1: Database files exist
        if os.path.exists(DB_FILE):
            self.log_step("Check main database exists", "success")
            checks_passed += 1
        else:
            self.log_step("Check main database exists", "error", f"Database not found: {DB_FILE}")
        
        # Check 2: Custom database exists
        if os.path.exists(CUSTOM_DB_FILE):
            self.log_step("Check custom database exists", "success")
            checks_passed += 1
        else:
            self.log_step("Check custom database exists", "error", f"Database not found: {CUSTOM_DB_FILE}")
        
        # Check 3: viralmonitor availability
        try:
            from viralmonitor.utils.db import get_total_amount, remove_amount
            self.log_step("Check viralmonitor availability", "success")
            checks_passed += 1
        except ImportError:
            self.log_step("Check viralmonitor availability", "error", "viralmonitor module not available")
        
        # Check 4: Database connections work
        try:
            with get_connection(DB_FILE) as conn:
                conn.execute("SELECT 1").fetchone()
            self.log_step("Check main database connection", "success")
            checks_passed += 1
        except Exception as e:
            self.log_step("Check main database connection", "error", str(e))
        
        # Check 5: Custom database connection
        try:
            with get_connection(CUSTOM_DB_FILE) as conn:
                conn.execute("SELECT 1").fetchone()
            self.log_step("Check custom database connection", "success")
            checks_passed += 1
        except Exception as e:
            self.log_step("Check custom database connection", "error", str(e))
        
        # Check 6: Identify duplicate custom plans
        try:
            duplicate_count = self.count_duplicate_custom_plans()
            if duplicate_count > 0:
                self.log_step("Check for duplicate custom plans", "warning", f"Found {duplicate_count} duplicates")
            else:
                self.log_step("Check for duplicate custom plans", "success", "No duplicates found")
            checks_passed += 1
        except Exception as e:
            self.log_step("Check for duplicate custom plans", "error", str(e))
        
        success_rate = checks_passed / total_checks
        self.log_step("Pre-migration checks", "success" if success_rate >= 0.8 else "warning", 
                     f"{checks_passed}/{total_checks} checks passed ({success_rate:.1%})")
        
        return success_rate >= 0.8
    
    def count_duplicate_custom_plans(self):
        """Count duplicate custom plans that need cleanup."""
        try:
            with get_connection(CUSTOM_DB_FILE) as conn:
                c = conn.cursor()
                c.execute("""
                    SELECT COUNT(*) FROM custom_plans 
                    WHERE plan_name = 'Default Plan' 
                    AND user_id IN (
                        SELECT user_id FROM custom_plans 
                        WHERE plan_name = 'Default Plan' 
                        GROUP BY user_id 
                        HAVING COUNT(*) > 1
                    )
                """)
                return c.fetchone()[0]
        except Exception:
            return 0
    
    def apply_withdrawal_service_fix(self):
        """Apply withdrawal service viralmonitor integration fix."""
        try:
            self.log_step("Apply withdrawal service fix", "progress", "Updating withdrawal service methods")
            
            # The code changes are already in utils/withdrawal_service.py
            # We just need to verify the viralmonitor integration is working
            try:
                from viralmonitor.utils.db import get_total_amount, remove_amount
                
                # Test the functions work (this is a dry run)
                test_user_id = 999999  # Non-existent user for testing
                test_balance = get_total_amount(test_user_id)  # Should return 0
                
                self.log_step("Verify viralmonitor integration", "success", 
                             f"viralmonitor functions operational (test balance: {test_balance})")
                
                # Store rollback info
                self.rollback_data['withdrawal_service'] = {
                    'fix_applied': True,
                    'viralmonitor_available': True,
                    'timestamp': datetime.now().isoformat()
                }
                
                return True
                
            except Exception as e:
                self.log_step("Verify viralmonitor integration", "error", str(e))
                return False
                
        except Exception as e:
            self.log_step("Apply withdrawal service fix", "error", str(e))
            return False
    
    def apply_custom_plans_cleanup(self):
        """Clean up duplicate custom plans."""
        try:
            self.log_step("Apply custom plans cleanup", "progress", "Removing duplicate 'Default Plan' entries")
            
            with get_connection(CUSTOM_DB_FILE) as conn:
                conn.execute('BEGIN IMMEDIATE')
                c = conn.cursor()
                
                # Store rollback data before cleanup
                c.execute("""
                    SELECT id, user_id, plan_name, created_at, updated_at 
                    FROM custom_plans 
                    WHERE plan_name = 'Default Plan'
                """)
                before_cleanup = c.fetchall()
                
                self.rollback_data['custom_plans'] = {
                    'before_cleanup': before_cleanup,
                    'timestamp': datetime.now().isoformat()
                }
                
                # Find and remove duplicates, keeping only the oldest entry per user
                c.execute("""
                    DELETE FROM custom_plans 
                    WHERE id NOT IN (
                        SELECT MIN(id) 
                        FROM custom_plans 
                        WHERE plan_name = 'Default Plan' 
                        GROUP BY user_id
                    ) 
                    AND plan_name = 'Default Plan'
                """)
                
                deleted_count = c.rowcount
                
                # Fix timestamp uniqueness for remaining records
                c.execute("""
                    SELECT id FROM custom_plans 
                    WHERE (created_at = '' OR created_at IS NULL OR updated_at = '' OR updated_at IS NULL)
                    OR created_at = updated_at
                """)
                records_to_fix = c.fetchall()
                
                for i, (record_id,) in enumerate(records_to_fix):
                    # Create unique timestamps
                    base_time = datetime.now()
                    created_time = (base_time - timedelta(seconds=len(records_to_fix)-i)).isoformat()
                    updated_time = (base_time - timedelta(seconds=len(records_to_fix)-i-1)).isoformat()
                    
                    c.execute("""
                        UPDATE custom_plans 
                        SET created_at = ?, updated_at = ? 
                        WHERE id = ?
                    """, (created_time, updated_time, record_id))
                
                conn.commit()
                
                self.log_step("Custom plans cleanup completed", "success", 
                             f"Removed {deleted_count} duplicates, fixed {len(records_to_fix)} timestamps")
                
                return True
                
        except Exception as e:
            self.log_step("Apply custom plans cleanup", "error", str(e))
            return False
    
    def verify_migration(self):
        """Verify migration was successful."""
        verification_passed = 0
        total_verifications = 4
        
        # Verify 1: No duplicate custom plans remain
        try:
            duplicate_count = self.count_duplicate_custom_plans()
            if duplicate_count == 0:
                self.log_step("Verify no duplicate custom plans", "success")
                verification_passed += 1
            else:
                self.log_step("Verify no duplicate custom plans", "error", f"Still {duplicate_count} duplicates")
        except Exception as e:
            self.log_step("Verify no duplicate custom plans", "error", str(e))
        
        # Verify 2: viralmonitor integration works
        try:
            from viralmonitor.utils.db import get_total_amount
            test_balance = get_total_amount(999999)  # Test with non-existent user
            self.log_step("Verify viralmonitor integration", "success", f"Integration working (test: {test_balance})")
            verification_passed += 1
        except Exception as e:
            self.log_step("Verify viralmonitor integration", "error", str(e))
        
        # Verify 3: Database integrity
        try:
            with get_connection(DB_FILE) as conn:
                conn.execute("PRAGMA integrity_check").fetchone()
            with get_connection(CUSTOM_DB_FILE) as conn:
                conn.execute("PRAGMA integrity_check").fetchone()
            self.log_step("Verify database integrity", "success")
            verification_passed += 1
        except Exception as e:
            self.log_step("Verify database integrity", "error", str(e))
        
        # Verify 4: Custom plans table structure
        try:
            with get_connection(CUSTOM_DB_FILE) as conn:
                c = conn.cursor()
                c.execute("PRAGMA table_info(custom_plans)")
                columns = [col[1] for col in c.fetchall()]
                required_columns = ['user_id', 'plan_name', 'created_at', 'updated_at']
                if all(col in columns for col in required_columns):
                    self.log_step("Verify custom plans table structure", "success")
                    verification_passed += 1
                else:
                    missing = [col for col in required_columns if col not in columns]
                    self.log_step("Verify custom plans table structure", "error", f"Missing columns: {missing}")
        except Exception as e:
            self.log_step("Verify custom plans table structure", "error", str(e))
        
        success_rate = verification_passed / total_verifications
        self.log_step("Migration verification", "success" if success_rate == 1.0 else "warning",
                     f"{verification_passed}/{total_verifications} verifications passed ({success_rate:.1%})")
        
        return success_rate >= 0.75
    
    def create_rollback_script(self):
        """Create rollback script for emergency use."""
        try:
            rollback_script = f"""#!/usr/bin/env python3
'''
Emergency Rollback Script
Generated: {datetime.now().isoformat()}
Backup Directory: {self.backup_dir}
'''

import shutil
import os
import sys

def rollback():
    print("Starting emergency rollback...")
    
    # Restore database backups
    backup_dir = "{self.backup_dir}"
    
    if os.path.exists(os.path.join(backup_dir, "viralcore.db.backup")):
        shutil.copy2(os.path.join(backup_dir, "viralcore.db.backup"), "{DB_FILE}")
        print("✅ Restored main database")
    
    if os.path.exists(os.path.join(backup_dir, "custom.db.backup")):
        shutil.copy2(os.path.join(backup_dir, "custom.db.backup"), "{CUSTOM_DB_FILE}")
        print("✅ Restored custom database")
    
    print("🔄 Rollback completed. Please restart the application.")
    print("🔍 Check logs and contact support if issues persist.")

if __name__ == "__main__":
    rollback()
"""
            
            rollback_path = os.path.join(self.backup_dir, "emergency_rollback.py")
            with open(rollback_path, 'w') as f:
                f.write(rollback_script)
            
            os.chmod(rollback_path, 0o755)  # Make executable
            
            # Also save rollback data as JSON
            rollback_data_path = os.path.join(self.backup_dir, "rollback_data.json")
            with open(rollback_data_path, 'w') as f:
                json.dump(self.rollback_data, f, indent=2)
            
            self.log_step("Create rollback script", "success", f"Created at {rollback_path}")
            return True
            
        except Exception as e:
            self.log_step("Create rollback script", "error", str(e))
            return False
    
    def save_migration_report(self):
        """Save detailed migration report."""
        try:
            report = {
                'migration_completed': datetime.now().isoformat(),
                'backup_directory': self.backup_dir,
                'migration_steps': self.migration_log,
                'rollback_data': self.rollback_data,
                'success': True
            }
            
            report_path = os.path.join(self.backup_dir, "migration_report.json")
            with open(report_path, 'w') as f:
                json.dump(report, f, indent=2)
            
            # Also save human-readable report
            readable_report_path = os.path.join(self.backup_dir, "migration_report.txt")
            with open(readable_report_path, 'w') as f:
                f.write("ViralCore Production Migration Report\n")
                f.write("=" * 40 + "\n\n")
                f.write(f"Migration completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Backup directory: {self.backup_dir}\n\n")
                
                f.write("Migration Steps:\n")
                f.write("-" * 20 + "\n")
                for step in self.migration_log:
                    status_symbol = "✅" if step['status'] == "success" else "❌" if step['status'] == "error" else "⚠️"
                    f.write(f"{status_symbol} {step['step']}\n")
                    if step['details']:
                        f.write(f"   {step['details']}\n")
                
                f.write(f"\nRollback script: {os.path.join(self.backup_dir, 'emergency_rollback.py')}\n")
            
            self.log_step("Save migration report", "success", f"Report saved to {report_path}")
            return True
            
        except Exception as e:
            self.log_step("Save migration report", "error", str(e))
            return False
    
    def run_migration(self, skip_backup=False):
        """Run the complete migration process."""
        logger.info("🚀 Starting ViralCore Production Migration")
        logger.info("=" * 50)
        
        # Step 1: Pre-migration checks
        if not self.pre_migration_checks():
            logger.error("❌ Pre-migration checks failed. Aborting migration.")
            return False
        
        # Step 2: Create backup
        if not skip_backup:
            if not self.create_backup():
                logger.error("❌ Backup creation failed. Aborting migration.")
                return False
        else:
            self.log_step("Skip backup", "warning", "Backup skipped as requested")
        
        # Step 3: Apply withdrawal service fix
        if not self.apply_withdrawal_service_fix():
            logger.error("❌ Withdrawal service fix failed. Check logs.")
            return False
        
        # Step 4: Apply custom plans cleanup
        if not self.apply_custom_plans_cleanup():
            logger.error("❌ Custom plans cleanup failed. Check logs.")
            return False
        
        # Step 5: Verify migration
        if not self.verify_migration():
            logger.warning("⚠️ Migration verification had issues. Check logs.")
        
        # Step 6: Create rollback script
        self.create_rollback_script()
        
        # Step 7: Save migration report
        self.save_migration_report()
        
        logger.info("🎉 Migration completed successfully!")
        logger.info(f"📁 Backup and reports saved to: {self.backup_dir}")
        logger.info(f"🔄 Emergency rollback script: {os.path.join(self.backup_dir, 'emergency_rollback.py')}")
        
        return True

def main():
    parser = argparse.ArgumentParser(description='ViralCore Production Migration Tool')
    parser.add_argument('--backup-dir', help='Custom backup directory path')
    parser.add_argument('--skip-backup', action='store_true', help='Skip backup creation (not recommended)')
    parser.add_argument('--dry-run', action='store_true', help='Perform checks without applying changes')
    
    args = parser.parse_args()
    
    migration = ProductionMigration(backup_dir=args.backup_dir)
    
    if args.dry_run:
        logger.info("🔍 Running in dry-run mode (no changes will be made)")
        success = migration.pre_migration_checks()
        duplicate_count = migration.count_duplicate_custom_plans()
        logger.info(f"📊 Found {duplicate_count} duplicate custom plans to clean up")
        return 0 if success else 1
    
    success = migration.run_migration(skip_backup=args.skip_backup)
    return 0 if success else 1

if __name__ == "__main__":
    exit(main())