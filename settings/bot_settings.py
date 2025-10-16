# settings/bot_settings.py

import random

# List of Telegram group chat IDs for comment batches.
# Order matters: pointer will rotate through this list. Commentz will be sent to these groups in order.
# Ensure these IDs are correct and that the bot has permission to post in these groups.
COMMENT_GROUP_IDS = [
    -1002294475790,
    -1002892312179,
    -1002857579648,
    -1002846132369,
    -1002707256903,
    -1002894977614,
    -1002532192752,
    -1002750424599,
    -1003111154860,
    -1002982578132,
    # Add more group IDs as needed
]

# Number of accounts (comments) available per group
# This should match how many commenters you have in each group
ACCOUNTS_PER_GROUP = 5

# Time interval between sending to each group in seconds
# Default: 30 minutes
INTERVAL_MINUTES = random.randint(10, 40)
BATCH_INTERVAL_SECONDS = INTERVAL_MINUTES * 60 

# File path to persist the batch pointer index
# This file will store a JSON object: {"pointer": <int>}
POINTER_FILE = "settings/group_pointer.json"

# ========================================
# Likes Group Configuration
# ========================================
# Independent admin group that receives every post with likes_needed metric
# This group is exempt from rotation and receives all posts unconditionally

# Enable/disable Likes Group sending (default: disabled for backward compatibility)
import os
ADMIN_LIKES_GROUP_ENABLED = os.getenv("ADMIN_LIKES_GROUP_ENABLED", "false").lower() == "true"

# Likes Group chat ID (must be configured when enabled)
ADMIN_LIKES_GROUP_CHAT_ID = os.getenv("ADMIN_LIKES_GROUP_CHAT_ID", None)
if ADMIN_LIKES_GROUP_CHAT_ID:
    try:
        ADMIN_LIKES_GROUP_CHAT_ID = int(ADMIN_LIKES_GROUP_CHAT_ID)
    except ValueError:
        ADMIN_LIKES_GROUP_CHAT_ID = None
