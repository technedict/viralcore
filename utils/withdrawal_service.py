#!/usr/bin/env python3
# utils/withdrawal_service.py
# Withdrawal service with automatic vs manual payment modes

import sqlite3
import uuid
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
        
        # Set approval state for manual payments
        if payment_mode == PaymentMode.MANUAL:
            withdrawal.admin_approval_state = AdminApprovalState.PENDING
        
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
        
        Args:
            withdrawal: Withdrawal to process
            
        Returns:
            True if successful, False otherwise
        """
        
        if withdrawal.payment_mode != PaymentMode.AUTOMATIC:
            raise ValueError("Cannot process manual withdrawal as automatic")
        
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
                    ORDER BY id FOR UPDATE
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
                
                # Deduct balance atomically
                balance_type = "affiliate" if withdrawal.is_affiliate_withdrawal else "reply"
                success = atomic_withdraw_operation(
                    user_id=withdrawal.user_id,
                    balance_type=balance_type,
                    amount=withdrawal.amount_usd,
                    reason=f"Manual withdrawal approved by admin {admin_id}",
                    operation_id=withdrawal.operation_id
                )
                
                if not success:
                    logger.error(f"Balance deduction failed for manual withdrawal {withdrawal_id}")
                    return False
                
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
                    ORDER BY id FOR UPDATE
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


# Global service instance cache
_withdrawal_service = None

def get_withdrawal_service():
    """Get or create withdrawal service instance."""
    global _withdrawal_service
    if _withdrawal_service is None:
        _withdrawal_service = WithdrawalService()
    return _withdrawal_service