#!/usr/bin/env python3
"""
Tests for scheduled send system and split-send behavior.
"""

import pytest
import sys
import os
import asyncio
from datetime import datetime, timedelta
import sqlite3

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.scheduled_sends import scheduled_send_system, ScheduledSend, SendStatus
from utils.db_utils import get_connection, DB_FILE


class TestScheduledSendSystem:
    """Test scheduled send system."""
    
    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        """Setup and teardown for each test."""
        # Clear scheduled_sends table before each test
        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("DELETE FROM scheduled_sends")
            conn.commit()
        
        yield
        
        # Cleanup after test
        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("DELETE FROM scheduled_sends")
            conn.commit()
    
    def test_split_send_creates_two_halves(self):
        """Test that split send creates first and second half sends."""
        groups = [1, 2, 3, 4, 5, 6]
        submission_id = "test_submission_1"
        
        sends = scheduled_send_system.schedule_split_send(
            submission_id=submission_id,
            groups=groups,
            message_text="Test message",
            parse_mode="MarkdownV2"
        )
        
        # Should split 6 groups into 3 + 3
        assert len(sends) == 6
        
        # Count halves
        first_half = [s for s in sends if s.half_number == 1]
        second_half = [s for s in sends if s.half_number == 2]
        
        assert len(first_half) == 3
        assert len(second_half) == 3
    
    def test_split_send_timing(self):
        """Test that first half is at T+30min and second at T+60min."""
        groups = [1, 2, 3, 4]
        submission_id = "test_submission_2"
        
        now = datetime.utcnow()
        sends = scheduled_send_system.schedule_split_send(
            submission_id=submission_id,
            groups=groups,
            message_text="Test message",
            parse_mode="MarkdownV2"
        )
        
        # Get unique run_at times
        run_times = set(s.run_at for s in sends)
        assert len(run_times) == 2  # Two different times
        
        # Parse times and verify they're ~30 min apart
        times = sorted([datetime.fromisoformat(t) for t in run_times])
        
        # First time should be ~30 min from now
        first_time_diff = (times[0] - now).total_seconds()
        assert 29 * 60 < first_time_diff < 31 * 60  # Allow 1 min tolerance
        
        # Second time should be ~60 min from now
        second_time_diff = (times[1] - now).total_seconds()
        assert 59 * 60 < second_time_diff < 61 * 60  # Allow 1 min tolerance
    
    def test_idempotency_prevents_duplicates(self):
        """Test that idempotency keys prevent duplicate scheduling."""
        groups = [1, 2]
        submission_id = "test_submission_3"
        
        # Schedule first time
        sends1 = scheduled_send_system.schedule_split_send(
            submission_id=submission_id,
            groups=groups,
            message_text="Test message",
            parse_mode="MarkdownV2"
        )
        
        # Schedule again with same submission_id - should return existing
        sends2 = scheduled_send_system.schedule_split_send(
            submission_id=submission_id,
            groups=groups,
            message_text="Test message",
            parse_mode="MarkdownV2"
        )
        
        # Should have same number of sends
        assert len(sends1) == len(sends2)
        
        # Verify no duplicates in database
        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM scheduled_sends WHERE submission_id = ?", (submission_id,))
            count = c.fetchone()[0]
            assert count == len(sends1)
    
    def test_get_due_sends(self):
        """Test retrieving due sends."""
        groups = [1, 2]
        submission_id = "test_submission_4"
        
        # Create a send that's due now (manually insert with past time)
        past_time = datetime.utcnow() - timedelta(minutes=5)
        future_time = datetime.utcnow() + timedelta(minutes=30)
        
        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            
            # Insert one due send
            c.execute('''
                INSERT INTO scheduled_sends (
                    send_id, submission_id, chat_id, message_text, parse_mode,
                    run_at, status, half_number, idempotency_key, correlation_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                'due_send_1', submission_id, 1, 'Test', 'MarkdownV2',
                past_time.isoformat(), 'scheduled', 1, 'due_key_1', 'corr_1', datetime.utcnow().isoformat()
            ))
            
            # Insert one future send
            c.execute('''
                INSERT INTO scheduled_sends (
                    send_id, submission_id, chat_id, message_text, parse_mode,
                    run_at, status, half_number, idempotency_key, correlation_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                'future_send_1', submission_id, 2, 'Test', 'MarkdownV2',
                future_time.isoformat(), 'scheduled', 2, 'future_key_1', 'corr_1', datetime.utcnow().isoformat()
            ))
            
            conn.commit()
        
        # Get due sends
        due = scheduled_send_system.get_due_sends()
        
        # Should only return the due send
        assert len(due) == 1
        assert due[0].send_id == 'due_send_1'
        
        # Status should be updated to in_progress
        assert due[0].status == SendStatus.IN_PROGRESS
    
    def test_mark_send_completed(self):
        """Test marking a send as completed."""
        groups = [1]
        submission_id = "test_submission_5"
        
        sends = scheduled_send_system.schedule_split_send(
            submission_id=submission_id,
            groups=groups,
            message_text="Test message",
            parse_mode="MarkdownV2"
        )
        
        send_id = sends[0].send_id
        
        # Mark as completed
        scheduled_send_system.mark_send_completed(send_id)
        
        # Verify status in database
        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT status, executed_at FROM scheduled_sends WHERE send_id = ?", (send_id,))
            row = c.fetchone()
            
            assert row['status'] == 'completed'
            assert row['executed_at'] is not None
    
    def test_mark_send_failed(self):
        """Test marking a send as failed."""
        groups = [1]
        submission_id = "test_submission_6"
        
        sends = scheduled_send_system.schedule_split_send(
            submission_id=submission_id,
            groups=groups,
            message_text="Test message",
            parse_mode="MarkdownV2"
        )
        
        send_id = sends[0].send_id
        error_msg = "Test error message"
        
        # Mark as failed
        scheduled_send_system.mark_send_failed(send_id, error_msg)
        
        # Verify status and error in database
        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT status, error_message, executed_at FROM scheduled_sends WHERE send_id = ?", (send_id,))
            row = c.fetchone()
            
            assert row['status'] == 'failed'
            assert row['error_message'] == error_msg
            assert row['executed_at'] is not None
    
    def test_odd_number_of_groups(self):
        """Test split with odd number of groups."""
        groups = [1, 2, 3, 4, 5]
        submission_id = "test_submission_7"
        
        sends = scheduled_send_system.schedule_split_send(
            submission_id=submission_id,
            groups=groups,
            message_text="Test message",
            parse_mode="MarkdownV2"
        )
        
        # Should split 5 groups into 2 + 3
        first_half = [s for s in sends if s.half_number == 1]
        second_half = [s for s in sends if s.half_number == 2]
        
        assert len(first_half) == 2
        assert len(second_half) == 3
    
    def test_single_group(self):
        """Test split with single group."""
        groups = [1]
        submission_id = "test_submission_8"
        
        sends = scheduled_send_system.schedule_split_send(
            submission_id=submission_id,
            groups=groups,
            message_text="Test message",
            parse_mode="MarkdownV2"
        )
        
        # Single group should all go to first half
        assert len(sends) == 1
        assert sends[0].half_number == 1
    
    def test_correlation_id_preserved(self):
        """Test that correlation ID is preserved across sends."""
        groups = [1, 2]
        submission_id = "test_submission_9"
        correlation_id = "test_correlation_id"
        
        sends = scheduled_send_system.schedule_split_send(
            submission_id=submission_id,
            groups=groups,
            message_text="Test message",
            parse_mode="MarkdownV2",
            correlation_id=correlation_id
        )
        
        # All sends should have the same correlation ID
        for send in sends:
            assert send.correlation_id == correlation_id


class TestScheduledSendPersistence:
    """Test that scheduled sends survive restarts."""
    
    def test_sends_persist_across_connections(self):
        """Test that scheduled sends are readable after closing connection."""
        groups = [1, 2, 3]
        submission_id = "test_persistence_1"
        
        # Create sends
        sends = scheduled_send_system.schedule_split_send(
            submission_id=submission_id,
            groups=groups,
            message_text="Test message",
            parse_mode="MarkdownV2"
        )
        
        send_ids = [s.send_id for s in sends]
        
        # Simulate restart by creating new connection
        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT send_id FROM scheduled_sends WHERE submission_id = ?", (submission_id,))
            rows = c.fetchall()
            
            persisted_ids = [r['send_id'] for r in rows]
            
            # All sends should be persisted
            assert set(persisted_ids) == set(send_ids)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
