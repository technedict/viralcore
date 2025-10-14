#!/usr/bin/env python3
"""
Test script for multiple custom plans functionality.
"""

import sys
import os
sys.path.append('.')

from utils.db_utils import (
    init_custom_db, 
    create_custom_plan, 
    get_user_custom_plans, 
    get_custom_plan,
    update_custom_plan,
    delete_custom_plan
)

def test_multiple_custom_plans():
    """Test the multiple custom plans functionality."""
    
    print("=== Testing Multiple Custom Plans ===\n")
    
    # Initialize database
    print("1. Initializing custom database...")
    init_custom_db()
    print("✅ Database initialized\n")
    
    # Test user ID
    test_user_id = 12345
    
    # Test creating multiple plans
    print("2. Creating multiple custom plans...")
    
    plan1_success = create_custom_plan(
        user_id=test_user_id,
        plan_name="Viral Plan",
        likes=100,
        retweets=50,
        comments=25,
        views=10000
    )
    print(f"   Created 'Viral Plan': {plan1_success}")
    
    plan2_success = create_custom_plan(
        user_id=test_user_id,
        plan_name="Engagement Plan",
        likes=75,
        retweets=30,
        comments=15,
        views=5000
    )
    print(f"   Created 'Engagement Plan': {plan2_success}")
    
    plan3_success = create_custom_plan(
        user_id=test_user_id,
        plan_name="Budget Plan",
        likes=25,
        retweets=10,
        comments=5,
        views=2000
    )
    print(f"   Created 'Budget Plan': {plan3_success}")
    
    # Test duplicate plan name (should fail)
    duplicate_success = create_custom_plan(
        user_id=test_user_id,
        plan_name="Viral Plan",  # Same name
        likes=200,
        retweets=100,
        comments=50,
        views=20000
    )
    print(f"   Tried to create duplicate 'Viral Plan': {duplicate_success} (should be False)")
    print()
    
    # Test getting all plans
    print("3. Getting all custom plans...")
    all_plans = get_user_custom_plans(test_user_id, active_only=False)
    print(f"   Found {len(all_plans)} plans:")
    for plan in all_plans:
        print(f"     - {plan['plan_name']}: {plan['target_likes']}L, {plan['target_retweets']}RT, {plan['target_comments']}C, {plan['target_views']}V")
    print()
    
    # Test getting specific plans
    print("4. Testing specific plan retrieval...")
    
    # Get default plan (first active plan)
    default_targets = get_custom_plan(test_user_id)
    print(f"   Default plan targets: {default_targets}")
    
    # Get specific plan by name
    viral_targets = get_custom_plan(test_user_id, "Viral Plan")
    print(f"   'Viral Plan' targets: {viral_targets}")
    
    engagement_targets = get_custom_plan(test_user_id, "Engagement Plan")
    print(f"   'Engagement Plan' targets: {engagement_targets}")
    
    # Get non-existent plan
    missing_targets = get_custom_plan(test_user_id, "Non-existent Plan")
    print(f"   'Non-existent Plan' targets: {missing_targets} (should be (0,0,0,0))")
    print()
    
    # Test updating a plan
    print("5. Testing plan updates...")
    update_success = update_custom_plan(
        user_id=test_user_id,
        plan_name="Budget Plan",
        likes=30,  # Updated from 25
        comments=8  # Updated from 5
    )
    print(f"   Updated 'Budget Plan': {update_success}")
    
    # Verify update
    updated_targets = get_custom_plan(test_user_id, "Budget Plan")
    print(f"   Updated 'Budget Plan' targets: {updated_targets}")
    print()
    
    # Test deactivating a plan
    print("6. Testing plan deactivation...")
    deactivate_success = update_custom_plan(
        user_id=test_user_id,
        plan_name="Engagement Plan",
        is_active=False
    )
    print(f"   Deactivated 'Engagement Plan': {deactivate_success}")
    
    # Get only active plans
    active_plans = get_user_custom_plans(test_user_id, active_only=True)
    print(f"   Active plans: {[p['plan_name'] for p in active_plans]}")
    
    # Get all plans including inactive
    all_plans_after = get_user_custom_plans(test_user_id, active_only=False)
    print(f"   All plans: {[(p['plan_name'], 'Active' if p['is_active'] else 'Inactive') for p in all_plans_after]}")
    print()
    
    # Test deleting a plan
    print("7. Testing plan deletion...")
    delete_success = delete_custom_plan(test_user_id, "Budget Plan")
    print(f"   Deleted 'Budget Plan': {delete_success}")
    
    # Verify deletion
    final_plans = get_user_custom_plans(test_user_id, active_only=False)
    print(f"   Remaining plans: {[p['plan_name'] for p in final_plans]}")
    print()
    
    print("=== Test completed successfully! ===")

if __name__ == "__main__":
    test_multiple_custom_plans()