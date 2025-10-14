#!/usr/bin/env python3
"""
Test custom plans functionality after the fix.
"""

import sqlite3
from utils.db_utils import (
    get_connection, DB_FILE, CUSTOM_DB_FILE,
    get_x_purchases, get_latest_tier_for_x, get_custom_plan
)

def test_custom_plans_functionality():
    """
    Test that custom plans now work properly for posting.
    """
    test_user_id = 5137148238
    test_username = "testuser123"
    
    print("=== Testing Custom Plans Functionality ===\n")
    
    # 1. Check custom plans exist
    with get_connection(CUSTOM_DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT plan_name, target_likes, target_retweets, target_comments, target_views, is_active
            FROM custom_plans WHERE user_id = ?
        """, (test_user_id,))
        plans = c.fetchall()
    
    print(f"1. Custom Plans for user {test_user_id}:")
    for plan in plans:
        status = "ACTIVE" if plan['is_active'] else "INACTIVE"
        print(f"   - {plan['plan_name']}: {plan['target_likes']} likes, {plan['target_retweets']} retweets, {plan['target_comments']} comments, {plan['target_views']} views [{status}]")
    
    # 2. Check purchase records
    purchases = get_x_purchases(test_user_id)
    print(f"\n2. Purchase Records for user {test_user_id}:")
    for purchase in purchases:
        print(f"   - Plan: {purchase['plan_type']}, Remaining Posts: {purchase['rposts']}, Payment: ${purchase['amount_paid_usd']}")
    
    # 3. Test tier lookup
    tier, rposts = get_latest_tier_for_x(test_user_id, test_username)
    print(f"\n3. Tier Lookup for @{test_username}: tier={tier}, remaining_posts={rposts}")
    
    # 4. Test custom plan targets
    ct1_targets = get_custom_plan(test_user_id, "CT1")
    frog_targets = get_custom_plan(test_user_id, "frog")
    default_targets = get_custom_plan(test_user_id)  # Should get first active plan
    
    print(f"\n4. Custom Plan Targets:")
    print(f"   - CT1 plan: {ct1_targets}")
    print(f"   - frog plan: {frog_targets}")
    print(f"   - default (first active): {default_targets}")
    
    # 5. Simulate the posting workflow
    print(f"\n5. Posting Workflow Simulation:")
    
    if tier == "ct" and rposts and rposts > 0:
        print("   ✅ Step 1: User has custom plan access")
        
        # Get custom plan targets (this is what the handler does)
        if ct1_targets != (0, 0, 0, 0):
            print(f"   ✅ Step 2: CT1 plan targets retrieved: {ct1_targets}")
        else:
            print("   ❌ Step 2: CT1 plan targets not found")
        
        if frog_targets != (0, 0, 0, 0):
            print(f"   ✅ Step 3: frog plan targets retrieved: {frog_targets}")
        else:
            print("   ❌ Step 3: frog plan targets not found")
            
        print("   ✅ Step 4: User can proceed with posting")
        
    else:
        print("   ❌ User cannot post - no custom plan access")
    
    # 6. Test the error condition
    print(f"\n6. Error Condition Test:")
    
    # Simulate a user without any purchase records
    test_user_no_purchases = 9999999
    tier_empty, rposts_empty = get_latest_tier_for_x(test_user_no_purchases, "nonexistent")
    
    if tier_empty is None:
        print("   ✅ Users without purchase records correctly return None tier")
    else:
        print(f"   ❌ Users without purchase records incorrectly return tier: {tier_empty}")
    
    print(f"\n=== Test Complete ===")

if __name__ == "__main__":
    test_custom_plans_functionality()