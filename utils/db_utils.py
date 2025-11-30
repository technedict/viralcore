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
    """Set up custom_plans table for user-defined engagement goals (supports multiple plans per user)."""
    with get_connection(CUSTOM_DB_FILE) as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS custom_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                plan_name TEXT NOT NULL,
                target_likes INTEGER DEFAULT 0,
                target_retweets INTEGER DEFAULT 0,
                target_comments INTEGER DEFAULT 0,
                target_views INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, plan_name)
            );
        ''')
        
        # Check what columns actually exist before creating indexes
        c.execute('PRAGMA table_info(custom_plans)')
        columns = [col[1] for col in c.fetchall()]
        
        # Add indexes for better performance (only if columns exist)
        c.execute('CREATE INDEX IF NOT EXISTS idx_custom_plans_user_id ON custom_plans(user_id)')
        
        if 'is_active' in columns:
            c.execute('CREATE INDEX IF NOT EXISTS idx_custom_plans_active ON custom_plans(user_id, is_active)')
        
        if 'plan_name' in columns:
            c.execute('CREATE INDEX IF NOT EXISTS idx_custom_plans_name ON custom_plans(user_id, plan_name)')
            
    print("Custom DB initialized successfully.")

# --- User & Affiliate Management ---

def create_user(user_id: int, username: str, referrer: Optional[int] = None) -> bool:
    """
    Insert a new user into the database if they don't already exist.
    If the user exists but has no referrer and one is provided, update the referrer.
    
    Returns:
        True if a new user was created or referrer was updated, False if user already exists with a referrer.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        
        # Check if user already exists
        c.execute("SELECT id, referrer FROM users WHERE id = ?", (user_id,))
        existing_user = c.fetchone()
        
        if existing_user:
            # User exists - check if we can set referrer
            if referrer and not existing_user['referrer']:
                # Validate that referrer exists and is not the user themselves
                if referrer == user_id:
                    logger.warning(f"Referral attempt: User {user_id} cannot refer themselves.")
                    return False
                
                c.execute("SELECT id FROM users WHERE id = ?", (referrer,))
                if c.fetchone():
                    # Valid referrer - update
                    c.execute(
                        "UPDATE users SET referrer = ? WHERE id = ?",
                        (referrer, user_id)
                    )
                    conn.commit()
                    logger.info(f"REFERRAL_REGISTERED: User {user_id} ({username}) referred by user {referrer}")
                    return True
                else:
                    logger.warning(f"Referral attempt: Referrer {referrer} does not exist for user {user_id}")
                    return False
            # User already exists with or without referrer
            logger.debug(f"User {username} (ID: {user_id}) already exists.")
            return False
        else:
            # New user - validate referrer if provided
            if referrer:
                if referrer == user_id:
                    logger.warning(f"Referral attempt: User {user_id} cannot refer themselves.")
                    referrer = None
                else:
                    c.execute("SELECT id FROM users WHERE id = ?", (referrer,))
                    if not c.fetchone():
                        logger.warning(f"Referral attempt: Referrer {referrer} does not exist for new user {user_id}")
                        referrer = None
            
            # Create the new user
            c.execute(
                """
                INSERT INTO users (id, username, referrer)
                VALUES (?, ?, ?)
                """,
                (user_id, username, referrer)
            )
            conn.commit()
            
            if referrer:
                logger.info(f"REFERRAL_REGISTERED: New user {user_id} ({username}) referred by user {referrer}")
            else:
                logger.info(f"User {username} (ID: {user_id}) created without referrer.")
            
            return True

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

def get_referrer_id(user_id: int) -> Optional[int]:
    """
    Retrieve just the referrer's user ID for a given user.
    This is more efficient when you only need the ID.
    """
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT referrer FROM users WHERE id = ?", (user_id,))
        row = c.fetchone()
        return row['referrer'] if row and row['referrer'] else None

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

def admin_adjust_referral_balance(
    admin_id: int,
    target_user_id: int,
    amount: float,
    reason: str = "Admin adjustment"
) -> bool:
    """
    Admin function to add or remove referral/affiliate balance to/from any user.
    Logs all adjustments for audit purposes.
    
    Args:
        admin_id: The admin user ID performing the adjustment
        target_user_id: The user ID to adjust balance for
        amount: Amount to add (positive) or remove (negative)
        reason: Reason for the adjustment
    
    Returns:
        True if successful, False otherwise
    """
    import logging
    from datetime import datetime
    logger = logging.getLogger(__name__)
    
    # Verify admin privileges
    admin_user = get_user(admin_id)
    if not admin_user or not admin_user['is_admin']:
        logger.warning(f"ADMIN_BALANCE_ADJUST_DENIED: User {admin_id} is not an admin")
        return False
    
    # Verify target user exists
    target_user = get_user(target_user_id)
    if not target_user:
        logger.warning(f"ADMIN_BALANCE_ADJUST_FAILED: Target user {target_user_id} does not exist")
        return False
    
    current_balance = target_user['affiliate_balance'] or 0.0
    
    # Validate negative adjustments don't go below zero
    if amount < 0 and abs(amount) > current_balance:
        logger.warning(
            f"ADMIN_BALANCE_ADJUST_FAILED: Cannot remove ${abs(amount):.2f} from user {target_user_id}. "
            f"Current balance: ${current_balance:.2f}"
        )
        return False
    
    try:
        from utils.balance_operations import atomic_balance_update, generate_operation_id
        
        operation_id = generate_operation_id(target_user_id, "admin_adjust", abs(amount))
        
        success = atomic_balance_update(
            user_id=target_user_id,
            balance_type="affiliate",
            amount=amount,
            operation_type="admin_adjustment",
            reason=f"Admin {admin_id}: {reason}",
            operation_id=operation_id
        )
        
        if success:
            new_balance = current_balance + amount
            logger.info(
                f"ADMIN_BALANCE_ADJUST: Admin {admin_id} adjusted user {target_user_id} "
                f"balance by ${amount:.2f}. Old: ${current_balance:.2f}, New: ${new_balance:.2f}. "
                f"Reason: {reason}"
            )
        else:
            logger.error(
                f"ADMIN_BALANCE_ADJUST_FAILED: Atomic operation failed for admin {admin_id} "
                f"adjusting user {target_user_id} by ${amount:.2f}"
            )
        
        return success
        
    except ImportError:
        # Fallback to non-atomic operation
        logger.warning("Using non-atomic balance adjustment (balance_operations module not available)")
        
        new_balance = current_balance + amount
        
        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            c.execute(
                "UPDATE users SET affiliate_balance = ? WHERE id = ?",
                (new_balance, target_user_id)
            )
            conn.commit()
        
        logger.info(
            f"ADMIN_BALANCE_ADJUST: Admin {admin_id} adjusted user {target_user_id} "
            f"balance by ${amount:.2f}. Old: ${current_balance:.2f}, New: ${new_balance:.2f}. "
            f"Reason: {reason}"
        )
        return True

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

# --- Custom Plans (Multiple Plans Support) ---

def get_custom_plan(user_id: int, plan_name: str = None) -> Tuple[int, int, int, int]:
    """
    Fetch a user's custom engagement targets for a specific plan or their default active plan.
    Returns (0,0,0,0) if no plan exists.
    
    Args:
        user_id: User ID
        plan_name: Specific plan name, or None to get the first active plan
    """
    with get_connection(CUSTOM_DB_FILE) as conn:
        c = conn.cursor()
        
        # Check what columns exist
        try:
            c.execute("PRAGMA table_info(custom_plans)")
            columns = [col[1] for col in c.fetchall()]
        except:
            return (0, 0, 0, 0)
        
        # Build safe query
        if plan_name and 'plan_name' in columns:
            # Get specific plan by name
            query = "SELECT "
            select_parts = []
            if 'target_likes' in columns:
                select_parts.append("target_likes")
            else:
                select_parts.append("0 as target_likes")
            if 'target_retweets' in columns:
                select_parts.append("target_retweets")
            else:
                select_parts.append("0 as target_retweets")
            if 'target_comments' in columns:
                select_parts.append("target_comments")
            else:
                select_parts.append("0 as target_comments")
            if 'target_views' in columns:
                select_parts.append("target_views")
            else:
                select_parts.append("0 as target_views")
                
            query += ", ".join(select_parts)
            query += " FROM custom_plans WHERE user_id = ? AND plan_name = ?"
            
            if 'is_active' in columns:
                query += " AND is_active = 1"
                
            try:
                c.execute(query, (user_id, plan_name))
            except:
                return (0, 0, 0, 0)
        else:
            # Get first active plan (for backward compatibility)
            query = "SELECT "
            select_parts = []
            if 'target_likes' in columns:
                select_parts.append("target_likes")
            else:
                select_parts.append("0 as target_likes")
            if 'target_retweets' in columns:
                select_parts.append("target_retweets")
            else:
                select_parts.append("0 as target_retweets")
            if 'target_comments' in columns:
                select_parts.append("target_comments")
            else:
                select_parts.append("0 as target_comments")
            if 'target_views' in columns:
                select_parts.append("target_views")
            else:
                select_parts.append("0 as target_views")
                
            query += ", ".join(select_parts)
            query += " FROM custom_plans WHERE user_id = ?"
            
            if 'is_active' in columns:
                query += " AND is_active = 1"
                
            if 'created_at' in columns:
                query += " ORDER BY created_at ASC"
                
            query += " LIMIT 1"
            
            try:
                c.execute(query, (user_id,))
            except:
                return (0, 0, 0, 0)
        
        row = c.fetchone()
        return tuple(row) if row else (0, 0, 0, 0)

def get_user_custom_plans(user_id: int, active_only: bool = True) -> List[Dict[str, Any]]:
    """
    Get all custom plans for a user.
    
    Args:
        user_id: User ID
        active_only: If True, only return active plans
    
    Returns:
        List of custom plan dictionaries
    """
    with get_connection(CUSTOM_DB_FILE) as conn:
        c = conn.cursor()
        
        # First check what columns exist to build a safe query
        c.execute("PRAGMA table_info(custom_plans)")
        columns = [col[1] for col in c.fetchall()]
        
        # Build query based on available columns
        select_columns = ["id", "user_id"]
        
        # Add columns if they exist
        if 'plan_name' in columns:
            select_columns.append("plan_name")
        if 'target_likes' in columns:
            select_columns.append("target_likes") 
        if 'target_retweets' in columns:
            select_columns.append("target_retweets")
        if 'target_comments' in columns:
            select_columns.append("target_comments")
        if 'target_views' in columns:
            select_columns.append("target_views")
        if 'is_active' in columns:
            select_columns.append("is_active")
        if 'created_at' in columns:
            select_columns.append("created_at")
        if 'updated_at' in columns:
            select_columns.append("updated_at")
        if 'max_posts' in columns:
            select_columns.append("max_posts")
            
        query = f"""
            SELECT {', '.join(select_columns)}
            FROM custom_plans
            WHERE user_id = ?
        """
        params = [user_id]
        
        if active_only and 'is_active' in columns:
            query += " AND is_active = 1"
            
        if 'created_at' in columns:
            query += " ORDER BY created_at DESC"
        
        try:
            c.execute(query, params)
            
            plans = []
            for row in c.fetchall():
                # Convert row to dict for easier access
                row_dict = dict(row)
                
                plan_dict = {
                    'id': row_dict.get('id', 0),
                    'plan_name': row_dict.get('plan_name', 'Default Plan'),
                    'target_likes': row_dict.get('target_likes', 0),
                    'target_retweets': row_dict.get('target_retweets', 0),
                    'target_comments': row_dict.get('target_comments', 0),
                    'target_views': row_dict.get('target_views', 0),
                    'is_active': bool(row_dict.get('is_active', 1)),
                    'created_at': row_dict.get('created_at', ''),
                    'updated_at': row_dict.get('updated_at', ''),
                    'max_posts': row_dict.get('max_posts', 50)
                }
                plans.append(plan_dict)
            
            return plans
            
        except Exception as e:
            print(f"Error querying custom plans: {e}")
            return []

def create_custom_plan(user_id: int, plan_name: str, likes: int, retweets: int, comments: int, views: int, max_posts: int = 50) -> bool:
    """
    Create a new custom plan for a user.
    
    Args:
        user_id: User ID
        plan_name: Name for the custom plan
        likes: Target likes
        retweets: Target retweets
        comments: Target comments
        views: Target views
        max_posts: Maximum number of posts allowed (default: 50)
    
    Returns:
        True if successful, False if plan name already exists
    """
    from datetime import datetime
    
    with get_connection(CUSTOM_DB_FILE) as conn:
        c = conn.cursor()
        
        # Check if plan name already exists for this user
        c.execute(
            "SELECT id FROM custom_plans WHERE user_id = ? AND plan_name = ?",
            (user_id, plan_name)
        )
        if c.fetchone():
            return False  # Plan name already exists
        
        current_time = datetime.utcnow().isoformat()
        
        c.execute(
            """
            INSERT INTO custom_plans 
            (user_id, plan_name, target_likes, target_retweets, target_comments, target_views, max_posts, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (user_id, plan_name, likes, retweets, comments, views, max_posts, current_time, current_time)
        )
        conn.commit()
    
    # Create corresponding purchase record for the custom plan
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        
        # Check if user already has a 'ct' purchase record
        c.execute("""
            SELECT COUNT(*) FROM purchases 
            WHERE user_id = ? AND plan_type = 'ct'
        """, (user_id,))
        
        existing_count = c.fetchone()[0]
        
        if existing_count == 0:
            # Create purchase record for custom plan access using the specified max_posts
            c.execute("""
                INSERT INTO purchases 
                (user_id, plan_type, quantity, amount_paid_usd, payment_method, 
                 transaction_ref, timestamp, x_username, posts, rposts)
                VALUES (?, 'ct', ?, 0.0, 'custom_plan', ?, ?, '', ?, ?)
            """, (
                user_id,
                max_posts,
                f"custom_plan_{user_id}_{plan_name}_{current_time}",
                current_time,
                max_posts,
                max_posts
            ))
            conn.commit()
        
    print(f"Custom plan '{plan_name}' created for user {user_id}.")
    return True

def update_custom_plan(user_id: int, plan_name: str, likes: int = None, retweets: int = None, 
                      comments: int = None, views: int = None, is_active: bool = None) -> bool:
    """
    Update an existing custom plan.
    
    Args:
        user_id: User ID
        plan_name: Plan name to update
        likes: New target likes (optional)
        retweets: New target retweets (optional)
        comments: New target comments (optional)
        views: New target views (optional)
        is_active: New active status (optional)
    
    Returns:
        True if successful, False if plan doesn't exist
    """
    from datetime import datetime
    
    with get_connection(CUSTOM_DB_FILE) as conn:
        c = conn.cursor()
        
        # Check if plan exists
        c.execute(
            "SELECT id FROM custom_plans WHERE user_id = ? AND plan_name = ?",
            (user_id, plan_name)
        )
        if not c.fetchone():
            return False  # Plan doesn't exist
        
        # Build update query dynamically
        updates = []
        params = []
        
        if likes is not None:
            updates.append("target_likes = ?")
            params.append(likes)
        if retweets is not None:
            updates.append("target_retweets = ?")
            params.append(retweets)
        if comments is not None:
            updates.append("target_comments = ?")
            params.append(comments)
        if views is not None:
            updates.append("target_views = ?")
            params.append(views)
        if is_active is not None:
            updates.append("is_active = ?")
            params.append(1 if is_active else 0)
        
        if updates:
            updates.append("updated_at = ?")
            params.append(datetime.utcnow().isoformat())
            
            params.extend([user_id, plan_name])
            
            query = f"UPDATE custom_plans SET {', '.join(updates)} WHERE user_id = ? AND plan_name = ?"
            c.execute(query, params)
            conn.commit()
        
    print(f"Custom plan '{plan_name}' updated for user {user_id}.")
    return True

def delete_custom_plan(user_id: int, plan_name: str) -> bool:
    """
    Delete a custom plan.
    
    Args:
        user_id: User ID
        plan_name: Plan name to delete
    
    Returns:
        True if successful, False if plan doesn't exist
    """
    with get_connection(CUSTOM_DB_FILE) as conn:
        c = conn.cursor()
        
        result = c.execute(
            "DELETE FROM custom_plans WHERE user_id = ? AND plan_name = ?",
            (user_id, plan_name)
        )
        
        success = result.rowcount > 0
        if success:
            conn.commit()
            print(f"Custom plan '{plan_name}' deleted for user {user_id}.")
        
        return success

def set_custom_plan(user_id: int, likes: int, retweets: int, comments: int, views: int, plan_name: str = "Default Plan") -> None:
    """
    Legacy function for backward compatibility. Creates or updates a custom plan.
    
    Args:
        user_id: User ID
        likes: Target likes
        retweets: Target retweets  
        comments: Target comments
        views: Target views
        plan_name: Plan name (defaults to "Default Plan")
    """
    from datetime import datetime
    
    with get_connection(CUSTOM_DB_FILE) as conn:
        c = conn.cursor()
        
        current_time = datetime.utcnow().isoformat()
        
        c.execute(
            """
            INSERT OR REPLACE INTO custom_plans 
            (user_id, plan_name, target_likes, target_retweets, target_comments, target_views, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (user_id, plan_name, likes, retweets, comments, views, current_time, current_time)
        )
        conn.commit()
    print(f"Custom plan '{plan_name}' set for user {user_id}.")

def decrement_custom_plan_posts(user_id: int, plan_name: str) -> bool:
    """
    Decrement the max_posts for a custom plan by 1.
    If max_posts reaches 0, the plan is deactivated.
    
    Args:
        user_id: User ID
        plan_name: Name of the custom plan
    
    Returns:
        True if successfully decremented, False if plan not found or no posts remaining
    """
    from datetime import datetime
    
    with get_connection(CUSTOM_DB_FILE) as conn:
        c = conn.cursor()
        
        # Get current max_posts
        c.execute(
            "SELECT max_posts FROM custom_plans WHERE user_id = ? AND plan_name = ? AND is_active = 1",
            (user_id, plan_name)
        )
        row = c.fetchone()
        
        if not row or row['max_posts'] <= 0:
            return False  # Plan not found or no posts remaining
        
        new_posts = row['max_posts'] - 1
        
        if new_posts <= 0:
            # Deactivate the plan
            c.execute(
                """
                UPDATE custom_plans 
                SET max_posts = 0, is_active = 0, updated_at = ? 
                WHERE user_id = ? AND plan_name = ?
                """,
                (datetime.utcnow().isoformat(), user_id, plan_name)
            )
        else:
            # Just decrement
            c.execute(
                """
                UPDATE custom_plans 
                SET max_posts = ?, updated_at = ? 
                WHERE user_id = ? AND plan_name = ?
                """,
                (new_posts, datetime.utcnow().isoformat(), user_id, plan_name)
            )
        
        conn.commit()
        return True

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