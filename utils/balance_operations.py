#!/usr/bin/env python3
# utils/balance_operations.py
# Atomic balance operations with idempotency support

import sqlite3
import uuid
import logging
from typing import Optional, Literal
from datetime import datetime
from utils.db_utils import get_connection, DB_FILE
from viralmonitor.utils.db import get_total_amount, remove_amount

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
    operation_id: Optional[str] = None
) -> bool:
    """
    Perform atomic balance update with idempotency.
    
    Args:
        user_id: User ID
        balance_type: "affiliate" or "reply"
        amount: Amount to add/subtract (negative for debit)
        operation_type: Type of operation (e.g., "withdraw", "bonus")
        reason: Human-readable reason
        operation_id: Optional operation ID for idempotency
    
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
            
            # Get current balance
            if balance_type == "affiliate":
                c.execute(
                    "SELECT affiliate_balance FROM users WHERE id = ?",
                    (user_id,)
                )
                row = c.fetchone()
                current_balance = row['affiliate_balance'] if row else 0.0
                
                # Check sufficient funds for debit operations
                if amount < 0 and abs(amount) > current_balance:
                    logger.warning(f"Insufficient affiliate balance for user {user_id}: requested {abs(amount)}, available {current_balance}")
                    conn.rollback()
                    return False
                
                # Update balance
                new_balance = current_balance + amount
                c.execute(
                    "UPDATE users SET affiliate_balance = ? WHERE id = ?",
                    (new_balance, user_id)
                )
                
            elif balance_type == "reply":
                # For reply balance, get current balance safely
                from viralmonitor.utils.db import get_total_amount
                current_balance = get_total_amount(user_id)
                
                if amount < 0 and abs(amount) > current_balance:
                    logger.warning(f"Insufficient reply balance for user {user_id}: requested {abs(amount)}, available {current_balance}")
                    conn.rollback()
                    return False
                
                # Update reply balance
                if amount < 0:
                    # Debit operation
                    new_balance = current_balance + amount  # amount is negative
                    c.execute("""
                        INSERT OR REPLACE INTO reply_balances 
                        (user_id, balance, total_posts, daily_posts) 
                        VALUES (
                            ?, 
                            ?,
                            COALESCE((SELECT total_posts FROM reply_balances WHERE user_id = ?), 0),
                            COALESCE((SELECT daily_posts FROM reply_balances WHERE user_id = ?), 0)
                        )
                    """, (user_id, new_balance, user_id, user_id))
                else:
                    # Credit operation
                    c.execute("""
                        INSERT OR REPLACE INTO reply_balances 
                        (user_id, balance, total_posts, daily_posts) 
                        VALUES (
                            ?, 
                            COALESCE((SELECT balance FROM reply_balances WHERE user_id = ?), 0) + ?,
                            COALESCE((SELECT total_posts FROM reply_balances WHERE user_id = ?), 0),
                            COALESCE((SELECT daily_posts FROM reply_balances WHERE user_id = ?), 0)
                        )
                    """, (user_id, user_id, amount, user_id, user_id))
            
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
            
        except sqlite3.Error as e:
            logger.error(f"Database error in atomic_balance_update: {e}")
            conn.rollback()
            return False
        except Exception as e:
            logger.error(f"Unexpected error in atomic_balance_update: {e}")
            conn.rollback()
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
            from utils.db_utils import get_affiliate_balance
            return get_affiliate_balance(user_id)
        elif balance_type == "reply":
            return get_total_amount(user_id)
        else:
            logger.error(f"Invalid balance type: {balance_type}")
            return 0.0
    except Exception as e:
        logger.error(f"Error getting {balance_type} balance for user {user_id}: {e}")
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