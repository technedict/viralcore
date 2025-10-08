#!/usr/bin/env python3
"""
Worker for processing scheduled sends.
Runs in background and executes sends at their scheduled time.
"""

import asyncio
from datetime import datetime
import logging
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from telegram.ext import Application

from utils.scheduled_sends import scheduled_send_system, ScheduledSend
from utils.logging import get_logger

logger = get_logger(__name__)


class ScheduledSendWorker:
    """Background worker for executing scheduled sends."""
    
    def __init__(self, app: 'Application', check_interval: int = 60):
        """
        Initialize worker.
        
        Args:
            app: Telegram Application for sending messages
            check_interval: How often to check for due sends (seconds)
        """
        self.app = app
        self.check_interval = check_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    async def start(self):
        """Start the worker."""
        if self._running:
            logger.warning("Scheduled send worker already running")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info(f"Scheduled send worker started (check interval: {self.check_interval}s)")
    
    async def stop(self):
        """Stop the worker."""
        if not self._running:
            return
        
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("Scheduled send worker stopped")
    
    async def _run(self):
        """Main worker loop."""
        while self._running:
            try:
                await self._process_due_sends()
            except Exception as e:
                logger.error(f"Error in scheduled send worker: {e}", exc_info=True)
            
            # Wait before next check
            await asyncio.sleep(self.check_interval)
    
    async def _process_due_sends(self):
        """Process all sends that are due."""
        due_sends = scheduled_send_system.get_due_sends()
        
        if not due_sends:
            return
        
        logger.info(f"Processing {len(due_sends)} due scheduled sends")
        
        for send in due_sends:
            await self._execute_send(send)
    
    async def _execute_send(self, send: ScheduledSend):
        """Execute a single scheduled send."""
        try:
            logger.info(
                f"Executing scheduled send: send_id={send.send_id}, "
                f"submission={send.submission_id}, chat_id={send.chat_id}, "
                f"half={send.half_number}, correlation_id={send.correlation_id}"
            )
            
            await self.app.bot.send_message(
                chat_id=send.chat_id,
                text=send.message_text,
                parse_mode=send.parse_mode
            )
            
            scheduled_send_system.mark_send_completed(send.send_id)
            
            logger.info(
                f"scheduled_send_executed: send_id={send.send_id}, "
                f"submission_id={send.submission_id}, "
                f"correlation_id={send.correlation_id}"
            )
            
        except Exception as e:
            error_msg = f"Failed to send to {send.chat_id}: {str(e)}"
            scheduled_send_system.mark_send_failed(send.send_id, error_msg)
            
            logger.error(
                f"scheduled_send_failed: send_id={send.send_id}, "
                f"submission_id={send.submission_id}, "
                f"correlation_id={send.correlation_id}, "
                f"error={error_msg}",
                exc_info=True
            )


# Global worker instance (will be initialized in main bot)
_worker: Optional[ScheduledSendWorker] = None


def init_worker(app: 'Application'):
    """Initialize the global worker."""
    global _worker
    _worker = ScheduledSendWorker(app)
    return _worker


def get_worker() -> Optional[ScheduledSendWorker]:
    """Get the global worker instance."""
    return _worker
