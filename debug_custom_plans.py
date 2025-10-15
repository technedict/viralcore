#!/usr/bin/env python3
"""
Test script to debug the custom plan admin submission issue
"""

import sys
sys.path.append('/home/technedict/Desktop/viralpackage/viralcore')

def test_custom_plan_parsing():
    """Test the parsing logic that the admin handler uses"""
    
    test_inputs = [
        "12345, Test Plan, 100, 50, 25, 3000",  # 6 parts format
        "12345, Test Plan, 100, 50, 25, 3000, 20",  # 7 parts format  
        "12345, 100, 50, 25, 3000",  # 5 parts format
        "12345,Test Plan,100,50,25,3000",  # No spaces
        " 12345 , Test Plan , 100 , 50 , 25 , 3000 ",  # Extra spaces
    ]
    
    for i, text in enumerate(test_inputs):
        print(f"\nTest {i+1}: '{text}'")
        try:
            parts = [p.strip() for p in text.split(",")]
            print(f"  Parts: {parts}")
            print(f"  Length: {len(parts)}")
            
            if len(parts) == 5:
                # Old format: UserID, Likes, Retweets, Comments, Views
                uid, likes, rts, cmts, views = [int(p) for p in parts]
                plan_name = "Admin Plan"
                max_posts = 50  # Default
                print(f"  Format: 5-part (old)")
            elif len(parts) == 6:
                # Format: UserID, PlanName, Likes, Retweets, Comments, Views
                uid = int(parts[0])
                plan_name = parts[1]
                likes, rts, cmts, views = [int(p) for p in parts[2:]]
                max_posts = 50  # Default
                print(f"  Format: 6-part")
            elif len(parts) == 7:
                # Full format: UserID, PlanName, Likes, Retweets, Comments, Views, MaxPosts
                uid = int(parts[0])
                plan_name = parts[1]
                likes, rts, cmts, views, max_posts = [int(p) for p in parts[2:]]
                print(f"  Format: 7-part")
            else:
                raise ValueError("Invalid number of parameters")
            
            print(f"  Parsed: uid={uid}, plan_name='{plan_name}', likes={likes}, rts={rts}, cmts={cmts}, views={views}, max_posts={max_posts}")
            
            # Test the function call
            from utils.admin_db_utils import add_custom_plan
            success = add_custom_plan(uid, likes, rts, cmts, views, plan_name, max_posts)
            print(f"  Function call result: {success}")
            
        except Exception as e:
            print(f"  ❌ Error: {e}")
            import traceback
            traceback.print_exc()

def test_function_signature():
    """Test the function signature"""
    from utils.admin_db_utils import add_custom_plan
    import inspect
    
    sig = inspect.signature(add_custom_plan)
    print(f"Function signature: {sig}")
    print("Parameters:")
    for name, param in sig.parameters.items():
        print(f"  {name}: {param.annotation} = {param.default}")

if __name__ == "__main__":
    print("Custom Plan Admin Submission Debug")
    print("=" * 50)
    
    test_function_signature()
    test_custom_plan_parsing()