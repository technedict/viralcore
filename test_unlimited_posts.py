#!/usr/bin/env python3
"""
Test that custom plans now have truly unlimited posts.
"""

from utils.db_utils import (
    get_connection, DB_FILE, 
    decrement_x_rpost, get_latest_tier_for_x
)

def test_unlimited_custom_plans():
    """
    Test that custom plans don't get decremented and remain unlimited.
    """
    test_user_id = 5137148238
    test_username = "testuser123"
    
    print("=== Testing Unlimited Custom Plans ===\n")
    
    # Check initial state
    tier, rposts = get_latest_tier_for_x(test_user_id, test_username)
    print(f"Initial state: tier={tier}, rposts={rposts}")
    
    # Simulate multiple post submissions
    print(f"\nSimulating 5 post submissions:")
    for i in range(1, 6):
        new_rposts = decrement_x_rpost(test_user_id, test_username)
        print(f"  Post {i}: remaining posts = {new_rposts}")
    
    # Check final state
    tier_final, rposts_final = get_latest_tier_for_x(test_user_id, test_username)
    print(f"\nFinal state: tier={tier_final}, rposts={rposts_final}")
    
    # Verify purchase record still exists
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT plan_type, rposts FROM purchases 
            WHERE user_id = ? AND x_username = ?
        """, (test_user_id, test_username))
        record = c.fetchone()
    
    if record:
        print(f"Purchase record: plan_type={record['plan_type']}, rposts={record['rposts']}")
        
        if record['plan_type'] == 'ct' and record['rposts'] == rposts:
            print("✅ SUCCESS: Custom plan has unlimited posts!")
        else:
            print("❌ FAILED: Custom plan posts were decremented")
    else:
        print("❌ FAILED: Purchase record was deleted")

def test_regular_plan_decrements():
    """
    Test that regular plans still get decremented properly.
    """
    print(f"\n=== Testing Regular Plan Decrements ===\n")
    
    # Create a test regular plan purchase
    test_user_id = 8888888
    test_username = "regular_user"
    
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        
        # Delete any existing records for this test user
        c.execute("DELETE FROM purchases WHERE user_id = ?", (test_user_id,))
        
        # Create a T1 plan with 3 posts
        c.execute("""
            INSERT INTO purchases 
            (user_id, plan_type, quantity, amount_paid_usd, payment_method, 
             transaction_ref, timestamp, x_username, posts, rposts)
            VALUES (?, 't1', 3, 5.0, 'test', 'test_regular_plan', datetime('now'), ?, 3, 3)
        """, (test_user_id, test_username))
        conn.commit()
    
    # Test decrements
    print(f"Testing regular plan decrements:")
    for i in range(1, 5):
        tier, rposts = get_latest_tier_for_x(test_user_id, test_username)
        if tier is None:
            print(f"  Post {i}: No active plan (posts exhausted)")
            break
        
        new_rposts = decrement_x_rpost(test_user_id, test_username)
        print(f"  Post {i}: tier={tier}, remaining posts = {new_rposts}")
    
    # Final check
    tier_final, rposts_final = get_latest_tier_for_x(test_user_id, test_username)
    if tier_final is None:
        print("✅ SUCCESS: Regular plan was properly exhausted")
    else:
        print(f"❌ FAILED: Regular plan still active: tier={tier_final}, rposts={rposts_final}")

if __name__ == "__main__":
    test_unlimited_custom_plans()
    test_regular_plan_decrements()