#!/usr/bin/env python3
"""
Test custom plans selection flow.
"""

from utils.db_utils import get_user_custom_plans, get_custom_plan, get_latest_tier_for_x

def test_custom_plans_flow():
    """
    Test the complete custom plans selection flow.
    """
    test_user_id = 5137148238
    test_username = "testuser123"
    
    print("=== Testing Custom Plans Selection Flow ===\n")
    
    # 1. Check if user has custom plans
    custom_plans = get_user_custom_plans(test_user_id, active_only=True)
    print(f"1. User has {len(custom_plans)} active custom plans:")
    for plan in custom_plans:
        print(f"   - {plan['plan_name']}: {plan['target_likes']}L, {plan['target_retweets']}RT, {plan['target_comments']}C, {plan['target_views']}V")
    
    # 2. Check what tier the user gets
    tier, rposts = get_latest_tier_for_x(test_user_id, test_username)
    print(f"\n2. User's tier for @{test_username}: {tier} (rposts: {rposts})")
    
    # 3. Test custom plan selection logic
    print(f"\n3. Testing custom plan selection logic:")
    
    # Simulate no plan selected (None)
    selected_plan = None
    if selected_plan is None:
        print(f"   - No plan selected → Should show plan selection menu")
    else:
        print(f"   - Plan '{selected_plan}' already selected")
    
    # Simulate plan selection
    for plan in custom_plans:
        plan_name = plan['plan_name']
        targets = get_custom_plan(test_user_id, plan_name)
        print(f"   - Plan '{plan_name}' targets: {targets}")
    
    # 4. Test invalid plan name
    invalid_targets = get_custom_plan(test_user_id, "nonexistent")
    print(f"   - Invalid plan 'nonexistent' targets: {invalid_targets}")
    
    print(f"\n✅ Custom plans selection flow test complete!")

if __name__ == "__main__":
    test_custom_plans_flow()