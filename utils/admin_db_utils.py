import sqlite3
from typing import List, Optional
from utils.db_utils import DB_FILE, CUSTOM_DB_FILE, get_connection

# -------------------------------
# Admin Helper Functions
# -------------------------------

def is_admin(user_id: int) -> bool:
    """Check if a user has admin privileges."""
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT is_admin FROM users WHERE id = ?", (user_id,))
        row = c.fetchone()
        return bool(row and row["is_admin"])

def get_all_users() -> List[sqlite3.Row]:
    """Fetch all users from the database."""
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM users")
        return c.fetchall()


def get_all_payments() -> List[sqlite3.Row]:
    """Fetch all purchase records from the database."""
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM purchases")
        return c.fetchall()


def get_rposts(user_id: int) -> int:
    """Get the most recent remaining-posts count for a user."""
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            "SELECT rposts FROM purchases WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user_id,)
        )
        row = c.fetchone()
        return row["rposts"] if row else 0


def get_rposts_by_payment(payment_id: int) -> int:
    """Get remaining-posts count for a specific purchase."""
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT rposts FROM purchases WHERE id = ?", (payment_id,))
        row = c.fetchone()
        return row["rposts"] if row else 0


def get_username_by_payment(payment_id: int) -> str:
    """Get the X username associated with a purchase."""
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT x_username FROM purchases WHERE id = ?", (payment_id,))
        row = c.fetchone()
        return row["x_username"] if row and row["x_username"] else "unknown"


# --- NEW FUNCTION TO GET TELEGRAM USERNAME ---
def get_username_by_userid(user_id: int) -> Optional[str]:
    """
    Retrieves the Telegram username for a given user ID from the 'users' table.

    Args:
        user_id (int): The user's unique Telegram ID.

    Returns:
        Optional[str]: The Telegram username as a string if found, otherwise None.
                       Returns 'N/A' if the user exists but has no username set.
    """
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        # Assuming the 'users' table has a column named 'username'
        # If your column is named differently (e.g., 'tg_username'), change 'username' below.
        c.execute("SELECT username FROM users WHERE id = ?", (user_id,))
        row = c.fetchone()
        if row:
            # Return username if it exists, otherwise 'N/A' for clarity
            return row["username"] if row["username"] else "N/A"
        return None # User ID not found in the 'users' table
    
def add_payment(user_id: int, x_username: str, tier: str, comments: str, amount: int, cost: float) -> None:
    """Record a new purchase for a user."""
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO purchases (user_id, x_username, plan_type, payment_method, quantity, posts, rposts, amount_paid_usd) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, x_username, tier, "Admin", comments, amount, amount, cost)
        )


def add_posts(payment_id: int, posts_to_add: int) -> None:
    """Add posts to an existing purchase's remaining count."""
    current = get_rposts_by_payment(payment_id)
    new_rposts = current + posts_to_add
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            "UPDATE purchases SET rposts = ? WHERE id = ?",
            (new_rposts, payment_id)
        )


def add_custom_plan(user_id: int, target_likes: int, target_retweets: int,
                    target_comments: int, target_views: int) -> None:
    """Create a custom engagement plan for a user."""
    with get_connection(CUSTOM_DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO custom_plans (user_id, target_likes, target_retweets, target_comments, target_views) VALUES (?, ?, ?, ?, ?)",
            (user_id, target_likes, target_retweets, target_comments, target_views)
        )


def update_payment(payment_id: int, user_id: int, new_tier: str, new_post: int) -> None:
    """Update tier and post counts for a purchase."""
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            "UPDATE purchases SET plan_type = ?, rposts = ?, posts = ? WHERE id = ? AND user_id = ?",
            (new_tier, new_post, new_post, payment_id, user_id)
        )


def reset_purchase(user_id: int) -> None:
    """Reset all remaining posts to original posts for a user."""
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            "UPDATE purchases SET rposts = posts WHERE user_id = ?",
            (user_id,)
        )


def reset_affiliate_balance(user_id: int) -> None:
    """Zero out a user's affiliate balance."""
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            "UPDATE users SET affiliate_balance = 0 WHERE id = ?",
            (user_id,)
        )


def promote_user_to_admin(user_id: int) -> None:
    """Grant admin privileges to a user."""
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (user_id,))


def promote_user_to_reply_guy(user_id: int) -> None:
    """Grant reply guy privileges to a user."""
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET is_reply_guy = 1 WHERE id = ?", (user_id,))


def demote_user(user_id: int) -> None:
    """Revoke admin privileges from a user."""
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET is_admin = 0 WHERE id = ?", (user_id,))


def delete_custom_plan_by_payment(payment_id: int) -> None:
    """Remove a custom plan when its purchase is deleted."""
    with get_connection(CUSTOM_DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            "DELETE FROM custom_plans WHERE user_id = (SELECT user_id FROM purchases WHERE id = ?)",
            (payment_id,)
        )


def delete_payment(payment_id: int) -> None:
    """Delete a purchase record."""
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM purchases WHERE id = ?", (payment_id,))


def delete_user(user_id: int) -> None:
    """Delete a user account and all related data."""
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM users WHERE id = ?", (user_id,))