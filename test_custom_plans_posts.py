#!/usr/bin/env python3
"""
Test script to debug custom plans post counting issue.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.db_utils import (
    get_x_purchases, get_latest_tier_for_x, get_custom_plan, 
    get_user_custom_plans, get_connection, DB_FILE
)

def debug_custom_plans_posts(user_id):
    """Debug why custom plans users see 'no remaining posts'."""
    print(f"🔍 Debugging Custom Plans for User ID: {user_id}")
    print("=" * 60)
    
    # 1. Check X purchases
    print("1. Checking X purchases...")
    x_purchases = get_x_purchases(user_id)
    print(f"   Found {len(x_purchases)} X purchases:")
    
    total_rposts = 0
    for i, purchase in enumerate(x_purchases):
        print(f"   Purchase {i+1}: {dict(purchase)}")
        total_rposts += purchase['rposts']
    
    print(f"   Total remaining posts from purchases: {total_rposts}")
    print()
    
    # 2. Check custom plans
    print("2. Checking custom plans...")
    custom_plans = get_user_custom_plans(user_id, active_only=True)
    print(f"   Found {len(custom_plans)} active custom plans:")
    
    for i, plan in enumerate(custom_plans):
        print(f"   Plan {i+1}: {plan}")
    print()
    
    # 3. Check for custom plan purchases (plan_type = 'ct')
    print("3. Checking custom plan purchases in database...")
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT plan_type, x_username, posts, rposts, amount_paid_usd, timestamp 
            FROM purchases 
            WHERE user_id = ? AND plan_type = 'ct'
            ORDER BY timestamp DESC
        """, (user_id,))
        
        ct_purchases = c.fetchall()
        print(f"   Found {len(ct_purchases)} custom plan purchases:")
        
        for i, purchase in enumerate(ct_purchases):
            print(f"   Custom Purchase {i+1}: {dict(purchase)}")
    print()
    
    # 4. Test with a specific X username
    print("4. Testing with X usernames...")
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT DISTINCT x_username FROM purchases WHERE user_id = ?", (user_id,))
        usernames = [row[0] for row in c.fetchall() if row[0]]
    
    if usernames:
        for username in usernames:
            tier, rposts = get_latest_tier_for_x(user_id, username)
            print(f"   Username @{username}: tier={tier}, rposts={rposts}")
    else:
        print("   No X usernames found in purchases")
    print()
    
    # 5. Check the validation logic
    print("5. Analyzing the problem...")
    if total_rposts <= 0:
        print("   ❌ PROBLEM: total_rposts <= 0 triggers 'no remaining posts' message")
        
        if len(custom_plans) > 0 and len(ct_purchases) == 0:
            print("   ⚠️  ROOT CAUSE: User has custom plans but no 'ct' purchase records!")
            print("   💡 SOLUTION: Custom plans need to create purchase records with plan_type='ct'")
        elif len(ct_purchases) > 0:
            print("   ⚠️  ROOT CAUSE: Custom plan purchases exist but have rposts=0")
            print("   💡 SOLUTION: Check why rposts are being decremented incorrectly")
    else:
        print("   ✅ No issue detected with post counting")

def test_with_sample_user():
    """Test with a sample user who has custom plans."""
    print("Testing custom plans post validation...")
    
    # Let's check for users with custom plans
    from utils.db_utils import CUSTOM_DB_FILE
    
    with get_connection(CUSTOM_DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT DISTINCT user_id FROM custom_plans WHERE is_active = 1 LIMIT 5")
        users_with_plans = [row[0] for row in c.fetchall()]
    
    if not users_with_plans:
        print("❌ No users with active custom plans found")
        return
    
    print(f"Found {len(users_with_plans)} users with custom plans")
    
    for user_id in users_with_plans:
        debug_custom_plans_posts(user_id)
        print("\n" + "="*60 + "\n")

if __name__ == "__main__":
    test_with_sample_user()