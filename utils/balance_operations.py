#!/usr/bin/env python3
# utils/balance_operations.py
# Atomic balance operations with idempotency support

import sqlite3
import uuid, os, sys
import logging
from typing import Optional, Literal
from datetime import datetime
from utils.db_utils import get_connection, DB_FILE

current_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
root_dir = os.path.abspath(os.path.join(current_dir, "..", ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# Try to import viralmonitor if available (optional dependency)
try:
    from viralmonitor.utils.db import get_total_amount, remove_amount
    VIRALMONITOR_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    logger = logging.getLogger(__name__)
    logger.warning("viralmonitor module not available, using fallback for reply balance operations")
    VIRALMONITOR_AVAILABLE = False
    get_total_amount = None
    remove_amount = None

logger = logging.getLogger(__name__)

BalanceType = Literal["affiliate", "reply"]

def init_operations_ledger():
    """Initialize operations ledger for idempotency."""
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS balance_operations (
                operation_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                balance_type TEXT NOT NULL,
                amount REAL NOT NULL,
                operation_type TEXT NOT NULL,
                reason TEXT,
                timestamp TEXT NOT NULL,
                status TEXT DEFAULT 'completed',
                UNIQUE(operation_id)
            );
        ''')
        # Index for performance
        c.execute('CREATE INDEX IF NOT EXISTS idx_balance_ops_user ON balance_operations(user_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_balance_ops_timestamp ON balance_operations(timestamp)')
        conn.commit()

def generate_operation_id(user_id: int, operation_type: str, amount: float) -> str:
    """Generate a unique operation ID for this specific operation."""
    return f"{operation_type}_{user_id}_{amount}_{uuid.uuid4().hex[:8]}"

def is_operation_completed(operation_id: str, conn=None) -> bool:
    """Check if an operation has already been completed."""
    if conn is None:
        # Use separate connection if not provided
        with get_connection(DB_FILE) as temp_conn:
            c = temp_conn.cursor()
            c.execute("SELECT status FROM balance_operations WHERE operation_id = ?", (operation_id,))
            row = c.fetchone()
            return row is not None and row['status'] == 'completed'
    else:
        # Use existing connection
        c = conn.cursor()
        c.execute("SELECT status FROM balance_operations WHERE operation_id = ?", (operation_id,))
        row = c.fetchone()
        return row is not None and row['status'] == 'completed'

def atomic_balance_update(
    user_id: int,
    balance_type: BalanceType,
    amount: float,
    operation_type: str,
    reason: str,
    operation_id: Optional[str] = None,
    max_retries: int = 3
) -> bool:
    """
    Perform atomic balance update with idempotency and retry logic.
    
    Args:
        user_id: User ID
        balance_type: "affiliate" or "reply"
        amount: Amount to add/subtract (negative for debit)
        operation_type: Type of operation (e.g., "withdraw", "bonus")
        reason: Human-readable reason
        operation_id: Optional operation ID for idempotency
        max_retries: Maximum number of retries for database locked errors
    
    Returns:
        True if successful, False otherwise
    """
    if operation_id and is_operation_completed(operation_id):
        logger.info(f"Operation {operation_id} already completed, skipping")
        return True
    
    if not operation_id:
        operation_id = generate_operation_id(user_id, operation_type, abs(amount))
    
    # Initialize ledger outside of transaction to avoid deadlocks
    init_operations_ledger()
    
    # Retry logic for database locked errors
    import time
    for attempt in range(max_retries):
        try:
            return _perform_balance_update(user_id, balance_type, amount, operation_type, reason, operation_id)
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e).lower() and attempt < max_retries - 1:
                # Exponential backoff
                wait_time = 0.1 * (2 ** attempt)
                logger.warning(f"Database locked, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
            else:
                logger.error(f"Database error in atomic_balance_update: {e}")
                return False
    
    return False

def _perform_balance_update(
    user_id: int,
    balance_type: BalanceType,
    amount: float,
    operation_type: str,
    reason: str,
    operation_id: str
) -> bool:
    """Internal function to perform the actual balance update."""
    with get_connection(DB_FILE) as conn:
        try:
            c = conn.cursor()
            
            # Start exclusive transaction (SQLite-compatible locking)
            conn.execute("BEGIN EXCLUSIVE")
            
            # Double-check operation completion inside transaction
            if operation_id and is_operation_completed(operation_id, conn):
                logger.info(f"Operation {operation_id} already completed (double-check), skipping")
                conn.rollback()
                return True
            
            # Get current balance and update atomically
            if balance_type == "affiliate":
                # For withdrawals (amount < 0), use atomic UPDATE with balance check
                if amount < 0:
                    # Atomic update: only succeed if balance is sufficient
                    result = c.execute(
                        "UPDATE users SET affiliate_balance = affiliate_balance + ? WHERE id = ? AND affiliate_balance >= ?",
                        (amount, user_id, abs(amount))
                    )
                    if result.rowcount == 0:
                        # Either user doesn't exist or insufficient balance
                        c.execute("SELECT affiliate_balance FROM users WHERE id = ?", (user_id,))
                        row = c.fetchone()
                        current_balance = row['affiliate_balance'] if row else 0.0
                        logger.warning(f"Insufficient affiliate balance for user {user_id}: requested {abs(amount)}, available {current_balance}")
                        conn.rollback()
                        return False
                else:
                    # For deposits (amount > 0), simple atomic update
                    c.execute(
                        "UPDATE users SET affiliate_balance = affiliate_balance + ? WHERE id = ?",
                        (amount, user_id)
                    )
                
            elif balance_type == "reply":
                # For reply balance, use atomic UPDATE approach
                # First ensure row exists
                c.execute("""
                    INSERT OR IGNORE INTO reply_balances 
                    (user_id, balance, total_posts, daily_posts) 
                    VALUES (?, 0.0, 0, 0)
                """, (user_id,))
                
                # Atomic update with balance check for withdrawals
                if amount < 0:
                    # Debit operation - only succeed if balance is sufficient
                    result = c.execute("""
                        UPDATE reply_balances 
                        SET balance = balance + ? 
                        WHERE user_id = ? AND balance >= ?
                    """, (amount, user_id, abs(amount)))
                    
                    if result.rowcount == 0:
                        # Insufficient balance
                        c.execute("SELECT balance FROM reply_balances WHERE user_id = ?", (user_id,))
                        row = c.fetchone()
                        current_balance = row['balance'] if row else 0.0
                        logger.warning(f"Insufficient reply balance for user {user_id}: requested {abs(amount)}, available {current_balance}")
                        conn.rollback()
                        return False
                else:
                    # Credit operation - simple atomic update
                    c.execute("""
                        UPDATE reply_balances 
                        SET balance = balance + ? 
                        WHERE user_id = ?
                    """, (amount, user_id))
            
            # Record operation in ledger
            c.execute("""
                INSERT INTO balance_operations 
                (operation_id, user_id, balance_type, amount, operation_type, reason, timestamp, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'completed')
            """, (
                operation_id,
                user_id,
                balance_type,
                amount,
                operation_type,
                reason,
                datetime.utcnow().isoformat()
            ))
            
            conn.commit()
            logger.info(f"Balance operation completed: {operation_id} - User {user_id}, {balance_type} balance changed by {amount}")
            return True
            
        except sqlite3.OperationalError as e:
            # Let database locked errors bubble up for retry
            conn.rollback()
            raise
        except sqlite3.Error as e:
            logger.error(f"Database error in _perform_balance_update: {e}")
            conn.rollback()
            return False
        except Exception as e:
            logger.error(f"Unexpected error in _perform_balance_update: {e}")
            conn.rollback()
            return False
            return False

def atomic_withdraw_operation(
    user_id: int,
    balance_type: BalanceType,
    amount: float,
    reason: str = "Withdrawal",
    operation_id: Optional[str] = None
) -> bool:
    """
    Perform atomic withdrawal operation.
    
    Args:
        user_id: User ID
        balance_type: "affiliate" or "reply"
        amount: Positive amount to withdraw
        reason: Withdrawal reason
        operation_id: Optional operation ID for idempotency
    
    Returns:
        True if successful, False otherwise
    """
    if amount <= 0:
        logger.error("Withdrawal amount must be positive")
        return False
    
    return atomic_balance_update(
        user_id=user_id,
        balance_type=balance_type,
        amount=-amount,  # Negative for withdrawal
        operation_type="withdraw",
        reason=reason,
        operation_id=operation_id
    )

def atomic_deposit_operation(
    user_id: int,
    balance_type: BalanceType,
    amount: float,
    reason: str = "Deposit",
    operation_id: Optional[str] = None
) -> bool:
    """
    Perform atomic deposit operation.
    
    Args:
        user_id: User ID
        balance_type: "affiliate" or "reply"
        amount: Positive amount to deposit
        reason: Deposit reason
        operation_id: Optional operation ID for idempotency
    
    Returns:
        True if successful, False otherwise
    """
    if amount <= 0:
        logger.error("Deposit amount must be positive")
        return False
    
    return atomic_balance_update(
        user_id=user_id,
        balance_type=balance_type,
        amount=amount,  # Positive for deposit
        operation_type="deposit",
        reason=reason,
        operation_id=operation_id
    )

def get_balance_safely(user_id: int, balance_type: BalanceType) -> float:
    """
    Get balance with proper error handling.
    
    Args:
        user_id: User ID
        balance_type: "affiliate" or "reply"
    
    Returns:
        Current balance or 0.0 if user not found
    """
    try:
        if balance_type == "affiliate":
            with get_connection(DB_FILE) as conn:
                c = conn.cursor()
                c.execute("SELECT affiliate_balance FROM users WHERE id = ?", (user_id,))
                row = c.fetchone()
                return row['affiliate_balance'] if row else 0.0
        elif balance_type == "reply":
            if VIRALMONITOR_AVAILABLE and get_total_amount:
                return get_total_amount(user_id)
            else:
                # Fallback to reply_balances table
                with get_connection(DB_FILE) as conn:
                    c = conn.cursor()
                    c.execute("SELECT balance FROM reply_balances WHERE user_id = ?", (user_id,))
                    row = c.fetchone()
                    return row['balance'] if row else 0.0
        else:
            logger.error(f"Invalid balance type: {balance_type}")
            return 0.0
    except Exception as e:
        logger.error(f"Error getting {balance_type} balance for user {user_id}: {e}")
        return 0.0
        return 0.0

def validate_withdrawal_request(user_id: int, balance_type: BalanceType, amount: float) -> tuple[bool, str]:
    """
    Validate withdrawal request before processing.
    
    Args:
        user_id: User ID
        balance_type: "affiliate" or "reply"
        amount: Amount to withdraw
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if amount <= 0:
        return False, "Withdrawal amount must be positive"
    
    current_balance = get_balance_safely(user_id, balance_type)
    
    if amount > current_balance:
        return False, f"Insufficient {balance_type} balance: requested ${amount:.2f}, available ${current_balance:.2f}"
    
    # Additional validation - ensure the balance belongs to the requesting user
    from utils.db_utils import get_user
    user = get_user(user_id)
    if not user:
        return False, "User not found"
    
    return True, ""