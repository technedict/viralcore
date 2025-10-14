#!/usr/bin/env python3
"""
Fix existing custom plan purchase records to use proper post counts.
"""

from utils.db_utils import get_connection, DB_FILE, CUSTOM_DB_FILE

def fix_existing_custom_plan_purchases():
    """
    Update existing custom plan purchase records to use proper post counts from custom_plans table.
    """
    print("Fixing existing custom plan purchase records...")
    
    # Get all custom plans with their max_posts
    with get_connection(CUSTOM_DB_FILE) as custom_conn:
        c = custom_conn.cursor()
        c.execute("""
            SELECT user_id, max_posts FROM custom_plans 
            WHERE is_active = 1
            GROUP BY user_id
        """)
        user_posts = {row['user_id']: row['max_posts'] for row in c.fetchall()}
    
    print(f"Found {len(user_posts)} users with custom plans")
    
    # Update purchase records for these users
    with get_connection(DB_FILE) as main_conn:
        c = main_conn.cursor()
        
        for user_id, max_posts in user_posts.items():
            # Update existing 'ct' purchase records for this user
            c.execute("""
                UPDATE purchases 
                SET quantity = ?, posts = ?, rposts = ?
                WHERE user_id = ? AND plan_type = 'ct'
            """, (max_posts, max_posts, max_posts, user_id))
            
            rows_updated = c.rowcount
            if rows_updated > 0:
                print(f"Updated {rows_updated} purchase record(s) for user {user_id} to {max_posts} posts")
        
        main_conn.commit()
    
    print("✅ Custom plan purchase records updated!")

def test_updated_records():
    """
    Test that the updated records work correctly.
    """
    print("\n=== Testing Updated Records ===")
    
    # Check purchase records
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT user_id, plan_type, quantity, posts, rposts 
            FROM purchases WHERE plan_type = 'ct'
            ORDER BY user_id
        """)
        purchases = c.fetchall()
    
    print("Custom plan purchase records:")
    for purchase in purchases:
        print(f"  User {purchase['user_id']}: {purchase['rposts']} remaining posts out of {purchase['posts']}")
    
    # Test with a specific user
    test_user_id = 5137148238
    from utils.db_utils import get_latest_tier_for_x, decrement_x_rpost
    
    # Make sure user has a username set
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            UPDATE purchases 
            SET x_username = 'testuser123' 
            WHERE user_id = ? AND plan_type = 'ct' AND (x_username = '' OR x_username IS NULL)
        """, (test_user_id,))
        conn.commit()
    
    # Test the flow
    tier, rposts = get_latest_tier_for_x(test_user_id, 'testuser123')
    print(f"\nTest user {test_user_id}: tier={tier}, rposts={rposts}")
    
    if tier == 'ct' and rposts and rposts <= 50:
        print("✅ Custom plan has proper post limit!")
        
        # Test decrementing
        print("Testing post decrementing...")
        new_rposts = decrement_x_rpost(test_user_id, 'testuser123')
        print(f"After one post: {new_rposts} remaining")
        
        if new_rposts == rposts - 1:
            print("✅ Posts decrement correctly!")
        else:
            print("❌ Posts not decrementing properly")
    else:
        print("❌ Custom plan test failed")

if __name__ == "__main__":
    fix_existing_custom_plan_purchases()
    test_updated_records()