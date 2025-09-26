#!/usr/bin/env python3
# ViralMonitor/utils/db.py
# Reply balance management for ViralMonitor integration

import sqlite3
import logging
from typing import List, Optional
from utils.db_utils import get_connection, DB_FILE

logger = logging.getLogger(__name__)

# Initialize reply balance table
def init_reply_balance_db():
    """Initialize reply balance tracking table"""
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS reply_balances (
                user_id INTEGER PRIMARY KEY,
                balance REAL DEFAULT 0.0,
                total_posts INTEGER DEFAULT 0,
                daily_posts INTEGER DEFAULT 0,
                last_post_date TEXT DEFAULT '',
                is_reply_guy INTEGER DEFAULT 0
            );
        ''')
        conn.commit()

def get_total_amount(user_id: int) -> float:
    """Get reply balance for a user."""
    init_reply_balance_db()
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT balance FROM reply_balances WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        return row['balance'] if row else 0.0

def get_total_posts(user_id: int) -> int:
    """Get total posts count for a user."""
    init_reply_balance_db()
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT total_posts FROM reply_balances WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        return row['total_posts'] if row else 0

def get_user_daily_posts(user_id: int) -> int:
    """Get daily posts count for a user."""
    init_reply_balance_db()
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT daily_posts FROM reply_balances WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        return row['daily_posts'] if row else 0

def add_post(user_id: int, amount: float = 0.0):
    """Add a post and optionally update balance."""
    init_reply_balance_db()
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            INSERT OR REPLACE INTO reply_balances 
            (user_id, balance, total_posts, daily_posts) 
            VALUES (
                ?, 
                COALESCE((SELECT balance FROM reply_balances WHERE user_id = ?), 0) + ?,
                COALESCE((SELECT total_posts FROM reply_balances WHERE user_id = ?), 0) + 1,
                COALESCE((SELECT daily_posts FROM reply_balances WHERE user_id = ?), 0) + 1
            )
        """, (user_id, user_id, amount, user_id, user_id))
        conn.commit()

def remove_amount(user_id: int, amount: float) -> bool:
    """Remove amount from reply balance (for withdrawals)."""
    if amount <= 0:
        return False
    
    init_reply_balance_db()
    current_balance = get_total_amount(user_id)
    
    if amount > current_balance:
        logger.warning(f"Insufficient reply balance for user {user_id}: requested {amount}, available {current_balance}")
        return False
    
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            UPDATE reply_balances 
            SET balance = balance - ?
            WHERE user_id = ? AND balance >= ?
        """, (amount, user_id, amount))
        
        if c.rowcount == 0:
            logger.error(f"Failed to remove amount from reply balance for user {user_id}")
            return False
        
        conn.commit()
        logger.info(f"Removed {amount} from reply balance for user {user_id}")
        return True

def get_all_reply_guys_ids() -> List[int]:
    """Get all reply guy user IDs."""
    init_reply_balance_db()
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT user_id FROM reply_balances WHERE is_reply_guy = 1")
        return [row['user_id'] for row in c.fetchall()]

def get_username_by_userid(user_id: int) -> Optional[str]:
    """Get username by user ID."""
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT username FROM users WHERE id = ?", (user_id,))
        row = c.fetchone()
        return row['username'] if row else None