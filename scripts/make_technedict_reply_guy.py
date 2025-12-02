#!/usr/bin/env python3
"""
Script to promote technedict to reply guy status.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.admin_db_utils import promote_user_to_reply_guy
from utils.db_utils import get_user

def main():
    # You'll need to get your Telegram user ID
    # This is typically visible when you interact with the bot
    user_id = input("Enter your Telegram user ID: ").strip()
    
    if not user_id.isdigit():
        print("Error: User ID must be a number")
        return
    
    user_id = int(user_id)
    
    # Check if user exists
    user = get_user(user_id)
    if not user:
        print(f"Error: User {user_id} not found in database")
        print("Please start the bot first with /start to create your user account")
        return
    
    # Promote to reply guy
    promote_user_to_reply_guy(user_id)
    username = user['username'] if user['username'] else 'unknown'
    print(f"✅ User {user_id} ({username}) is now a reply guy!")
    print("\nYou now have access to the Reply Guys Panel in the bot.")

if __name__ == "__main__":
    main()
