#!/usr/bin/env python3
"""
Test script to debug referral registration issues.
"""

import sys
import os
import sqlite3

# Add current directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.db_utils import create_user, get_user, get_connection, DB_FILE

def test_referral_system():
    """Test the referral system step by step."""
    print("=== Testing Referral System ===")
    
    # Test data
    referrer_id = 123456
    referrer_username = "test_referrer"
    referee_id = 789012
    referee_username = "test_referee"
    
    print(f"\n1. Creating referrer user: ID={referrer_id}, username={referrer_username}")
    create_user(referrer_id, referrer_username)
    
    # Verify referrer was created
    referrer_record = get_user(referrer_id)
    if referrer_record:
        print(f"   ✅ Referrer created: {dict(referrer_record)}")
    else:
        print(f"   ❌ Referrer not found!")
        return
    
    print(f"\n2. Creating referee user with referrer: ID={referee_id}, username={referee_username}, referrer={referrer_id}")
    create_user(referee_id, referee_username, referrer_id)
    
    # Verify referee was created with correct referrer
    referee_record = get_user(referee_id)
    if referee_record:
        print(f"   ✅ Referee created: {dict(referee_record)}")
        if referee_record['referrer'] == referrer_id:
            print(f"   ✅ Referrer correctly set: {referee_record['referrer']}")
        else:
            print(f"   ❌ Referrer mismatch: expected {referrer_id}, got {referee_record['referrer']}")
    else:
        print(f"   ❌ Referee not found!")
        return
    
    print(f"\n3. Checking database directly...")
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        
        # Check users table structure
        c.execute("PRAGMA table_info(users)")
        columns = c.fetchall()
        print(f"   Users table columns: {[col[1] for col in columns]}")
        
        # Check if referrer field exists and has data
        c.execute("SELECT id, username, referrer FROM users WHERE id IN (?, ?)", (referrer_id, referee_id))
        users = c.fetchall()
        print(f"   Direct query results:")
        for user in users:
            print(f"     ID: {user[0]}, Username: {user[1]}, Referrer: {user[2]}")
    
    print(f"\n4. Testing referral link format...")
    referral_link = f"/start ref_{referrer_id}"
    print(f"   Referral link: {referral_link}")
    
    # Simulate parsing the referral code (like in start_handler.py)
    parts = referral_link.split()
    referrer_parsed = None
    if len(parts) > 1 and parts[1].startswith("ref_"):
        try:
            referrer_parsed = int(parts[1][4:])
            print(f"   ✅ Referral code parsed correctly: {referrer_parsed}")
        except ValueError:
            print(f"   ❌ Failed to parse referral code")
            referrer_parsed = None
    
    if referrer_parsed == referrer_id:
        print(f"   ✅ Referral parsing works correctly")
    else:
        print(f"   ❌ Referral parsing failed: expected {referrer_id}, got {referrer_parsed}")

def check_existing_referrals():
    """Check existing referrals in the database."""
    print(f"\n=== Checking Existing Referrals ===")
    
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        
        # Count total users
        c.execute("SELECT COUNT(*) FROM users")
        total_users = c.fetchone()[0]
        print(f"Total users in database: {total_users}")
        
        # Count users with referrers
        c.execute("SELECT COUNT(*) FROM users WHERE referrer IS NOT NULL")
        users_with_referrers = c.fetchone()[0]
        print(f"Users with referrers: {users_with_referrers}")
        
        # Show some examples of users with referrers
        c.execute("SELECT id, username, referrer FROM users WHERE referrer IS NOT NULL LIMIT 10")
        referred_users = c.fetchall()
        if referred_users:
            print(f"Sample referred users:")
            for user in referred_users:
                print(f"  User ID: {user[0]}, Username: {user[1]}, Referrer: {user[2]}")
        else:
            print("No users with referrers found!")
        
        # Check for potential issues
        c.execute("""
            SELECT u1.id as user_id, u1.username as username, u1.referrer as referrer_id, u2.username as referrer_username
            FROM users u1 
            LEFT JOIN users u2 ON u1.referrer = u2.id 
            WHERE u1.referrer IS NOT NULL AND u2.id IS NULL
        """)
        invalid_referrers = c.fetchall()
        if invalid_referrers:
            print(f"\n⚠️  Users with invalid referrer IDs (referrer doesn't exist):")
            for user in invalid_referrers:
                print(f"  User ID: {user[0]}, Username: {user[1]}, Invalid Referrer ID: {user[2]}")

def cleanup_test_data():
    """Clean up test data."""
    print(f"\n=== Cleaning up test data ===")
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM users WHERE id IN (123456, 789012)")
        deleted = c.rowcount
        conn.commit()
        print(f"Deleted {deleted} test users")

if __name__ == "__main__":
    print("Starting referral system diagnostics...")
    
    # Check existing data first
    check_existing_referrals()
    
    # Run tests
    test_referral_system()
    
    # Clean up
    cleanup_test_data()
    
    print(f"\n=== Summary ===")
    print("If referrals are not registering, possible issues:")
    print("1. Users not using the correct /start ref_<user_id> format")
    print("2. Database connection issues")
    print("3. Race conditions during user creation")
    print("4. Frontend not generating referral links correctly")
    print("5. Bot restart clearing context data")