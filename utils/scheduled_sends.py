#!/usr/bin/env python3
"""
Scheduled send system with persistent storage for restart resilience.
Implements split-send behavior: first half at T+30min, second half at T+60min.
"""

import json
import sqlite3
import uuid
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from enum import Enum
import logging

from utils.db_utils import get_connection, DB_FILE
from utils.logging import get_logger, generate_correlation_id

logger = get_logger(__name__)


class SendStatus(Enum):
    """Send status enumeration."""
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ScheduledSend:
    """Represents a scheduled send job."""
    send_id: str
    submission_id: str  # Links to original submission
    chat_id: int
    message_text: str
    parse_mode: str
    run_at: str  # ISO format timestamp
    status: SendStatus
    half_number: int  # 1 for first half, 2 for second half
    idempotency_key: str
    correlation_id: str
    created_at: str
    executed_at: Optional[str] = None
    error_message: Optional[str] = None


class ScheduledSendSystem:
    """System for managing persistent scheduled sends."""
    
    def __init__(self):
        self._init_database()
    
    def _init_database(self):
        """Initialize scheduled_sends table."""
        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            
            c.execute('''
                CREATE TABLE IF NOT EXISTS scheduled_sends (
                    send_id TEXT PRIMARY KEY,
                    submission_id TEXT NOT NULL,
                    chat_id INTEGER NOT NULL,
                    message_text TEXT NOT NULL,
                    parse_mode TEXT NOT NULL,
                    run_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'scheduled',
                    half_number INTEGER NOT NULL,
                    idempotency_key TEXT UNIQUE NOT NULL,
                    correlation_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    executed_at TEXT,
                    error_message TEXT,
                    UNIQUE(idempotency_key)
                )
            ''')
            
            # Indices for performance
            c.execute('CREATE INDEX IF NOT EXISTS idx_scheduled_sends_status ON scheduled_sends(status)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_scheduled_sends_run_at ON scheduled_sends(run_at)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_scheduled_sends_submission ON scheduled_sends(submission_id)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_scheduled_sends_correlation ON scheduled_sends(correlation_id)')
            
            conn.commit()
        
        logger.info("Scheduled send system database initialized")
    
    def schedule_split_send(
        self,
        submission_id: str,
        groups: List[int],
        message_text: str,
        parse_mode: str = 'MarkdownV2',
        correlation_id: Optional[str] = None
    ) -> List[ScheduledSend]:
        """
        Schedule a split send: first half at T+30min, second half at T+60min.
        
        Args:
            submission_id: Unique ID for this submission
            groups: List of group chat IDs to send to
            message_text: Message text to send
            parse_mode: Parse mode for the message
            correlation_id: Optional correlation ID for tracking
        
        Returns:
            List of ScheduledSend objects created
        """
        if not correlation_id:
            correlation_id = generate_correlation_id()
        
        now = datetime.utcnow()
        first_half_time = now + timedelta(minutes=30)
        second_half_time = now + timedelta(minutes=60)
        
        # Split groups into two halves
        mid_point = len(groups) // 2
        first_half_groups = groups[:mid_point] if mid_point > 0 else groups[:1]
        second_half_groups = groups[mid_point:] if mid_point > 0 else []
        
        scheduled_sends = []
        
        # Schedule first half
        for chat_id in first_half_groups:
            send = self._create_scheduled_send(
                submission_id=submission_id,
                chat_id=chat_id,
                message_text=message_text,
                parse_mode=parse_mode,
                run_at=first_half_time,
                half_number=1,
                correlation_id=correlation_id
            )
            scheduled_sends.append(send)
        
        # Schedule second half (only if there are groups)
        if second_half_groups:
            for chat_id in second_half_groups:
                send = self._create_scheduled_send(
                    submission_id=submission_id,
                    chat_id=chat_id,
                    message_text=message_text,
                    parse_mode=parse_mode,
                    run_at=second_half_time,
                    half_number=2,
                    correlation_id=correlation_id
                )
                scheduled_sends.append(send)
        
        logger.info(
            f"scheduled_send_created: submission={submission_id}, "
            f"correlation_id={correlation_id}, "
            f"first_half={len(first_half_groups)} groups at {first_half_time.isoformat()}, "
            f"second_half={len(second_half_groups)} groups at {second_half_time.isoformat()}"
        )
        
        return scheduled_sends
    
    def _create_scheduled_send(
        self,
        submission_id: str,
        chat_id: int,
        message_text: str,
        parse_mode: str,
        run_at: datetime,
        half_number: int,
        correlation_id: str
    ) -> ScheduledSend:
        """Create and store a scheduled send."""
        send_id = str(uuid.uuid4())
        idempotency_key = f"{submission_id}_{chat_id}_{half_number}"
        
        send = ScheduledSend(
            send_id=send_id,
            submission_id=submission_id,
            chat_id=chat_id,
            message_text=message_text,
            parse_mode=parse_mode,
            run_at=run_at.isoformat(),
            status=SendStatus.SCHEDULED,
            half_number=half_number,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            created_at=datetime.utcnow().isoformat()
        )
        
        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            
            # Check for existing send with same idempotency key
            c.execute(
                "SELECT send_id FROM scheduled_sends WHERE idempotency_key = ?",
                (idempotency_key,)
            )
            existing = c.fetchone()
            
            if existing:
                logger.info(f"Scheduled send with idempotency key {idempotency_key} already exists")
                c.execute(
                    "SELECT * FROM scheduled_sends WHERE send_id = ?",
                    (existing['send_id'],)
                )
                row = c.fetchone()
                return self._row_to_send(row)
            
            # Insert new scheduled send
            c.execute('''
                INSERT INTO scheduled_sends (
                    send_id, submission_id, chat_id, message_text, parse_mode,
                    run_at, status, half_number, idempotency_key, correlation_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                send.send_id, send.submission_id, send.chat_id, send.message_text,
                send.parse_mode, send.run_at, send.status.value, send.half_number,
                send.idempotency_key, send.correlation_id, send.created_at
            ))
            
            conn.commit()
        
        return send
    
    def get_due_sends(self) -> List[ScheduledSend]:
        """Get all scheduled sends that are due to execute."""
        now = datetime.utcnow().isoformat()
        
        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            
            # Use SELECT FOR UPDATE for concurrency safety (if supported)
            # SQLite's BEGIN EXCLUSIVE provides similar semantics
            c.execute("BEGIN EXCLUSIVE")
            
            c.execute('''
                SELECT * FROM scheduled_sends
                WHERE status = 'scheduled' AND run_at <= ?
                ORDER BY run_at ASC
            ''', (now,))
            
            rows = c.fetchall()
            
            # Mark as in_progress to prevent duplicate execution
            if rows:
                send_ids = [row['send_id'] for row in rows]
                placeholders = ','.join(['?'] * len(send_ids))
                c.execute(f'''
                    UPDATE scheduled_sends
                    SET status = 'in_progress'
                    WHERE send_id IN ({placeholders})
                ''', send_ids)
            
            conn.commit()
            
            # Convert rows to ScheduledSend objects after update
            # Re-fetch to get updated status
            if rows:
                send_ids = [row['send_id'] for row in rows]
                placeholders = ','.join(['?'] * len(send_ids))
                c.execute(f'''
                    SELECT * FROM scheduled_sends
                    WHERE send_id IN ({placeholders})
                ''', send_ids)
                updated_rows = c.fetchall()
                sends = [self._row_to_send(row) for row in updated_rows]
            else:
                sends = []
        
        return sends
    
    def mark_send_completed(self, send_id: str):
        """Mark a send as completed."""
        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            c.execute('''
                UPDATE scheduled_sends
                SET status = ?, executed_at = ?
                WHERE send_id = ?
            ''', (SendStatus.COMPLETED.value, datetime.utcnow().isoformat(), send_id))
            conn.commit()
        
        logger.info(f"scheduled_send_executed: send_id={send_id}")
    
    def mark_send_failed(self, send_id: str, error_message: str):
        """Mark a send as failed."""
        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            c.execute('''
                UPDATE scheduled_sends
                SET status = ?, error_message = ?, executed_at = ?
                WHERE send_id = ?
            ''', (SendStatus.FAILED.value, error_message, datetime.utcnow().isoformat(), send_id))
            conn.commit()
        
        logger.error(f"scheduled_send_failed: send_id={send_id}, error={error_message}")
    
    def _row_to_send(self, row) -> ScheduledSend:
        """Convert database row to ScheduledSend object."""
        return ScheduledSend(
            send_id=row['send_id'],
            submission_id=row['submission_id'],
            chat_id=row['chat_id'],
            message_text=row['message_text'],
            parse_mode=row['parse_mode'],
            run_at=row['run_at'],
            status=SendStatus(row['status']),
            half_number=row['half_number'],
            idempotency_key=row['idempotency_key'],
            correlation_id=row['correlation_id'],
            created_at=row['created_at'],
            executed_at=row['executed_at'],
            error_message=row['error_message']
        )


# Global instance
scheduled_send_system = ScheduledSendSystem()
