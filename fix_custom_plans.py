#!/usr/bin/env python3
"""
Fix custom plans by creating corresponding purchase records.

This script creates purchase records for existing custom plans so that
users with custom plans can actually use them to post content.
"""

import sqlite3
from datetime import datetime
from utils.db_utils import get_connection, DB_FILE, CUSTOM_DB_FILE

def fix_custom_plans():
    """
    Create purchase records for all active custom plans that don't have them.
    """
    # Get all active custom plans
    with get_connection(CUSTOM_DB_FILE) as custom_conn:
        c = custom_conn.cursor()
        c.execute("""
            SELECT user_id, plan_name, target_likes, target_retweets, target_comments, target_views
            FROM custom_plans 
            WHERE is_active = 1
        """)
        custom_plans = c.fetchall()
    
    if not custom_plans:
        print("No active custom plans found.")
        return
    
    print(f"Found {len(custom_plans)} active custom plans")
    
    # For each custom plan, check if purchase record exists and create if needed
    with get_connection(DB_FILE) as main_conn:
        c = main_conn.cursor()
        
        for plan in custom_plans:
            user_id = plan['user_id']
            plan_name = plan['plan_name']
            
            # Check if user already has a 'ct' purchase record
            c.execute("""
                SELECT COUNT(*) FROM purchases 
                WHERE user_id = ? AND plan_type = 'ct'
            """, (user_id,))
            
            existing_count = c.fetchone()[0]
            
            if existing_count == 0:
                print(f"Creating purchase record for user {user_id}, plan '{plan_name}'")
                
                # Create purchase record for custom plan
                # Use a high number of posts (9999) since custom plans don't have post limits
                c.execute("""
                    INSERT INTO purchases 
                    (user_id, plan_type, quantity, amount_paid_usd, payment_method, 
                     transaction_ref, timestamp, x_username, posts, rposts)
                    VALUES (?, 'ct', 9999, 0.0, 'custom_plan', ?, ?, '', 9999, 9999)
                """, (
                    user_id,
                    f"custom_plan_{user_id}_{plan_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    datetime.now().isoformat()
                ))
            else:
                print(f"User {user_id} already has {existing_count} 'ct' purchase record(s)")
        
        main_conn.commit()
        print("Purchase records created successfully!")

def test_custom_plan_user():
    """
    Test that a user with custom plans can now post.
    """
    test_user_id = 5137148238
    
    # Get user's purchases
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT plan_type, rposts, quantity FROM purchases 
            WHERE user_id = ? AND plan_type != 'tgt'
            ORDER BY timestamp DESC
        """, (test_user_id,))
        purchases = c.fetchall()
    
    print(f"\nPurchases for user {test_user_id}:")
    for purchase in purchases:
        print(f"  Plan: {purchase['plan_type']}, Remaining: {purchase['rposts']}, Quantity: {purchase['quantity']}")
    
    # Test get_latest_tier_for_x with a dummy username
    from utils.db_utils import get_latest_tier_for_x
    
    # First add the username to a purchase record
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            UPDATE purchases 
            SET x_username = 'testuser123' 
            WHERE user_id = ? AND plan_type = 'ct' AND x_username = ''
        """, (test_user_id,))
        conn.commit()
    
    tier, rposts = get_latest_tier_for_x(test_user_id, 'testuser123')
    print(f"\nTier check for testuser123: tier={tier}, rposts={rposts}")
    
    if tier == 'ct' and rposts and rposts > 0:
        print("✅ Custom plans fix successful! User can now post.")
    else:
        print("❌ Custom plans fix failed.")

if __name__ == "__main__":
    print("Fixing custom plans...")
    fix_custom_plans()
    test_custom_plan_user()