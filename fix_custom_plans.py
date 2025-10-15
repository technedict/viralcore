#!/usr/bin/env python3
"""
Quick fix script for the production custom_plans table error.
Run this on the production server to resolve the "no such column: is_active" error.

Usage: python3 fix_custom_plans.py
"""

import sys
import os

# Add the viralcore directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def main():
    print("ViralCore Custom Plans Fix")
    print("=" * 40)
    
    try:
        # Run the custom plans base migration
        from scripts.migrate_database import apply_custom_plans_base_migration
        
        print("Applying custom plans schema migration...")
        success = apply_custom_plans_base_migration()
        
        if success:
            print("✅ Migration completed successfully!")
            
            # Test that init_custom_db works now
            print("Testing database initialization...")
            from utils.db_utils import init_custom_db
            init_custom_db()
            
            print("✅ Database initialization successful!")
            print("\nThe bot should now start without errors.")
            
        else:
            print("❌ Migration failed. Please check the error messages above.")
            return 1
            
    except Exception as e:
        print(f"❌ Error during migration: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())