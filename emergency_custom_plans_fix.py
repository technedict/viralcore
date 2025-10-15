#!/usr/bin/env python3
"""
Emergency fix for production custom_plans table missing columns.
This fixes the "no such column: plan_name" error.

Usage: python3 emergency_custom_plans_fix.py
"""

import sys
import os
import sqlite3

# Add the viralcore directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def main():
    print("Emergency Custom Plans Fix")
    print("=" * 40)
    
    try:
        from utils.db_utils import CUSTOM_DB_FILE
        
        print(f"Checking custom plans table at: {CUSTOM_DB_FILE}")
        
        # Check current schema
        with sqlite3.connect(CUSTOM_DB_FILE) as conn:
            c = conn.cursor()
            
            # Check if table exists
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='custom_plans'")
            table_exists = c.fetchone() is not None
            
            if not table_exists:
                print("❌ custom_plans table does not exist!")
                print("Creating new table with full schema...")
                
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
                        max_posts INTEGER DEFAULT 50,
                        UNIQUE(user_id, plan_name)
                    )
                ''')
                print("✅ Created custom_plans table with full schema")
                
            else:
                print("✅ custom_plans table exists, checking columns...")
                
                # Get current columns
                c.execute("PRAGMA table_info(custom_plans)")
                columns = [col[1] for col in c.fetchall()]
                print(f"Current columns: {columns}")
                
                # Check and add missing columns
                missing_columns = []
                
                if 'plan_name' not in columns:
                    c.execute("ALTER TABLE custom_plans ADD COLUMN plan_name TEXT DEFAULT 'Default Plan'")
                    missing_columns.append('plan_name')
                    
                if 'is_active' not in columns:
                    c.execute("ALTER TABLE custom_plans ADD COLUMN is_active INTEGER DEFAULT 1")
                    missing_columns.append('is_active')
                    
                if 'created_at' not in columns:
                    c.execute("ALTER TABLE custom_plans ADD COLUMN created_at TEXT DEFAULT ''")
                    missing_columns.append('created_at')
                    
                if 'updated_at' not in columns:
                    c.execute("ALTER TABLE custom_plans ADD COLUMN updated_at TEXT DEFAULT ''")
                    missing_columns.append('updated_at')
                    
                if 'max_posts' not in columns:
                    c.execute("ALTER TABLE custom_plans ADD COLUMN max_posts INTEGER DEFAULT 50")
                    missing_columns.append('max_posts')
                
                if missing_columns:
                    print(f"✅ Added missing columns: {missing_columns}")
                    
                    # Update timestamps for existing records
                    from datetime import datetime
                    current_time = datetime.now().isoformat()
                    
                    if 'created_at' in missing_columns:
                        c.execute("UPDATE custom_plans SET created_at = ? WHERE created_at = '' OR created_at IS NULL", (current_time,))
                    if 'updated_at' in missing_columns:
                        c.execute("UPDATE custom_plans SET updated_at = ? WHERE updated_at = '' OR updated_at IS NULL", (current_time,))
                        
                else:
                    print("✅ All required columns already exist")
            
            conn.commit()
        
        # Test the functions
        print("\\nTesting database functions...")
        from utils.db_utils import get_user_custom_plans, get_custom_plan, init_custom_db
        
        # Test init_custom_db
        init_custom_db()
        print("✅ init_custom_db() works correctly")
        
        # Test query functions
        plans = get_user_custom_plans(1)
        print(f"✅ get_user_custom_plans() works correctly (found {len(plans)} plans)")
        
        targets = get_custom_plan(1)
        print(f"✅ get_custom_plan() works correctly (targets: {targets})")
        
        print("\\n🎉 Emergency fix completed successfully!")
        print("The bot should now start without custom_plans table errors.")
        
    except Exception as e:
        print(f"❌ Error during fix: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())