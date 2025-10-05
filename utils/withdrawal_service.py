#!/usr/bin/env python3
# utils/withdrawal_service.py
# Withdrawal service with automatic vs manual payment modes

import sqlite3
import uuid
import os
import logging
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from enum import Enum
from dataclasses import dataclass

from utils.db_utils import get_connection, DB_FILE
from utils.balance_operations import atomic_withdraw_operation
from utils.api_client import get_flutterwave_client, APIError

logger = logging.getLogger(__name__)

class PaymentMode(Enum):
    AUTOMATIC = "automatic"
    MANUAL = "manual"

    @classmethod
    def from_withdrawal(cls, wm: "WithdrawalMode") -> "PaymentMode":
        return cls(wm.value)


class AdminApprovalState(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

class WithdrawalStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"

@dataclass
class Withdrawal:
    """Withdrawal model with new payment mode features."""
    id: Optional[int] = None
    user_id: int = None
    amount_usd: float = None
    amount_ngn: float = None
    payment_mode: PaymentMode = PaymentMode.AUTOMATIC
    admin_approval_state: Optional[AdminApprovalState] = None
    admin_id: Optional[int] = None
    account_name: str = None
    account_number: str = None
    bank_name: str = None
    bank_details_raw: str = None
    is_affiliate_withdrawal: bool = False
    status: WithdrawalStatus = WithdrawalStatus.PENDING
    approved_at: Optional[str] = None
    processed_at: Optional[str] = None
    failure_reason: Optional[str] = None
    flutterwave_reference: Optional[str] = None
    flutterwave_trace_id: Optional[str] = None
    operation_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Withdrawal':
        """Create Withdrawal from database row."""
        return cls(
            id=data.get('id'),
            user_id=data.get('user_id'),
            amount_usd=data.get('amount_usd'),
            amount_ngn=data.get('amount_ngn'),
            payment_mode=PaymentMode(data.get('payment_mode', 'automatic')),
            admin_approval_state=AdminApprovalState(data['admin_approval_state']) if data.get('admin_approval_state') else None,
            admin_id=data.get('admin_id'),
            account_name=data.get('account_name'),
            account_number=data.get('account_number'),
            bank_name=data.get('bank_name'),
            bank_details_raw=data.get('bank_details_raw'),
            is_affiliate_withdrawal=bool(data.get('is_affiliate_withdrawal', 0)),
            status=WithdrawalStatus(data.get('status', 'pending')),
            approved_at=data.get('approved_at'),
            processed_at=data.get('processed_at'),
            failure_reason=data.get('failure_reason'),
            flutterwave_reference=data.get('flutterwave_reference'),
            flutterwave_trace_id=data.get('flutterwave_trace_id'),
            operation_id=data.get('operation_id'),
            created_at=data.get('created_at'),
            updated_at=data.get('updated_at')
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            'user_id': self.user_id,
            'amount_usd': self.amount_usd,
            'amount_ngn': self.amount_ngn,
            'payment_mode': self.payment_mode.value,
            'admin_approval_state': self.admin_approval_state.value if self.admin_approval_state else None,
            'admin_id': self.admin_id,
            'account_name': self.account_name,
            'account_number': self.account_number,
            'bank_name': self.bank_name,
            'bank_details_raw': self.bank_details_raw,
            'is_affiliate_withdrawal': int(self.is_affiliate_withdrawal),
            'status': self.status.value,
            'approved_at': self.approved_at,
            'processed_at': self.processed_at,
            'failure_reason': self.failure_reason,
            'flutterwave_reference': self.flutterwave_reference,
            'flutterwave_trace_id': self.flutterwave_trace_id,
            'operation_id': self.operation_id,
            'updated_at': datetime.utcnow().isoformat()
        }

class WithdrawalService:
    """Service for managing withdrawals with automatic and manual payment modes."""
    
    def __init__(self):
        self.flutterwave_client = get_flutterwave_client()
    
    def create_withdrawal(
        self,
        user_id: int,
        amount_usd: float,
        amount_ngn: float,
        account_name: str,
        account_number: str,
        bank_name: str,
        bank_details_raw: str,
        is_affiliate_withdrawal: bool = False,
        payment_mode: PaymentMode = PaymentMode.AUTOMATIC
    ) -> Withdrawal:
        """
        Create a new withdrawal request.
        
        Args:
            user_id: User ID
            amount_usd: Amount in USD
            amount_ngn: Amount in NGN
            account_name: Bank account name
            account_number: Bank account number
            bank_name: Bank name
            bank_details_raw: Raw bank details as provided by user
            is_affiliate_withdrawal: Whether this is an affiliate withdrawal
            payment_mode: Payment mode (automatic or manual)
        
        Returns:
            Created Withdrawal object
        """
        
        # Check if admin approval is required
        disable_admin_approval = os.getenv("DISABLE_ADMIN_APPROVAL", "false").lower() == "true"
        
        # Create withdrawal object
        withdrawal = Withdrawal(
            user_id=user_id,
            amount_usd=amount_usd,
            amount_ngn=amount_ngn,
            payment_mode=payment_mode,
            account_name=account_name,
            account_number=account_number,
            bank_name=bank_name,
            bank_details_raw=bank_details_raw,
            is_affiliate_withdrawal=is_affiliate_withdrawal,
            status=WithdrawalStatus.PENDING,
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat()
        )
        
        # Set approval state - both manual AND automatic withdrawals require approval
        # unless DISABLE_ADMIN_APPROVAL is set (for testing/staging)
        if not disable_admin_approval:
            withdrawal.admin_approval_state = AdminApprovalState.PENDING
            logger.info(f"Withdrawal created with pending admin approval (user {user_id}, amount ${amount_usd})")
        else:
            logger.warning(f"Admin approval disabled - withdrawal created without approval requirement")
        
        # Generate operation ID for idempotency
        withdrawal.operation_id = f"withdraw_{user_id}_{amount_usd}_{uuid.uuid4().hex[:8]}"
        
        # Save to database
        withdrawal_id = self._save_withdrawal(withdrawal)
        withdrawal.id = withdrawal_id
        
        # Log creation
        self._log_audit_event(
            withdrawal_id=withdrawal_id,
            action="created",
            new_status=withdrawal.status.value,
            metadata={
                "payment_mode": payment_mode.value,
                "amount_usd": amount_usd,
                "amount_ngn": amount_ngn
            }
        )
        
        logger.info(f"Withdrawal {withdrawal_id} created for user {user_id} in {payment_mode.value} mode")
        
        return withdrawal
    
    def process_automatic_withdrawal(self, withdrawal: Withdrawal) -> bool:
        """
        Process automatic withdrawal using Flutterwave API.
        
        DEPRECATED: This method should not be called directly. Use approve_withdrawal_by_mode instead.
        This ensures proper admin approval workflow is followed.
        
        Args:
            withdrawal: Withdrawal to process
            
        Returns:
            True if successful, False otherwise
        """
        
        logger.warning(
            f"process_automatic_withdrawal called directly for withdrawal {withdrawal.id}. "
            "This method is deprecated - use approve_withdrawal_by_mode instead to ensure approval workflow."
        )
        
        if withdrawal.payment_mode != PaymentMode.AUTOMATIC:
            raise ValueError("Cannot process manual withdrawal as automatic")
        
        # CRITICAL: Check that withdrawal has been approved
        # This prevents premature API calls before admin approval
        if withdrawal.admin_approval_state != AdminApprovalState.APPROVED:
            error_msg = (
                f"Cannot process withdrawal {withdrawal.id} - admin approval required. "
                f"Current state: {withdrawal.admin_approval_state}"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        try:
            # Update status to processing
            withdrawal.status = WithdrawalStatus.PROCESSING
            self._update_withdrawal(withdrawal)
            
            # Generate reference
            reference = f"VCW_{withdrawal.id}_{uuid.uuid4().hex[:8]}"
            withdrawal.flutterwave_reference = reference
            
            # Call Flutterwave API
            response = self.flutterwave_client.initiate_transfer(
                amount=withdrawal.amount_ngn,
                beneficiary_name=withdrawal.account_name,
                account_number=withdrawal.account_number,
                account_bank=withdrawal.bank_name,
                reference=reference
            )
            
            # Store trace ID
            withdrawal.flutterwave_trace_id = response.get('trace_id')
            
            if response.get('success'):
                # Deduct balance atomically
                balance_type = "affiliate" if withdrawal.is_affiliate_withdrawal else "reply"
                success = atomic_withdraw_operation(
                    user_id=withdrawal.user_id,
                    balance_type=balance_type,
                    amount=withdrawal.amount_usd,
                    reason=f"Withdrawal to {withdrawal.account_name}",
                    operation_id=withdrawal.operation_id
                )
                
                if success:
                    withdrawal.status = WithdrawalStatus.COMPLETED
                    withdrawal.processed_at = datetime.utcnow().isoformat()
                    
                    self._log_audit_event(
                        withdrawal_id=withdrawal.id,
                        action="completed",
                        old_status="processing",
                        new_status="completed",
                        metadata={
                            "flutterwave_reference": reference,
                            "trace_id": response.get('trace_id')
                        }
                    )
                    
                    logger.info(f"Automatic withdrawal {withdrawal.id} completed successfully")
                    return True
                else:
                    # Balance deduction failed
                    withdrawal.status = WithdrawalStatus.FAILED
                    withdrawal.failure_reason = "Balance deduction failed"
                    
                    self._log_audit_event(
                        withdrawal_id=withdrawal.id,
                        action="failed",
                        old_status="processing",
                        new_status="failed",
                        metadata={"reason": "Balance deduction failed"}
                    )
                    
                    logger.error(f"Automatic withdrawal {withdrawal.id} failed: balance deduction failed")
                    return False
            else:
                # Flutterwave transfer failed
                withdrawal.status = WithdrawalStatus.FAILED
                withdrawal.failure_reason = response.get('error', 'Flutterwave transfer failed')
                
                self._log_audit_event(
                    withdrawal_id=withdrawal.id,
                    action="failed",
                    old_status="processing",
                    new_status="failed",
                    metadata={
                        "reason": "Flutterwave transfer failed",
                        "error": response.get('error')
                    }
                )
                
                logger.error(f"Automatic withdrawal {withdrawal.id} failed: {withdrawal.failure_reason}")
                return False
        
        except APIError as e:
            withdrawal.status = WithdrawalStatus.FAILED
            withdrawal.failure_reason = f"API error: {e.message}"
            
            self._log_audit_event(
                withdrawal_id=withdrawal.id,
                action="failed",
                old_status="processing",
                new_status="failed",
                metadata={"reason": f"API error: {e.message}"}
            )
            
            logger.error(f"Automatic withdrawal {withdrawal.id} failed with API error: {e.message}")
            return False
        
        except Exception as e:
            withdrawal.status = WithdrawalStatus.FAILED
            withdrawal.failure_reason = f"Unexpected error: {str(e)}"
            
            self._log_audit_event(
                withdrawal_id=withdrawal.id,
                action="failed",
                old_status="processing",
                new_status="failed",
                metadata={"reason": f"Unexpected error: {str(e)}"}
            )
            
            logger.error(f"Automatic withdrawal {withdrawal.id} failed with unexpected error: {str(e)}")
            return False
        
        finally:
            self._update_withdrawal(withdrawal)
    
    def approve_manual_withdrawal(self, withdrawal_id: int, admin_id: int, reason: str = None) -> bool:
        """
        Approve a manual withdrawal (idempotent).
        
        Args:
            withdrawal_id: Withdrawal ID to approve
            admin_id: Admin user ID performing the approval
            reason: Optional reason for approval
            
        Returns:
            True if successful, False otherwise
        """
        
        with get_connection(DB_FILE) as conn:
            try:
                conn.execute('BEGIN IMMEDIATE')  # Start exclusive transaction
                
                # Get withdrawal with row lock
                c = conn.cursor()
                c.execute('''
                    SELECT * FROM withdrawals 
                    WHERE id = ? AND payment_mode = 'manual'
                    ORDER BY id
                ''', (withdrawal_id,))
                
                row = c.fetchone()
                if not row:
                    logger.warning(f"Manual withdrawal {withdrawal_id} not found")
                    return False
                
                # Convert row to dict
                columns = [desc[0] for desc in c.description]
                withdrawal_data = dict(zip(columns, row))
                withdrawal = Withdrawal.from_dict(withdrawal_data)
                
                # Check if already processed (idempotency)
                if withdrawal.admin_approval_state == AdminApprovalState.APPROVED:
                    logger.info(f"Manual withdrawal {withdrawal_id} already approved")
                    return True
                
                if withdrawal.admin_approval_state != AdminApprovalState.PENDING:
                    logger.warning(f"Manual withdrawal {withdrawal_id} is not in pending state: {withdrawal.admin_approval_state}")
                    return False
                
                # Deduct balance directly within this transaction (to avoid nested transaction locks)
                balance_type = "affiliate" if withdrawal.is_affiliate_withdrawal else "reply"
                
                # Check if operation already completed (idempotency)
                c.execute("SELECT status FROM balance_operations WHERE operation_id = ?", (withdrawal.operation_id,))
                op_row = c.fetchone()
                if op_row and op_row['status'] == 'completed':
                    logger.info(f"Balance operation {withdrawal.operation_id} already completed")
                else:
                    # Deduct balance using atomic UPDATE with balance check
                    if balance_type == "affiliate":
                        # Atomic update: only succeed if balance is sufficient
                        result = c.execute(
                            "UPDATE users SET affiliate_balance = affiliate_balance - ? WHERE id = ? AND affiliate_balance >= ?",
                            (withdrawal.amount_usd, withdrawal.user_id, withdrawal.amount_usd)
                        )
                        
                        if result.rowcount == 0:
                            # Either user doesn't exist or insufficient balance
                            c.execute("SELECT affiliate_balance FROM users WHERE id = ?", (withdrawal.user_id,))
                            bal_row = c.fetchone()
                            current_balance = bal_row['affiliate_balance'] if bal_row else 0.0
                            logger.error(f"Insufficient affiliate balance for withdrawal {withdrawal_id}: {current_balance} < {withdrawal.amount_usd}")
                            conn.rollback()
                            return False
                        
                    elif balance_type == "reply":
                        # First ensure row exists
                        c.execute("""
                            INSERT OR IGNORE INTO reply_balances 
                            (user_id, balance, total_posts, daily_posts) 
                            VALUES (?, 0.0, 0, 0)
                        """, (withdrawal.user_id,))
                        
                        # Atomic update: only succeed if balance is sufficient
                        result = c.execute("""
                            UPDATE reply_balances 
                            SET balance = balance - ? 
                            WHERE user_id = ? AND balance >= ?
                        """, (withdrawal.amount_usd, withdrawal.user_id, withdrawal.amount_usd))
                        
                        if result.rowcount == 0:
                            # Insufficient balance
                            c.execute("SELECT balance FROM reply_balances WHERE user_id = ?", (withdrawal.user_id,))
                            bal_row = c.fetchone()
                            current_balance = bal_row['balance'] if bal_row else 0.0
                            logger.error(f"Insufficient reply balance for withdrawal {withdrawal_id}: {current_balance} < {withdrawal.amount_usd}")
                            conn.rollback()
                            return False
                    
                    # Record operation in ledger
                    from datetime import datetime
                    c.execute("""
                        INSERT INTO balance_operations 
                        (operation_id, user_id, balance_type, amount, operation_type, reason, timestamp, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 'completed')
                    """, (
                        withdrawal.operation_id,
                        withdrawal.user_id,
                        balance_type,
                        -withdrawal.amount_usd,  # Negative for withdrawal
                        "withdraw",
                        f"Manual withdrawal approved by admin {admin_id}",
                        datetime.utcnow().isoformat()
                    ))
                    
                    logger.info(f"Balance deducted for manual withdrawal {withdrawal_id}: {withdrawal.amount_usd} from {balance_type}")
                
                # Update withdrawal
                withdrawal.admin_approval_state = AdminApprovalState.APPROVED
                withdrawal.status = WithdrawalStatus.COMPLETED
                withdrawal.admin_id = admin_id
                withdrawal.approved_at = datetime.utcnow().isoformat()
                withdrawal.processed_at = datetime.utcnow().isoformat()
                withdrawal.updated_at = datetime.utcnow().isoformat()
                
                # Save changes
                self._update_withdrawal_in_transaction(withdrawal, conn)
                
                # Log audit event
                self._log_audit_event_in_transaction(
                    withdrawal_id=withdrawal_id,
                    admin_id=admin_id,
                    action="approved",
                    old_status="pending",
                    new_status="completed",
                    old_approval_state="pending",
                    new_approval_state="approved",
                    reason=reason,
                    conn=conn
                )
                
                conn.commit()
                logger.info(f"Manual withdrawal {withdrawal_id} approved by admin {admin_id}")
                return True
                
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to approve manual withdrawal {withdrawal_id}: {str(e)}")
                return False
    
    def reject_manual_withdrawal(self, withdrawal_id: int, admin_id: int, reason: str = None) -> bool:
        """
        Reject a manual withdrawal (idempotent).
        
        Args:
            withdrawal_id: Withdrawal ID to reject
            admin_id: Admin user ID performing the rejection
            reason: Optional reason for rejection
            
        Returns:
            True if successful, False otherwise
        """
        
        with get_connection(DB_FILE) as conn:
            try:
                conn.execute('BEGIN IMMEDIATE')  # Start exclusive transaction
                
                # Get withdrawal with row lock
                c = conn.cursor()
                c.execute('''
                    SELECT * FROM withdrawals 
                    WHERE id = ? AND payment_mode = 'manual'
                    ORDER BY id
                ''', (withdrawal_id,))
                
                row = c.fetchone()
                if not row:
                    logger.warning(f"Manual withdrawal {withdrawal_id} not found")
                    return False
                
                # Convert row to dict
                columns = [desc[0] for desc in c.description]
                withdrawal_data = dict(zip(columns, row))
                withdrawal = Withdrawal.from_dict(withdrawal_data)
                
                # Check if already processed (idempotency)
                if withdrawal.admin_approval_state == AdminApprovalState.REJECTED:
                    logger.info(f"Manual withdrawal {withdrawal_id} already rejected")
                    return True
                
                if withdrawal.admin_approval_state != AdminApprovalState.PENDING:
                    logger.warning(f"Manual withdrawal {withdrawal_id} is not in pending state: {withdrawal.admin_approval_state}")
                    return False
                
                # Update withdrawal
                withdrawal.admin_approval_state = AdminApprovalState.REJECTED
                withdrawal.status = WithdrawalStatus.REJECTED
                withdrawal.admin_id = admin_id
                withdrawal.failure_reason = reason or "Rejected by admin"
                withdrawal.processed_at = datetime.utcnow().isoformat()
                withdrawal.updated_at = datetime.utcnow().isoformat()
                
                # Save changes
                self._update_withdrawal_in_transaction(withdrawal, conn)
                
                # Log audit event
                self._log_audit_event_in_transaction(
                    withdrawal_id=withdrawal_id,
                    admin_id=admin_id,
                    action="rejected",
                    old_status="pending",
                    new_status="rejected",
                    old_approval_state="pending",
                    new_approval_state="rejected",
                    reason=reason,
                    conn=conn
                )
                
                conn.commit()
                logger.info(f"Manual withdrawal {withdrawal_id} rejected by admin {admin_id}")
                return True
                
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to reject manual withdrawal {withdrawal_id}: {str(e)}")
                return False
    
    def reject_withdrawal(self, withdrawal_id: int, admin_id: int, reason: str = None) -> bool:
        """
        Reject a withdrawal (works for both manual and automatic modes).
        
        Args:
            withdrawal_id: Withdrawal ID to reject
            admin_id: Admin user ID performing the rejection
            reason: Optional reason for rejection
            
        Returns:
            True if successful, False otherwise
        """
        
        with get_connection(DB_FILE) as conn:
            try:
                conn.execute('BEGIN IMMEDIATE')  # Start exclusive transaction
                
                # Get withdrawal with row lock
                c = conn.cursor()
                c.execute('''
                    SELECT * FROM withdrawals 
                    WHERE id = ?
                    ORDER BY id
                ''', (withdrawal_id,))
                
                row = c.fetchone()
                if not row:
                    logger.warning(f"Withdrawal {withdrawal_id} not found")
                    return False
                
                # Convert row to dict
                columns = [desc[0] for desc in c.description]
                withdrawal_data = dict(zip(columns, row))
                withdrawal = Withdrawal.from_dict(withdrawal_data)
                
                # Check if already rejected (idempotency)
                if withdrawal.admin_approval_state == AdminApprovalState.REJECTED:
                    logger.info(f"Withdrawal {withdrawal_id} already rejected")
                    return True
                
                if withdrawal.admin_approval_state != AdminApprovalState.PENDING:
                    logger.warning(f"Withdrawal {withdrawal_id} is not in pending state: {withdrawal.admin_approval_state}")
                    return False
                
                # Update withdrawal
                withdrawal.admin_approval_state = AdminApprovalState.REJECTED
                withdrawal.status = WithdrawalStatus.REJECTED
                withdrawal.admin_id = admin_id
                withdrawal.failure_reason = reason or "Rejected by admin"
                withdrawal.processed_at = datetime.utcnow().isoformat()
                withdrawal.updated_at = datetime.utcnow().isoformat()
                
                # Save changes
                self._update_withdrawal_in_transaction(withdrawal, conn)
                
                # Log audit event
                self._log_audit_event_in_transaction(
                    withdrawal_id=withdrawal_id,
                    admin_id=admin_id,
                    action="rejected",
                    old_status="pending",
                    new_status="rejected",
                    old_approval_state="pending",
                    new_approval_state="rejected",
                    reason=reason,
                    conn=conn
                )
                
                conn.commit()
                logger.info(f"Withdrawal {withdrawal_id} rejected by admin {admin_id}")
                return True
                
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to reject withdrawal {withdrawal_id}: {str(e)}")
                return False
    
    def approve_withdrawal_by_mode(self, withdrawal_id: int, admin_id: int, reason: str = None) -> bool:
        """
        Approve a withdrawal based on current system mode (idempotent).
        Reads withdrawal mode from settings at approval time.
        
        Args:
            withdrawal_id: Withdrawal ID to approve
            admin_id: Admin user ID performing the approval
            reason: Optional reason for approval
            
        Returns:
            True if successful, False otherwise
        """
        # Import here to avoid circular dependency
        from utils.withdrawal_settings import get_withdrawal_mode, WithdrawalMode
        
        # Get current system mode at approval time
        current_mode = get_withdrawal_mode()
        
        with get_connection(DB_FILE) as conn:
            try:
                conn.execute('BEGIN IMMEDIATE')  # Start exclusive transaction
                
                # Get withdrawal with row lock (SQLite compatible)
                c = conn.cursor()
                c.execute('''
                    SELECT * FROM withdrawals 
                    WHERE id = ?
                    ORDER BY id
                ''', (withdrawal_id,))
                
                row = c.fetchone()
                if not row:
                    logger.warning(f"Withdrawal {withdrawal_id} not found")
                    return False
                
                # Convert row to dict
                columns = [desc[0] for desc in c.description]
                withdrawal_data = dict(zip(columns, row))
                withdrawal = Withdrawal.from_dict(withdrawal_data)
                
                # Check if already processed (idempotency)
                if withdrawal.status in [WithdrawalStatus.COMPLETED, WithdrawalStatus.REJECTED]:
                    logger.info(f"Withdrawal {withdrawal_id} already processed: {withdrawal.status}")
                    return withdrawal.status == WithdrawalStatus.COMPLETED
                
                # Check if withdrawal is in valid state for approval
                if withdrawal.status != WithdrawalStatus.PENDING:
                    logger.warning(f"Withdrawal {withdrawal_id} is not in pending state: {withdrawal.status}")
                    return False
                
                # Process based on current mode
                if current_mode == WithdrawalMode.MANUAL:
                    return self._approve_withdrawal_manual_mode(withdrawal, admin_id, reason, conn)
                else:  # AUTOMATIC
                    return self._approve_withdrawal_automatic_mode(withdrawal, admin_id, reason, conn)
                    
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to approve withdrawal {withdrawal_id}: {str(e)}")
                return False

    def _approve_withdrawal_manual_mode(self, withdrawal: Withdrawal, admin_id: int, reason: str, conn) -> bool:
        """Approve withdrawal in manual mode - deduct balance only, no external API call."""
        try:
            c = conn.cursor()
            balance_type = "affiliate" if withdrawal.is_affiliate_withdrawal else "reply"
            
            # Check if operation already completed (idempotency)
            c.execute("SELECT status FROM balance_operations WHERE operation_id = ?", (withdrawal.operation_id,))
            op_row = c.fetchone()
            if op_row and op_row['status'] == 'completed':
                logger.info(f"Balance operation {withdrawal.operation_id} already completed")
            else:
                # Deduct balance using atomic UPDATE with balance check (same pattern as in approve_manual_withdrawal)
                if balance_type == "affiliate":
                    # Atomic update: only succeed if balance is sufficient
                    result = c.execute(
                        "UPDATE users SET affiliate_balance = affiliate_balance - ? WHERE id = ? AND affiliate_balance >= ?",
                        (withdrawal.amount_usd, withdrawal.user_id, withdrawal.amount_usd)
                    )
                    
                    if result.rowcount == 0:
                        # Either user doesn't exist or insufficient balance
                        c.execute("SELECT affiliate_balance FROM users WHERE id = ?", (withdrawal.user_id,))
                        bal_row = c.fetchone()
                        current_balance = bal_row['affiliate_balance'] if bal_row else 0.0
                        logger.error(f"Insufficient affiliate balance for withdrawal {withdrawal.id}: {current_balance} < {withdrawal.amount_usd}")
                        conn.rollback()
                        return False
                    
                elif balance_type == "reply":
                    # First ensure row exists
                    c.execute("""
                        INSERT OR IGNORE INTO reply_balances 
                        (user_id, balance, total_posts, daily_posts) 
                        VALUES (?, 0.0, 0, 0)
                    """, (withdrawal.user_id,))
                    
                    # Atomic update: only succeed if balance is sufficient
                    result = c.execute("""
                        UPDATE reply_balances 
                        SET balance = balance - ? 
                        WHERE user_id = ? AND balance >= ?
                    """, (withdrawal.amount_usd, withdrawal.user_id, withdrawal.amount_usd))
                    
                    if result.rowcount == 0:
                        # Insufficient balance
                        c.execute("SELECT balance FROM reply_balances WHERE user_id = ?", (withdrawal.user_id,))
                        bal_row = c.fetchone()
                        current_balance = bal_row['balance'] if bal_row else 0.0
                        logger.error(f"Insufficient reply balance for withdrawal {withdrawal.id}: {current_balance} < {withdrawal.amount_usd}")
                        conn.rollback()
                        return False
                
                # Record operation in ledger
                c.execute("""
                    INSERT INTO balance_operations 
                    (operation_id, user_id, balance_type, amount, operation_type, reason, timestamp, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'completed')
                """, (
                    withdrawal.operation_id,
                    withdrawal.user_id,
                    balance_type,
                    -withdrawal.amount_usd,  # Negative for withdrawal
                    "withdraw",
                    f"Manual withdrawal approved by admin {admin_id}",
                    datetime.utcnow().isoformat()
                ))
            
            # Update withdrawal
            withdrawal.status = WithdrawalStatus.COMPLETED
            withdrawal.admin_id = admin_id
            withdrawal.approved_at = datetime.utcnow().isoformat()
            withdrawal.processed_at = datetime.utcnow().isoformat()
            withdrawal.updated_at = datetime.utcnow().isoformat()
            
            # Save changes
            self._update_withdrawal_in_transaction(withdrawal, conn)
            
            # Log audit event
            self._log_audit_event_in_transaction(
                withdrawal_id=withdrawal.id,
                admin_id=admin_id,
                action="approved-manual",
                old_status="pending",
                new_status="completed",
                reason=reason,
                metadata={"mode": "manual", "external_api_called": False},
                conn=conn
            )
            
            conn.commit()
            logger.info(f"Withdrawal {withdrawal.id} approved in manual mode by admin {admin_id}")
            return True
            
        except Exception as e:
            logger.error(f"Manual mode approval failed for withdrawal {withdrawal.id}: {str(e)}")
            raise

    def _approve_withdrawal_automatic_mode(self, withdrawal: Withdrawal, admin_id: int, reason: str, conn) -> bool:
        """Approve withdrawal in automatic mode - deduct balance and call Flutterwave API."""
        try:
            c = conn.cursor()
            balance_type = "affiliate" if withdrawal.is_affiliate_withdrawal else "reply"
            
            # Check if operation already completed (idempotency)
            c.execute("SELECT status FROM balance_operations WHERE operation_id = ?", (withdrawal.operation_id,))
            op_row = c.fetchone()
            if op_row and op_row['status'] == 'completed':
                logger.info(f"Balance operation {withdrawal.operation_id} already completed")
            else:
                # Deduct balance using atomic UPDATE with balance check
                if balance_type == "affiliate":
                    # Atomic update: only succeed if balance is sufficient
                    result = c.execute(
                        "UPDATE users SET affiliate_balance = affiliate_balance - ? WHERE id = ? AND affiliate_balance >= ?",
                        (withdrawal.amount_usd, withdrawal.user_id, withdrawal.amount_usd)
                    )
                    
                    if result.rowcount == 0:
                        # Either user doesn't exist or insufficient balance
                        c.execute("SELECT affiliate_balance FROM users WHERE id = ?", (withdrawal.user_id,))
                        bal_row = c.fetchone()
                        current_balance = bal_row['affiliate_balance'] if bal_row else 0.0
                        logger.error(f"Insufficient affiliate balance for withdrawal {withdrawal.id}: {current_balance} < {withdrawal.amount_usd}")
                        conn.rollback()
                        return False
                    
                elif balance_type == "reply":
                    # First ensure row exists
                    c.execute("""
                        INSERT OR IGNORE INTO reply_balances 
                        (user_id, balance, total_posts, daily_posts) 
                        VALUES (?, 0.0, 0, 0)
                    """, (withdrawal.user_id,))
                    
                    # Atomic update: only succeed if balance is sufficient
                    result = c.execute("""
                        UPDATE reply_balances 
                        SET balance = balance - ? 
                        WHERE user_id = ? AND balance >= ?
                    """, (withdrawal.amount_usd, withdrawal.user_id, withdrawal.amount_usd))
                    
                    if result.rowcount == 0:
                        # Insufficient balance
                        c.execute("SELECT balance FROM reply_balances WHERE user_id = ?", (withdrawal.user_id,))
                        bal_row = c.fetchone()
                        current_balance = bal_row['balance'] if bal_row else 0.0
                        logger.error(f"Insufficient reply balance for withdrawal {withdrawal.id}: {current_balance} < {withdrawal.amount_usd}")
                        conn.rollback()
                        return False
                
                # Record operation in ledger
                c.execute("""
                    INSERT INTO balance_operations 
                    (operation_id, user_id, balance_type, amount, operation_type, reason, timestamp, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'completed')
                """, (
                    withdrawal.operation_id,
                    withdrawal.user_id,
                    balance_type,
                    -withdrawal.amount_usd,  # Negative for withdrawal
                    "withdraw",
                    f"Automatic withdrawal approved by admin {admin_id}",
                    datetime.utcnow().isoformat()
                ))
            
            # Update status to processing
            withdrawal.status = WithdrawalStatus.PROCESSING
            withdrawal.admin_id = admin_id
            withdrawal.approved_at = datetime.utcnow().isoformat()
            withdrawal.updated_at = datetime.utcnow().isoformat()
            
            # Generate reference
            reference = f"VCW_{withdrawal.id}_{uuid.uuid4().hex[:8]}"
            withdrawal.flutterwave_reference = reference
            
            # Save processing state first
            self._update_withdrawal_in_transaction(withdrawal, conn)
            conn.commit()  # Commit the processing state and balance deduction atomically
            
            # Defensive check: verify status is PROCESSING before calling external API
            if withdrawal.status != WithdrawalStatus.PROCESSING:
                error_msg = f"Cannot call Flutterwave API - withdrawal status is {withdrawal.status.value}, expected PROCESSING"
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            # Now call Flutterwave API (outside transaction)
            try:
                response = self.flutterwave_client.initiate_transfer(
                    amount=withdrawal.amount_ngn,
                    beneficiary_name=withdrawal.account_name,
                    account_number=withdrawal.account_number,
                    account_bank=withdrawal.bank_name,
                    reference=reference
                )
                
                # Start new transaction for final update
                with get_connection(DB_FILE) as final_conn:
                    final_conn.execute('BEGIN IMMEDIATE')
                    
                    # Store trace ID
                    withdrawal.flutterwave_trace_id = response.get('trace_id')
                    
                    if response.get('success'):
                        withdrawal.status = WithdrawalStatus.COMPLETED
                        withdrawal.processed_at = datetime.utcnow().isoformat()
                        
                        self._log_audit_event_in_transaction(
                            withdrawal_id=withdrawal.id,
                            admin_id=admin_id,
                            action="approved-automatic",
                            old_status="processing",
                            new_status="completed",
                            reason=reason,
                            metadata={
                                "mode": "automatic",
                                "external_api_called": True,
                                "flutterwave_reference": reference,
                                "trace_id": response.get('trace_id')
                            },
                            conn=final_conn
                        )
                        
                        logger.info(f"Withdrawal {withdrawal.id} approved in automatic mode by admin {admin_id}")
                        
                    else:
                        # Flutterwave transfer failed - rollback balance
                        error_code = response.get('code', 'FLUTTERWAVE_ERROR')
                        error_message = response.get('error', 'Flutterwave transfer failed')
                        correlation_id = str(uuid.uuid4())
                        
                        withdrawal.status = WithdrawalStatus.FAILED
                        withdrawal.failure_reason = error_message
                        
                        # Record error in database
                        self._record_withdrawal_error(
                            withdrawal_id=withdrawal.id,
                            error_code=error_code,
                            error_message=error_message,
                            error_payload=response,
                            request_id=response.get('request_id'),
                            correlation_id=correlation_id,
                            retry_count=0
                        )
                        
                        # Rollback balance deduction
                        rollback_success = self._rollback_balance_deduction(withdrawal, final_conn)
                        if not rollback_success:
                            logger.error(f"Failed to rollback balance for withdrawal {withdrawal.id}")
                        
                        self._log_audit_event_in_transaction(
                            withdrawal_id=withdrawal.id,
                            admin_id=admin_id,
                            action="failed-automatic",
                            old_status="processing",
                            new_status="failed",
                            reason=f"Flutterwave API failed: {error_message}",
                            metadata={
                                "mode": "automatic",
                                "external_api_called": True,
                                "api_error": error_message,
                                "error_code": error_code,
                                "correlation_id": correlation_id,
                                "balance_rolled_back": rollback_success
                            },
                            conn=final_conn
                        )
                        
                        logger.error(f"Withdrawal {withdrawal.id} failed in automatic mode: {withdrawal.failure_reason}")
                        
                        # Send admin notification asynchronously
                        import asyncio
                        try:
                            asyncio.create_task(self._notify_admin_of_error(
                                withdrawal=withdrawal,
                                error_code=error_code,
                                error_message=error_message,
                                correlation_id=correlation_id,
                                error_payload=response
                            ))
                        except Exception as notify_error:
                            logger.error(f"Failed to send error notification: {notify_error}")
                    
                    self._update_withdrawal_in_transaction(withdrawal, final_conn)
                    final_conn.commit()
                    
                    return withdrawal.status == WithdrawalStatus.COMPLETED
                    
            except Exception as api_error:
                # API call failed - rollback balance
                error_code = "API_EXCEPTION"
                error_message = str(api_error)
                correlation_id = str(uuid.uuid4())
                
                with get_connection(DB_FILE) as rollback_conn:
                    rollback_conn.execute('BEGIN IMMEDIATE')
                    
                    withdrawal.status = WithdrawalStatus.FAILED
                    withdrawal.failure_reason = f"API error: {error_message}"
                    
                    # Record error
                    self._record_withdrawal_error(
                        withdrawal_id=withdrawal.id,
                        error_code=error_code,
                        error_message=error_message,
                        error_payload={"exception": str(api_error), "type": type(api_error).__name__},
                        correlation_id=correlation_id,
                        retry_count=0
                    )
                    
                    rollback_success = self._rollback_balance_deduction(withdrawal, rollback_conn)
                    
                    self._log_audit_event_in_transaction(
                        withdrawal_id=withdrawal.id,
                        admin_id=admin_id,
                        action="failed-automatic",
                        old_status="processing",
                        new_status="failed",
                        reason=f"API exception: {error_message}",
                        metadata={
                            "mode": "automatic",
                            "external_api_called": False,
                            "api_exception": error_message,
                            "error_code": error_code,
                            "correlation_id": correlation_id,
                            "balance_rolled_back": rollback_success
                        },
                        conn=rollback_conn
                    )
                    
                    self._update_withdrawal_in_transaction(withdrawal, rollback_conn)
                    rollback_conn.commit()
                    
                    logger.error(f"Withdrawal {withdrawal.id} failed with API error: {error_message}")
                    
                    # Send admin notification
                    import asyncio
                    try:
                        asyncio.create_task(self._notify_admin_of_error(
                            withdrawal=withdrawal,
                            error_code=error_code,
                            error_message=error_message,
                            correlation_id=correlation_id
                        ))
                    except Exception as notify_error:
                        logger.error(f"Failed to send error notification: {notify_error}")
                    
                    return False
                    
        except Exception as e:
            logger.error(f"Automatic mode approval failed for withdrawal {withdrawal.id}: {str(e)}")
            raise

    def _rollback_balance_deduction(self, withdrawal: Withdrawal, conn) -> bool:
        """Rollback balance deduction for failed automatic withdrawal."""
        try:
            balance_type = "affiliate" if withdrawal.is_affiliate_withdrawal else "reply"
            
            # Add balance back (opposite of withdraw operation)
            from utils.balance_operations import atomic_deposit_operation
            success = atomic_deposit_operation(
                user_id=withdrawal.user_id,
                balance_type=balance_type,
                amount=withdrawal.amount_usd,
                reason=f"Rollback for failed withdrawal {withdrawal.id}",
                operation_id=f"rollback_{withdrawal.operation_id}"
            )
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to rollback balance for withdrawal {withdrawal.id}: {str(e)}")
            return False

    def get_withdrawal(self, withdrawal_id: int) -> Optional[Withdrawal]:
        """Get withdrawal by ID."""
        
        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM withdrawals WHERE id = ?', (withdrawal_id,))
            row = c.fetchone()
            
            if row:
                columns = [desc[0] for desc in c.description]
                withdrawal_data = dict(zip(columns, row))
                return Withdrawal.from_dict(withdrawal_data)
            
            return None
    
    def get_pending_withdrawals(self) -> List[Withdrawal]:
        """Get all pending withdrawals (regardless of payment mode)."""
        
        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            c.execute('''
                SELECT * FROM withdrawals 
                WHERE status = 'pending'
                ORDER BY created_at ASC
            ''')
            
            withdrawals = []
            for row in c.fetchall():
                columns = [desc[0] for desc in c.description]
                withdrawal_data = dict(zip(columns, row))
                withdrawals.append(Withdrawal.from_dict(withdrawal_data))
            
            return withdrawals
    
    def get_pending_manual_withdrawals(self) -> List[Withdrawal]:
        """Get all pending manual withdrawals."""
        
        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            c.execute('''
                SELECT * FROM withdrawals 
                WHERE payment_mode = 'manual' AND admin_approval_state = 'pending'
                ORDER BY created_at ASC
            ''')
            
            withdrawals = []
            columns = [desc[0] for desc in c.description]
            
            for row in c.fetchall():
                withdrawal_data = dict(zip(columns, row))
                withdrawals.append(Withdrawal.from_dict(withdrawal_data))
            
            return withdrawals
    
    def get_user_withdrawals(self, user_id: int, limit: int = 10, offset: int = 0) -> List[Withdrawal]:
        """Get user's withdrawal history."""
        
        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            c.execute('''
                SELECT * FROM withdrawals 
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            ''', (user_id, limit, offset))
            
            withdrawals = []
            columns = [desc[0] for desc in c.description]
            
            for row in c.fetchall():
                withdrawal_data = dict(zip(columns, row))
                withdrawals.append(Withdrawal.from_dict(withdrawal_data))
            
            return withdrawals
    
    def _save_withdrawal(self, withdrawal: Withdrawal) -> int:
        """Save withdrawal to database and return ID."""
        
        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            
            data = withdrawal.to_dict()
            columns = list(data.keys())
            placeholders = ', '.join(['?' for _ in columns])
            values = list(data.values())
            
            c.execute(f'''
                INSERT INTO withdrawals ({', '.join(columns)})
                VALUES ({placeholders})
            ''', values)
            
            conn.commit()
            return c.lastrowid
    
    def _update_withdrawal(self, withdrawal: Withdrawal):
        """Update withdrawal in database."""
        
        with get_connection(DB_FILE) as conn:
            self._update_withdrawal_in_transaction(withdrawal, conn)
            conn.commit()
    
    def _update_withdrawal_in_transaction(self, withdrawal: Withdrawal, conn):
        """Update withdrawal within an existing transaction."""
        
        c = conn.cursor()
        
        data = withdrawal.to_dict()
        set_clause = ', '.join([f'{col} = ?' for col in data.keys()])
        values = list(data.values()) + [withdrawal.id]
        
        c.execute(f'''
            UPDATE withdrawals 
            SET {set_clause}
            WHERE id = ?
        ''', values)
    
    def _log_audit_event(
        self,
        withdrawal_id: int,
        action: str,
        admin_id: int = None,
        old_status: str = None,
        new_status: str = None,
        old_approval_state: str = None,
        new_approval_state: str = None,
        reason: str = None,
        metadata: Dict[str, Any] = None
    ):
        """Log audit event for withdrawal."""
        
        with get_connection(DB_FILE) as conn:
            self._log_audit_event_in_transaction(
                withdrawal_id, action, admin_id, old_status, new_status,
                old_approval_state, new_approval_state, reason, metadata, conn
            )
            conn.commit()
    
    def _log_audit_event_in_transaction(
        self,
        withdrawal_id: int,
        action: str,
        admin_id: int = None,
        old_status: str = None,
        new_status: str = None,
        old_approval_state: str = None,
        new_approval_state: str = None,
        reason: str = None,
        metadata: Dict[str, Any] = None,
        conn = None
    ):
        """Log audit event within an existing transaction."""
        
        c = conn.cursor()
        
        import json
        metadata_json = json.dumps(metadata) if metadata else None
        
        c.execute('''
            INSERT INTO withdrawal_audit_log (
                withdrawal_id, admin_id, action, old_status, new_status,
                old_approval_state, new_approval_state, reason, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            withdrawal_id, admin_id, action, old_status, new_status,
            old_approval_state, new_approval_state, reason, metadata_json
        ))
    
    def _record_withdrawal_error(
        self,
        withdrawal_id: int,
        error_code: str,
        error_message: str,
        error_payload: Dict[str, Any] = None,
        request_id: str = None,
        correlation_id: str = None,
        retry_count: int = 0
    ) -> int:
        """
        Record withdrawal error in database.
        
        Returns:
            Error record ID
        """
        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            
            import json
            error_payload_json = json.dumps(error_payload) if error_payload else None
            
            c.execute('''
                INSERT INTO withdrawal_errors (
                    withdrawal_id, error_code, error_message, error_payload,
                    request_id, correlation_id, retry_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                withdrawal_id, error_code, error_message, error_payload_json,
                request_id, correlation_id, retry_count
            ))
            
            error_id = c.lastrowid
            conn.commit()
            
            logger.info(f"Recorded withdrawal error {error_id} for withdrawal {withdrawal_id}")
            return error_id
    
    async def _notify_admin_of_error(
        self,
        withdrawal: Withdrawal,
        error_code: str,
        error_message: str,
        correlation_id: str,
        error_payload: Dict[str, Any] = None
    ):
        """Send error notification to admin group."""
        try:
            from utils.notification_service import get_notification_service, NotificationMessage
            
            notification = NotificationMessage(
                title=f"❌ Withdrawal {withdrawal.id} Failed",
                body=f"""
Withdrawal request failed with error.

**User ID:** {withdrawal.user_id}
**Amount:** ${withdrawal.amount_usd} USD / ₦{withdrawal.amount_ngn} NGN
**Account:** {withdrawal.account_name} - {withdrawal.account_number}
**Bank:** {withdrawal.bank_name}
**Error Code:** {error_code}
**Error:** {error_message}
**Payment Mode:** {withdrawal.payment_mode.value}
""".strip(),
                correlation_id=correlation_id,
                priority="high",
                metadata={
                    "withdrawal_id": withdrawal.id,
                    "user_id": withdrawal.user_id,
                    "amount_usd": withdrawal.amount_usd,
                    "error_code": error_code,
                    "timestamp": datetime.utcnow().isoformat()
                }
            )
            
            notification_service = get_notification_service()
            await notification_service.send_notification(notification)
            
            logger.info(f"Sent error notification for withdrawal {withdrawal.id}")
            
        except Exception as e:
            logger.error(f"Failed to send error notification for withdrawal {withdrawal.id}: {e}", exc_info=True)
    
    def _get_retry_config(self) -> tuple[int, int]:
        """
        Get retry configuration from environment.
        
        Returns:
            (retry_count, backoff_seconds)
        """
        retry_count = int(os.getenv("WITHDRAWAL_RETRY_COUNT", "3"))
        backoff_sec = int(os.getenv("WITHDRAWAL_RETRY_BACKOFF_SEC", "60"))
        return retry_count, backoff_sec


# Global service instance cache
_withdrawal_service = None

def get_withdrawal_service():
    """Get or create withdrawal service instance."""
    global _withdrawal_service
    if _withdrawal_service is None:
        _withdrawal_service = WithdrawalService()
    return _withdrawal_service