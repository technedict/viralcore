#!/usr/bin/env python3
"""
Test the complete custom plans separation functionality
"""

import sys
sys.path.append('/home/technedict/Desktop/viralpackage/viralcore')

from utils.db_utils import get_user_custom_plans, get_x_accounts, get_latest_tier_for_x

def test_plan_separation():
    """Test that both tier plans and custom plans show up correctly"""
    test_user_id = 6030280354  # User with both tier plans and custom plans
    
    print("Plan Separation Test")
    print("=" * 50)
    
    # 1. Get user's X accounts
    x_accounts = get_x_accounts(test_user_id)
    print(f"X accounts: {x_accounts}")
    
    accounts = sorted({acc.strip().lower() for acc in x_accounts if acc.strip()})
    
    keyboard_buttons = []
    
    # 2. Test regular tier plan options
    print("\n2. Regular Tier Plans:")
    for acc in accounts:
        tier, remaining = get_latest_tier_for_x(test_user_id, acc)
        if tier and remaining and remaining > 0:
            button_text = f"@{acc.title()} ({tier.upper()} - {remaining} posts left)"
            callback_data = f"select_x_{acc}"
            keyboard_buttons.append((button_text, callback_data, "tier"))
            print(f"  {button_text} -> {callback_data}")
        else:
            print(f"  @{acc}: No active tier plan or no posts remaining")
    
    # 3. Test custom plan options
    print("\n3. Custom Plans:")
    custom_plans = get_user_custom_plans(test_user_id, active_only=True)
    for acc in accounts:
        for plan in custom_plans:
            plan_name = plan['plan_name']
            max_posts = plan.get('max_posts', 0)
            if max_posts > 0:
                button_text = f"@{acc.title()} (Custom: {plan_name} - {max_posts} posts left)"
                callback_data = f"select_x_{acc}_custom_{plan_name}"
                keyboard_buttons.append((button_text, callback_data, "custom"))
                print(f"  {button_text} -> {callback_data}")
    
    # 4. Summary
    print(f"\n4. Summary:")
    print(f"Total buttons: {len(keyboard_buttons)}")
    tier_count = len([b for b in keyboard_buttons if b[2] == "tier"])
    custom_count = len([b for b in keyboard_buttons if b[2] == "custom"])
    print(f"  Tier plan buttons: {tier_count}")
    print(f"  Custom plan buttons: {custom_count}")
    
    # 5. Test callback parsing
    print(f"\n5. Callback Parsing Test:")
    test_callbacks = [
        "select_x_testuser123",
        "select_x_testuser123_custom_frog",
        "select_x_testuser123_custom_CT1"
    ]
    
    for callback in test_callbacks:
        selection = callback.removeprefix("select_x_")
        if "_custom_" in selection:
            parts = selection.split("_custom_", 1)
            acc = parts[0]
            plan_name = parts[1]
            print(f"  '{callback}' -> account='{acc}', custom plan='{plan_name}'")
        else:
            acc = selection
            print(f"  '{callback}' -> account='{acc}', tier plan")
    
    print("\n✅ Plan separation test completed!")

if __name__ == "__main__":
    test_plan_separation()