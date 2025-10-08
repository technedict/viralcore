import sqlite3
import os
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from datetime import datetime

# Database directory - centralize all .db files here
DB_DIR = os.getenv("DB_DIR", "./db")

# Ensure DB directory exists
Path(DB_DIR).mkdir(parents=True, exist_ok=True)

# Warn if DB_DIR points to ephemeral storage
_db_path = Path(DB_DIR).resolve()
if str(_db_path).startswith(('/tmp', '/var/tmp')):
    import warnings
    warnings.warn(
        f"⚠️  DB_DIR is set to ephemeral storage: {_db_path}\n"
        f"Database files will be lost on restart. Set DB_DIR to persistent storage.",
        UserWarning,
        stacklevel=2
    )

# Database file paths - all in centralized directory
DB_FILE = str(Path(DB_DIR) / "viralcore.db")
TWEETS_DB_FILE = str(Path(DB_DIR) / "tweets.db")
TG_DB_FILE = str(Path(DB_DIR) / "tg.db")
GROUPS_TWEETS_DB_FILE = str(Path(DB_DIR) / "groups.db")
CUSTOM_DB_FILE = str(Path(DB_DIR) / "custom.db")


# (Optional) You might want to define constants for plan types
X_PLAN_TYPES = ('t1', 't2', 't3', 't4', 't5')
TG_PLAN_TYPE = 'tgt'


def get_connection(db_file: str) -> sqlite3.Connection:
    """Helper to open a SQLite connection with row factory and optimized settings."""
    # Increase timeout to 30 seconds to handle concurrent operations
    conn = sqlite3.connect(db_file, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    
    # Enable Write-Ahead Logging for better concurrency
    conn.execute("PRAGMA journal_mode=WAL")
    
    # Set busy timeout for additional safety
    conn.execute("PRAGMA busy_timeout=30000")
    
    return conn

# --- Database Initialization ---

def init_main_db() -> None:
    """Set up core user, purchases, and processed transactions tables."""
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT,
                x_username TEXT DEFAULT '', -- Added for storing user's primary X username
                referrer INTEGER,
                affiliate_balance REAL DEFAULT 0.0,
                is_reply_guy INTEGER DEFAULT 0,
                is_admin INTEGER DEFAULT 0
            );
        ''')
        
        # Add indexes for better performance
        c.execute('CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_users_affiliate_balance ON users(affiliate_balance)')
        
        # --- UPDATED PURCHASES TABLE ---
        c.execute('''
            CREATE TABLE IF NOT EXISTS purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                plan_type TEXT NOT NULL,       -- Renamed from 'tier'
                quantity INTEGER NOT NULL,     -- Renamed from 'posts'
                amount_paid_usd REAL NOT NULL, -- Renamed from 'total_cost'
                payment_method TEXT NOT NULL,
                transaction_ref TEXT UNIQUE,   -- Renamed from 'tx_hash', now handles both crypto hashes and bank invoice IDs
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                x_username TEXT DEFAULT '',    -- ADDED: Column for X username
                posts INTEGER DEFAULT 0,       -- ADDED: Column for remaining posts (posts)
                rposts INTEGER DEFAULT 0       -- ADDED: Column for remaining posts (rposts)
            );
        ''')
        # --- END UPDATED PURCHASES TABLE ---
        
        # Add indexes for better performance
        c.execute('CREATE INDEX IF NOT EXISTS idx_purchases_user_id ON purchases(user_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_purchases_plan_type ON purchases(plan_type)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_purchases_timestamp ON purchases(timestamp)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_purchases_transaction_ref ON purchases(transaction_ref)')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS processed_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_hash TEXT UNIQUE NOT NULL,
                user_id INTEGER,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        
        # Add indexes for better performance  
        c.execute('CREATE INDEX IF NOT EXISTS idx_processed_tx_hash ON processed_transactions(transaction_hash)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_processed_tx_user ON processed_transactions(user_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_processed_tx_timestamp ON processed_transactions(processed_at)')
        
    print("Main DB initialized successfully.")

def init_tweet_db() -> None:
    """Set up tweets table for tracking X (Twitter) engagement goals."""
    with get_connection(TWEETS_DB_FILE) as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS tweets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tweet_id TEXT NOT NULL,
                twitter_link TEXT NOT NULL,
                target_likes INTEGER NOT NULL,
                target_retweets INTEGER NOT NULL,
                target_comments INTEGER NOT NULL,
                target_views INTEGER NOT NULL,
                current_comments INTEGER DEFAULT 0,
                current_views INTEGER DEFAULT 0,
                current_likes INTEGER DEFAULT 0,
                current_retweets INTEGER DEFAULT 0,
                group_id INTEGER,
                completed INTEGER DEFAULT 0,
                click_count INTEGER DEFAULT 0,
                views BOOLEAN DEFAULT 0,
                comments BOOLEAN DEFAULT 0
            );
        ''')
    print("Tweet DB initialized successfully.")

def init_tg_db() -> None:
    """Set up telegram_posts table for tracking Telegram engagement goals."""
    with get_connection(TG_DB_FILE) as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS telegram_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_link TEXT NOT NULL,
                target_members INTEGER DEFAULT 0,
                target_comments INTEGER DEFAULT 0,
                target_reactions INTEGER DEFAULT 0,
                current_members INTEGER DEFAULT 0,
                current_comments INTEGER DEFAULT 0,
                current_reactions INTEGER DEFAULT 0,
                group_id INTEGER,
                completed INTEGER DEFAULT 0,
                views_enabled BOOLEAN DEFAULT 0,
                comments_enabled BOOLEAN DEFAULT 0
            );
        ''')
    print("TG DB initialized successfully.")

def init_groups_db() -> None:
    """Set up groups table for grouping engagement tasks."""
    with get_connection(GROUPS_TWEETS_DB_FILE) as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS groups (
                group_id INTEGER PRIMARY KEY,
                group_name TEXT UNIQUE NOT NULL
            );
        ''')
    print("Groups DB initialized successfully.")

def init_custom_db() -> None:
    """Set up custom_plans table for user-defined engagement goals."""
    with get_connection(CUSTOM_DB_FILE) as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS custom_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                target_likes INTEGER DEFAULT 0,
                target_retweets INTEGER DEFAULT 0,
                target_comments INTEGER DEFAULT 0,
                target_views INTEGER DEFAULT 0
            );
        ''')
    print("Custom DB initialized successfully.")

# --- User & Affiliate Management ---

def create_user(user_id: int, username: str, referrer: Optional[int] = None) -> None:
    """Insert a new user into the database if they don't already exist."""
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            """
            INSERT OR IGNORE INTO users (id, username, referrer)
            VALUES (?, ?, ?)
            """,
            (user_id, username, referrer)
        )
        conn.commit()
    print(f"User {username} (ID: {user_id}) created or already exists.")

def get_user(user_id: int) -> Optional[sqlite3.Row]:
    """Fetch a user's record by their ID."""
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT id, username, referrer, affiliate_balance, is_admin
              FROM users
             WHERE id = ?
            """,
            (user_id,)
        )
        return c.fetchone()
    
def is_reply_guy(user_id: int) -> bool:
    try:
        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            c.execute(
                """
                SELECT is_reply_guy
                  FROM users
                 WHERE id = ?
                """,
                (user_id,)
            )
            result = c.fetchone()

            if result:
                return bool(result[0])
            else:
                # User not found in the database
                print(f"User {user_id} not found in the database when checking is_reply_guy.")
                return False
    except sqlite3.Error as e:
        print(f"Database error when checking is_reply_guy for user {user_id}: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error when checking is_reply_guy for user {user_id}: {e}")
        return False


def set_user_x_username(user_id: int, x_username: str) -> None:
    """Sets or updates a user's primary X username in the users table."""
    cleaned_username = x_username.strip().lstrip('@')
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            "UPDATE users SET x_username = ? WHERE id = ?",
            (cleaned_username, user_id)
        )
        conn.commit()
    print(f"User {user_id}'s X username set to '{cleaned_username}'.")

def get_user_x_username(user_id: int) -> Optional[str]:
    """
    Retrieves a user's primary X username from the users table.
    If not found there, it falls back to the most recent X username from purchases.
    """
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        # First, try to get from the users table
        c.execute(
            "SELECT x_username FROM users WHERE id = ?",
            (user_id,)
        )
        user_row = c.fetchone()
        if user_row and user_row['x_username']:
            return user_row['x_username']

        # If not found in users table, fall back to purchases
        c.execute(
            """
            SELECT x_username
            FROM purchases
            WHERE user_id = ? AND x_username IS NOT '' AND x_username IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            (user_id,)
        )
        purchase_row = c.fetchone()
        return purchase_row['x_username'] if purchase_row else None

def get_referrer(user_id: int) -> Optional[sqlite3.Row]:
    """Retrieve the referrer's user record for a given user, if one exists."""
    user = get_user(user_id)
    if user and user['referrer']:
        return get_user(user['referrer'])
    return None

def get_total_referrals(user_id: int) -> int:
    """Count how many users a given user has referred."""
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            "SELECT COUNT(*) AS cnt FROM users WHERE referrer = ?",
            (user_id,)
        )
        return c.fetchone()['cnt']

def get_affiliate_balance(user_id: int) -> float:
    """Fetches the current affiliate balance for a given user."""
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT affiliate_balance FROM users WHERE id = ?", (user_id,))
        row = c.fetchone()
        return row['affiliate_balance'] if row else 0.0

def update_affiliate_balance(user_id: int, bonus: float) -> None:
    """Add a bonus amount to a user's affiliate balance using atomic operations."""
    try:
        from utils.balance_operations import atomic_balance_update
        
        success = atomic_balance_update(
            user_id=user_id,
            balance_type="affiliate",
            amount=bonus,
            operation_type="bonus",
            reason="Affiliate balance bonus via update_affiliate_balance"
        )
        
        if success:
            print(f"Affiliate balance for user {user_id} updated by {bonus}.")
        else:
            print(f"Failed to update affiliate balance for user {user_id} by {bonus}.")
            
    except ImportError:
        # Fallback to original implementation
        print("Warning: Using non-atomic balance operation (balance_operations module not available)")
        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            c.execute(
                """
                UPDATE users
                   SET affiliate_balance = affiliate_balance + ?
                 WHERE id = ?
                """,
                (bonus, user_id)
            )
            conn.commit()
        print(f"Affiliate balance for user {user_id} updated by {bonus}.")

def decrement_affiliate_balance(user_id: int, amount_to_remove: float) -> bool:
    """
    Decrements a user's affiliate balance using atomic operations.
    Returns True if successful, False otherwise (e.g., insufficient funds).
    """
    if amount_to_remove <= 0:
        print("Amount to remove must be a positive value.")
        return False

    # Use atomic withdrawal operation for safety
    try:
        from utils.balance_operations import atomic_withdraw_operation, validate_withdrawal_request
        
        # Validate the withdrawal first
        is_valid, error_msg = validate_withdrawal_request(user_id, "affiliate", amount_to_remove)
        if not is_valid:
            print(f"Validation failed: {error_msg}")
            return False
        
        # Perform atomic withdrawal
        success = atomic_withdraw_operation(
            user_id=user_id,
            balance_type="affiliate",
            amount=amount_to_remove,
            reason="Balance decrement via decrement_affiliate_balance"
        )
        
        if success:
            print(f"Successfully removed {amount_to_remove:.2f} from user {user_id}'s affiliate balance.")
        else:
            print(f"Failed to remove {amount_to_remove:.2f} from user {user_id}'s affiliate balance.")
        
        return success
        
    except ImportError:
        # Fallback to original implementation if balance_operations not available
        print("Warning: Using non-atomic balance operation (balance_operations module not available)")
        current_balance = get_affiliate_balance(user_id)

        if amount_to_remove > current_balance:
            print(f"Cannot remove {amount_to_remove:.2f}. User {user_id} only has {current_balance:.2f} in affiliate balance.")
            return False

        new_balance = current_balance - amount_to_remove

        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            try:
                c.execute(
                    "UPDATE users SET affiliate_balance = ? WHERE id = ?",
                    (new_balance, user_id)
                )
                conn.commit()
                print(f"Successfully removed {amount_to_remove:.2f} from user {user_id}'s affiliate balance. New balance: {new_balance:.2f}")
                return True
            except sqlite3.Error as e:
                print(f"Database error while decrementing balance for user {user_id}: {e}")
                conn.rollback()
                return False

def get_user_metrics(user_id: int) -> Tuple[int, int, float]:
    """
    Return total remaining X posts, total remaining TG posts, and affiliate balance for a user.
    Differentiation is based on 'plan_type':
    - 'tgt' for TG posts.
    - 't1', 't2', 't3', 't4', 't5' for X posts.
    """
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()

        # Sum of rposts for X (where plan_type is 't1', 't2', 't3', 't4', 't5')
        c.execute(
            """
            SELECT COALESCE(SUM(rposts), 0) AS total_x_posts
            FROM purchases
            WHERE user_id = ? AND plan_type IN ('t1', 't2', 't3', 't4', 't5')
            """,
            (user_id,)
        )
        total_x_posts = c.fetchone()['total_x_posts']

        # Sum of rposts for TG (where plan_type is 'tgt')
        c.execute(
            """
            SELECT COALESCE(SUM(rposts), 0) AS total_tg_posts
            FROM purchases
            WHERE user_id = ? AND plan_type = 'tgt'
            """,
            (user_id,)
        )
        total_tg_posts = c.fetchone()['total_tg_posts']

    # Fetch affiliate balance as before
    affiliate_balance = get_affiliate_balance(user_id)

    return total_x_posts, total_tg_posts, affiliate_balance


def get_detailed_purchase_balances(user_id: int) -> List[Dict[str, Any]]:
    """
    Fetches detailed remaining post balances for a user from individual purchases.
    Only returns purchases that still have 'rposts' remaining.

    Returns:
        A list of dictionaries, each representing a purchase with its details
        and remaining posts.
    """
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT
                id,
                plan_type,
                quantity,        -- Original quantity purchased
                posts,           -- Total posts purchased
                rposts,          -- Remaining posts
                amount_paid_usd,
                payment_method,
                transaction_ref,
                timestamp,
                x_username       -- Associated X username for this specific purchase
            FROM
                purchases
            WHERE
                user_id = ? AND rposts > 0 -- Filter for the user and only active (remaining) posts
            ORDER BY
                timestamp DESC -- Show most recent purchases first
            """,
            (user_id,)
        )
        # Fetch all results and convert each row (sqlite3.Row object) to a dictionary
        detailed_balances = [dict(row) for row in c.fetchall()]

    return detailed_balances


def format_detailed_balances_message(user_id: int) -> str:
    """
    Formats a user-friendly message detailing individual purchase balances.
    """
    details = get_detailed_purchase_balances(user_id)

    if not details:
        return "You currently have no active purchases with remaining posts."

    message = "📜 *Your Active Post Balances:*\n\n"
    for i, purchase in enumerate(details):
        purchase_id = purchase['id']
        plan_type = purchase['plan_type']
        original_qty = purchase['quantity']  # Original quantity purchased
        posts = purchase['posts']
        remaining_posts = purchase['rposts']
        amount_paid = purchase['amount_paid_usd']
        transaction_ref = purchase['transaction_ref']
        timestamp_str = purchase['timestamp']
        x_username_for_purchase = purchase['x_username'] # This is the X username associated with *this specific purchase*

        # Determine platform label and emoji based on plan_type
        platform_label = "Unknown"
        platform_emoji = "❓"
        if plan_type == TG_PLAN_TYPE:
            platform_label = "Telegram"
            platform_emoji = "✈️"
        elif plan_type in X_PLAN_TYPES:
            platform_label = "X (Twitter)"
            platform_emoji = "🐦"

        # Format timestamp for better readability
        try:
            formatted_date = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d %H:%M')
        except ValueError:
            formatted_date = timestamp_str # Fallback if format doesn't match

        message += f"*{i + 1}. Purchase #{purchase_id} {platform_emoji} ({platform_label})*\n"
        message += f"  - Plan Type: `{plan_type}`\n"
        message += f"  - Remaining: `{remaining_posts}` out of `{posts}` posts\n"
        if x_username_for_purchase: # Only show if an X username was explicitly linked to this purchase
             message += f"  - Linked X Account: @{x_username_for_purchase}\n"
        message += f"  - Amount Paid: `${amount_paid:.2f}`\n"
        if transaction_ref: # Only show if a transaction reference exists
            message += f"  - Transaction Ref: `{transaction_ref}`\n"
        message += f"  - Purchase Date: `{formatted_date}`\n"
        message += "\n"

    return message

# --- Purchase Management (General) ---

# --- UPDATED SAVE PURCHASE FUNCTION ---
def save_purchase(
    user_id: int,
    plan_type: str,            # Renamed from 'tier'
    quantity: int,             # Renamed from 'posts'
    amount_paid_usd: float,    # Renamed from 'total_cost'
    payment_method: str,
    comments: Optional[int] = 0,  # Default to 0 if not specified
    transaction_ref: Optional[str] = None # Renamed from 'tx_hash', handles both
) -> None:
    """Insert a new purchase record into the database."""
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO purchases (user_id, plan_type, quantity, amount_paid_usd, payment_method, transaction_ref, posts, rposts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, plan_type, comments, amount_paid_usd, payment_method, transaction_ref, quantity, quantity)  # rposts initialized to quantity
        )
        conn.commit()
    print(f"Purchase saved for user {user_id} (Transaction Ref: {transaction_ref}).")
# --- END UPDATED SAVE PURCHASE FUNCTION ---

def get_x_purchases(user_id: int) -> List[sqlite3.Row]:
    """List all purchases for a user, with the newest first."""
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT plan_type, x_username, posts, rposts, amount_paid_usd, timestamp, transaction_ref, payment_method
              FROM purchases
             WHERE user_id = ? AND plan_type != 'tgt'
             ORDER BY timestamp DESC
            """,
            (user_id,)
        )
        return c.fetchall()

# --- X (Twitter) Specific Functions ---

def get_x_accounts(user_id: int) -> List[str]:
    """List all unique X usernames a user has linked via purchases."""
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT DISTINCT x_username
              FROM purchases
             WHERE user_id = ? AND x_username IS NOT '' AND x_username IS NOT NULL AND plan_type != 'tgt'
            """,
            (user_id,)
        )
        return [r[0] for r in c.fetchall()]

def update_purchase_x_username(user_id: int, x_username: str) -> None:
    """
    Assigns an X username to the most recent purchase record that
    does not yet have an x_username assigned.
    """
    x_username_clean = x_username.strip().lower()
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            """
            UPDATE purchases
               SET x_username = ?
             WHERE user_id = ? AND (x_username = '' OR x_username IS NULL)
             ORDER BY timestamp DESC
             LIMIT 1
            """,
            (x_username_clean, user_id)
        )
        conn.commit()
    print(f"X username '{x_username_clean}' assigned to a purchase for user {user_id}.")

def get_latest_tier_for_x(user_id: int, x_username: str) -> Tuple[Optional[str], Optional[int]]:
    """
    Fetch the tier and remaining posts (rposts) for the oldest *active*
    purchase associated with a specific X username, limited to T1-T5 plan types,
    and excluding 'tgt' plan type.
    """
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT plan_type, rposts
              FROM purchases
             WHERE user_id = ?
               AND x_username = ?
               AND rposts > 0
               AND plan_type != 'tgt' -- Added this line to exclude 'tgt'
             ORDER BY timestamp ASC
             LIMIT 1
            """,
            (user_id, x_username)
        )
        row = c.fetchone()
        return (row['plan_type'], row['rposts']) if row else (None, None)

def decrement_x_rpost(user_id: int, x_username: str) -> Optional[int]:
    """
    Decrements one remaining post (rpost) from the oldest purchase
    associated with a specific X username. If rposts reaches 0, the record is deleted.
    Returns the new rposts count, or None if no matching purchase found.
    """
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT id, rposts
              FROM purchases
             WHERE user_id = ? AND x_username = ? AND rposts > 0
             ORDER BY timestamp ASC
             LIMIT 1
            """,
            (user_id, x_username)
        )
        row = c.fetchone()
        if not row:
            print(f"No active X purchase found for user {user_id} with username {x_username} to decrement.")
            return None

        purchase_id, old_rposts = row['id'], row['rposts']
        new_rposts = old_rposts - 1

        if new_rposts > 0:
            c.execute(
                "UPDATE purchases SET rposts = ? WHERE id = ?",
                (new_rposts, purchase_id)
            )
            print(f"Decremented rposts for purchase {purchase_id}. New rposts: {new_rposts}")
        else:
            c.execute(
                "DELETE FROM purchases WHERE id = ?",
                (purchase_id,)
            )
            print(f"Deleted purchase {purchase_id} as rposts reached 0.")
        conn.commit()
        return new_rposts

# --- Telegram Specific Functions ---

def get_tg_purchases(user_id: int) -> List[sqlite3.Row]:
    """
    List all Telegram-specific purchases (tier 'tgt' or 'tg_members') for a user,
    with newest first.
    """
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT plan_type, posts, rposts, amount_paid_usd, timestamp, payment_method, transaction_ref
              FROM purchases
             WHERE user_id = ?
               AND plan_type = 'tgt'
             ORDER BY timestamp DESC
            """,
            (user_id,)
        )
        return c.fetchall()
    
def get_tg_accounts(user_id: int) -> List[str]:
    """List all unique TG usernames a user has linked via purchases."""
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT DISTINCT x_username
              FROM purchases
             WHERE user_id = ? AND x_username IS NOT '' AND x_username IS NOT NULL AND plan_type = 'tgt'
            """,
            (user_id,)
        )
        return [r[0] for r in c.fetchall()]

def get_latest_tg_plan(user_id: int, tg_username) -> Tuple[Optional[str], Optional[int]]:
    """
    Fetch the plan type and remaining posts (rposts) for the oldest *active*
    Telegram purchase (plan_type 'tgt' or 'tg_members').
    Returns (None, None) if no active purchase found.
    """
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT plan_type, quantity, rposts
              FROM purchases
             WHERE user_id = ? AND x_username = ? AND rposts > 0 AND plan_type = 'tgt' 
             ORDER BY timestamp ASC
             LIMIT 1
            """,
            (user_id, tg_username)
        )
        row = c.fetchone()
        return(row['plan_type'], row["quantity"], row['rposts']) if row else (None, None, None)

def decrement_tg_rpost(user_id: int) -> Optional[int]:
    """
    Decrements one remaining post (rpost) from the oldest *active* Telegram purchase
    (plan_type 'tgt' or 'tg_members'). Deletes the row if rposts reaches 0.
    Returns the new rposts count, or None if no matching active purchase found.
    """
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT id, rposts
              FROM purchases
             WHERE user_id = ? AND (plan_type = 'tgt' OR plan_type = 'tg_members') AND rposts > 0
             ORDER BY timestamp ASC
             LIMIT 1
            """,
            (user_id,)
        )
        row = c.fetchone()
        if not row:
            print(f"No active Telegram purchase found for user {user_id} to decrement.")
            return None

        purchase_id, old_rposts = row['id'], row['rposts']
        new_rposts = old_rposts - 1

        if new_rposts > 0:
            c.execute(
                "UPDATE purchases SET rposts = ? WHERE id = ?",
                (new_rposts, purchase_id)
            )
            #print(f"Decremented rposts for TG purchase {purchase_id}. New rposts: {new_rposts}")
        else:
            c.execute(
                "DELETE FROM purchases WHERE id = ?",
                (purchase_id,)
            )
            #print(f"Deleted TG purchase {purchase_id} as rposts reached 0.")
        conn.commit()
        return new_rposts

# --- Custom Plans ---

def get_custom_plan(user_id: int) -> Tuple[int, int, int, int]:
    """Fetch a user's custom engagement targets. Returns (0,0,0,0) if no plan exists."""
    with get_connection(CUSTOM_DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT target_likes, target_retweets, target_comments, target_views
              FROM custom_plans
             WHERE user_id = ?
            """,
            (user_id,)
        )
        row = c.fetchone()
        return tuple(row) if row else (0, 0, 0, 0)

def set_custom_plan(user_id: int, likes: int, retweets: int, comments: int, views: int) -> None:
    """Inserts or updates a user's custom engagement targets."""
    with get_connection(CUSTOM_DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            """
            INSERT OR REPLACE INTO custom_plans (user_id, target_likes, target_retweets, target_comments, target_views)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, likes, retweets, comments, views)
        )
        conn.commit()
    print(f"Custom plan set for user {user_id}.")

# --- Transaction Processing ---

def is_transaction_hash_processed(transaction_hash: str) -> bool:
    """Check if a crypto transaction hash has already been processed to prevent duplicates."""
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            "SELECT 1 FROM processed_transactions WHERE transaction_hash = ?",
            (transaction_hash,)
        )
        return c.fetchone() is not None

def mark_transaction_hash_as_processed(transaction_hash: str, user_id: int) -> None:
    """Record a crypto transaction hash as processed."""
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            "INSERT OR IGNORE INTO processed_transactions (transaction_hash, user_id) VALUES (?, ?)",
            (transaction_hash, user_id)
        )
        conn.commit()
    print(f"Transaction hash {transaction_hash} marked as processed for user {user_id}.")

# --- DB Migration Utilities ---

def migrate_db_files_to_directory() -> bool:
    """
    Migrate existing .db files from root to DB_DIR with backups.
    Safe to call multiple times (idempotent).
    
    Returns:
        True if migration successful or not needed, False otherwise
    """
    import shutil
    from datetime import datetime
    
    root_dir = Path(__file__).parent.parent
    db_files = ["viralcore.db", "tweets.db", "tg.db", "groups.db", "custom.db"]
    
    migrated = False
    
    for db_file in db_files:
        old_path = root_dir / db_file
        new_path = Path(DB_DIR) / db_file
        
        # Skip if old file doesn't exist
        if not old_path.exists():
            continue
            
        # Skip if already in correct location
        if old_path.resolve() == new_path.resolve():
            continue
        
        try:
            # Create backup directory
            backup_dir = Path(DB_DIR) / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            
            # Create timestamped backup
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = backup_dir / f"{db_file}.backup_{timestamp}"
            
            # Copy old file to backup
            shutil.copy2(old_path, backup_path)
            print(f"✅ Backed up {db_file} to {backup_path}")
            
            # Move to new location
            shutil.move(str(old_path), str(new_path))
            print(f"✅ Migrated {db_file} to {new_path}")
            
            migrated = True
            
        except Exception as e:
            print(f"❌ Failed to migrate {db_file}: {e}")
            return False
    
    if migrated:
        print(f"✅ Database files migrated to {DB_DIR}")
    else:
        print(f"ℹ️  No database files to migrate (already in {DB_DIR})")
    
    return True