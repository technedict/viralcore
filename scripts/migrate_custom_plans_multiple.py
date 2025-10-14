#!/usr/bin/env python3
"""
Migration script to update custom_plans table to support multiple plans per user.

This script:
1. Backs up existing custom_plans data
2. Updates the table schema to remove UNIQUE constraint on user_id
3. Adds plan_name, created_at, updated_at, and is_active fields
4. Migrates existing data to new format with default plan names
"""

import sqlite3
import os
import shutil
from datetime import datetime
from pathlib import Path

# Import the CUSTOM_DB_FILE path
import sys
sys.path.append(str(Path(__file__).parent.parent))
from utils.db_utils import CUSTOM_DB_FILE, get_connection

def backup_custom_db():
    """Create a backup of the custom database before migration."""
    if not os.path.exists(CUSTOM_DB_FILE):
        print("Custom database doesn't exist yet, skipping backup.")
        return True
    
    backup_path = f"{CUSTOM_DB_FILE}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    try:
        shutil.copy2(CUSTOM_DB_FILE, backup_path)
        print(f"Custom database backed up to: {backup_path}")
        return True
    except Exception as e:
        print(f"Failed to backup custom database: {e}")
        return False

def migrate_custom_plans_table():
    """Migrate the custom_plans table to support multiple plans per user."""
    
    if not backup_custom_db():
        return False
    
    try:
        with get_connection(CUSTOM_DB_FILE) as conn:
            c = conn.cursor()
            
            # Check if migration is needed
            c.execute("PRAGMA table_info(custom_plans)")
            columns = [row[1] for row in c.fetchall()]
            
            if 'plan_name' in columns:
                print("Custom plans table already migrated to support multiple plans.")
                return True
            
            print("Starting custom plans table migration...")
            
            # Step 1: Create backup table with existing data
            c.execute('''
                CREATE TABLE IF NOT EXISTS custom_plans_backup AS 
                SELECT * FROM custom_plans
            ''')
            
            # Step 2: Get existing data
            c.execute("SELECT * FROM custom_plans")
            existing_data = c.fetchall()
            
            # Step 3: Drop the old table
            c.execute("DROP TABLE custom_plans")
            
            # Step 4: Create new table with updated schema
            c.execute('''
                CREATE TABLE custom_plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    plan_name TEXT NOT NULL,
                    target_likes INTEGER DEFAULT 0,
                    target_retweets INTEGER DEFAULT 0,
                    target_comments INTEGER DEFAULT 0,
                    target_views INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, plan_name)
                )
            ''')
            
            # Add indexes for better performance
            c.execute('CREATE INDEX IF NOT EXISTS idx_custom_plans_user_id ON custom_plans(user_id)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_custom_plans_active ON custom_plans(user_id, is_active)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_custom_plans_name ON custom_plans(user_id, plan_name)')
            
            # Step 5: Migrate existing data with default plan names
            current_time = datetime.utcnow().isoformat()
            
            for row in existing_data:
                # Assuming old schema: (id, user_id, target_likes, target_retweets, target_comments, target_views)
                old_id, user_id, target_likes, target_retweets, target_comments, target_views = row
                
                c.execute('''
                    INSERT INTO custom_plans 
                    (user_id, plan_name, target_likes, target_retweets, target_comments, target_views, is_active, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    user_id, 
                    "Default Plan",  # Default plan name for existing plans
                    target_likes, 
                    target_retweets, 
                    target_comments, 
                    target_views,
                    1,  # is_active = True
                    current_time,
                    current_time
                ))
            
            conn.commit()
            print(f"Successfully migrated {len(existing_data)} custom plans to new schema.")
            
            # Step 6: Clean up backup table (optional - keep for safety)
            # c.execute("DROP TABLE custom_plans_backup")
            
            return True
            
    except Exception as e:
        print(f"Error during custom plans migration: {e}")
        return False

def verify_migration():
    """Verify that the migration was successful."""
    try:
        with get_connection(CUSTOM_DB_FILE) as conn:
            c = conn.cursor()
            
            # Check table structure
            c.execute("PRAGMA table_info(custom_plans)")
            columns = {row[1]: row[2] for row in c.fetchall()}
            
            expected_columns = {
                'id': 'INTEGER',
                'user_id': 'INTEGER',
                'plan_name': 'TEXT',
                'target_likes': 'INTEGER',
                'target_retweets': 'INTEGER', 
                'target_comments': 'INTEGER',
                'target_views': 'INTEGER',
                'is_active': 'INTEGER',
                'created_at': 'TEXT',
                'updated_at': 'TEXT'
            }
            
            for col_name, col_type in expected_columns.items():
                if col_name not in columns:
                    print(f"ERROR: Missing column '{col_name}'")
                    return False
                    
            # Check data integrity
            c.execute("SELECT COUNT(*) FROM custom_plans")
            count = c.fetchone()[0]
            
            c.execute("SELECT COUNT(*) FROM custom_plans WHERE plan_name IS NOT NULL")
            named_count = c.fetchone()[0]
            
            if count != named_count:
                print(f"ERROR: Some plans missing plan_name. Total: {count}, Named: {named_count}")
                return False
                
            print(f"Migration verification successful. Found {count} custom plans.")
            return True
            
    except Exception as e:
        print(f"Error during migration verification: {e}")
        return False

def main():
    """Run the custom plans migration."""
    print("Starting custom plans multiple plans migration...")
    
    if not migrate_custom_plans_table():
        print("Migration failed!")
        return False
        
    if not verify_migration():
        print("Migration verification failed!")
        return False
        
    print("Custom plans migration completed successfully!")
    return True

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)