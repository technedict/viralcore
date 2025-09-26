#!/usr/bin/env python3
# utils/graceful_shutdown.py
# Graceful shutdown management for background tasks and services

import signal
import asyncio
import logging
import sqlite3
from typing import Dict, List, Optional, Set
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from utils.db_utils import get_connection, DB_FILE
from utils.boost_utils import boost_manager

logger = logging.getLogger(__name__)

class JobStatus:
    """Job status constants."""
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class GracefulShutdownManager:
    """Manages graceful shutdown of background tasks and services."""
    
    def __init__(self):
        self.shutdown_requested = False
        self.background_tasks: Set[asyncio.Task] = set()
        self.cleanup_callbacks: List[callable] = []
        self.job_queue_initialized = False
        
    def init_job_queue(self):
        """Initialize the job queue database table."""
        if self.job_queue_initialized:
            return
            
        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            c.execute('''
                CREATE TABLE IF NOT EXISTS job_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT UNIQUE NOT NULL,
                    job_type TEXT NOT NULL,
                    status TEXT DEFAULT 'queued',
                    payload TEXT,
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    error_message TEXT,
                    worker_id TEXT
                );
            ''')
            
            # Create indices for performance
            c.execute('CREATE INDEX IF NOT EXISTS idx_job_queue_status ON job_queue(status)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_job_queue_created ON job_queue(created_at)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_job_queue_type ON job_queue(job_type)')
            
            conn.commit()
        
        self.job_queue_initialized = True
        logger.info("Job queue database initialized")
    
    def register_cleanup_callback(self, callback: callable):
        """Register a cleanup callback to be called during shutdown."""
        self.cleanup_callbacks.append(callback)
    
    def add_background_task(self, task: asyncio.Task):
        """Register a background task for tracking."""
        self.background_tasks.add(task)
        task.add_done_callback(self.background_tasks.discard)
    
    async def enqueue_job(self, job_id: str, job_type: str, payload: str = None, max_retries: int = 3) -> bool:
        """
        Enqueue a job with persistent storage.
        
        Args:
            job_id: Unique job identifier
            job_type: Type of job (e.g., 'boost', 'withdrawal')
            payload: JSON payload for the job
            max_retries: Maximum retry attempts
        
        Returns:
            True if job was enqueued successfully
        """
        self.init_job_queue()
        
        try:
            with get_connection(DB_FILE) as conn:
                c = conn.cursor()
                c.execute("""
                    INSERT OR REPLACE INTO job_queue 
                    (job_id, job_type, status, payload, max_retries, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (job_id, job_type, JobStatus.QUEUED, payload, max_retries, datetime.utcnow().isoformat()))
                conn.commit()
            
            logger.info(f"Job enqueued: {job_id} ({job_type})")
            return True
            
        except sqlite3.Error as e:
            logger.error(f"Failed to enqueue job {job_id}: {e}")
            return False
    
    async def start_job(self, job_id: str, worker_id: str = "default") -> bool:
        """Mark a job as started."""
        self.init_job_queue()
        
        try:
            with get_connection(DB_FILE) as conn:
                c = conn.cursor()
                c.execute("""
                    UPDATE job_queue 
                    SET status = ?, started_at = ?, worker_id = ?
                    WHERE job_id = ? AND status = ?
                """, (JobStatus.IN_PROGRESS, datetime.utcnow().isoformat(), worker_id, job_id, JobStatus.QUEUED))
                
                if c.rowcount == 0:
                    logger.warning(f"Could not start job {job_id} - not found or not queued")
                    return False
                
                conn.commit()
            
            logger.info(f"Job started: {job_id}")
            return True
            
        except sqlite3.Error as e:
            logger.error(f"Failed to start job {job_id}: {e}")
            return False
    
    async def complete_job(self, job_id: str, error_message: str = None) -> bool:
        """Mark a job as completed or failed."""
        self.init_job_queue()
        
        status = JobStatus.FAILED if error_message else JobStatus.COMPLETED
        
        try:
            with get_connection(DB_FILE) as conn:
                c = conn.cursor()
                c.execute("""
                    UPDATE job_queue 
                    SET status = ?, completed_at = ?, error_message = ?
                    WHERE job_id = ?
                """, (status, datetime.utcnow().isoformat(), error_message, job_id))
                conn.commit()
            
            logger.info(f"Job {'completed' if not error_message else 'failed'}: {job_id}")
            return True
            
        except sqlite3.Error as e:
            logger.error(f"Failed to complete job {job_id}: {e}")
            return False
    
    async def retry_job(self, job_id: str) -> bool:
        """Retry a failed job if it hasn't exceeded max retries."""
        self.init_job_queue()
        
        try:
            with get_connection(DB_FILE) as conn:
                c = conn.cursor()
                
                # Get current retry count and max retries
                c.execute("SELECT retry_count, max_retries FROM job_queue WHERE job_id = ?", (job_id,))
                row = c.fetchone()
                
                if not row:
                    logger.warning(f"Job {job_id} not found for retry")
                    return False
                
                retry_count, max_retries = row['retry_count'], row['max_retries']
                
                if retry_count >= max_retries:
                    logger.warning(f"Job {job_id} has exceeded max retries ({max_retries})")
                    return False
                
                # Increment retry count and reset to queued
                c.execute("""
                    UPDATE job_queue 
                    SET status = ?, retry_count = retry_count + 1, started_at = NULL, 
                        completed_at = NULL, error_message = NULL, worker_id = NULL
                    WHERE job_id = ?
                """, (JobStatus.QUEUED, job_id))
                conn.commit()
            
            logger.info(f"Job {job_id} queued for retry (attempt {retry_count + 2})")
            return True
            
        except sqlite3.Error as e:
            logger.error(f"Failed to retry job {job_id}: {e}")
            return False
    
    async def get_stale_jobs(self, threshold_minutes: int = 30) -> List[Dict]:
        """Get jobs that have been in progress for too long."""
        self.init_job_queue()
        
        threshold_time = (datetime.utcnow() - timedelta(minutes=threshold_minutes)).isoformat()
        
        try:
            with get_connection(DB_FILE) as conn:
                c = conn.cursor()
                c.execute("""
                    SELECT job_id, job_type, payload, retry_count, max_retries, started_at
                    FROM job_queue
                    WHERE status = ? AND started_at < ?
                """, (JobStatus.IN_PROGRESS, threshold_time))
                
                return [dict(row) for row in c.fetchall()]
                
        except sqlite3.Error as e:
            logger.error(f"Failed to get stale jobs: {e}")
            return []
    
    async def recover_stale_jobs(self, threshold_minutes: int = 30) -> int:
        """Recover stale jobs by marking them as failed or queuing for retry."""
        stale_jobs = await self.get_stale_jobs(threshold_minutes)
        recovered_count = 0
        
        for job in stale_jobs:
            job_id = job['job_id']
            retry_count = job['retry_count']
            max_retries = job['max_retries']
            
            if retry_count < max_retries:
                # Retry the job
                if await self.retry_job(job_id):
                    recovered_count += 1
                    logger.info(f"Recovered stale job for retry: {job_id}")
            else:
                # Mark as failed
                if await self.complete_job(job_id, "Job timeout - exceeded maximum duration"):
                    recovered_count += 1
                    logger.info(f"Marked stale job as failed: {job_id}")
        
        if recovered_count > 0:
            logger.info(f"Recovered {recovered_count} stale jobs")
        
        return recovered_count
    
    async def shutdown_background_tasks(self, timeout: float = 30.0):
        """Gracefully shutdown all background tasks."""
        if not self.background_tasks:
            logger.info("No background tasks to shutdown")
            return
        
        logger.info(f"Shutting down {len(self.background_tasks)} background tasks...")
        
        # Cancel all tasks
        for task in self.background_tasks:
            if not task.done():
                task.cancel()
        
        # Wait for tasks to complete or timeout
        try:
            await asyncio.wait_for(
                asyncio.gather(*self.background_tasks, return_exceptions=True),
                timeout=timeout
            )
            logger.info("All background tasks completed gracefully")
        except asyncio.TimeoutError:
            logger.warning(f"Some background tasks did not complete within {timeout}s timeout")
        except Exception as e:
            logger.error(f"Error during background task shutdown: {e}")
    
    async def shutdown_boost_manager(self):
        """Shutdown the boost manager gracefully."""
        try:
            logger.info("Shutting down boost manager...")
            await boost_manager.cancel_all()
            logger.info("Boost manager shutdown complete")
        except Exception as e:
            logger.error(f"Error shutting down boost manager: {e}")
    
    async def run_cleanup_callbacks(self):
        """Run all registered cleanup callbacks."""
        logger.info(f"Running {len(self.cleanup_callbacks)} cleanup callbacks...")
        
        for callback in self.cleanup_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback()
                else:
                    callback()
            except Exception as e:
                logger.error(f"Error in cleanup callback {callback.__name__}: {e}")
    
    async def graceful_shutdown(self):
        """Perform complete graceful shutdown sequence."""
        if self.shutdown_requested:
            logger.warning("Shutdown already in progress")
            return
        
        self.shutdown_requested = True
        logger.info("Starting graceful shutdown...")
        
        try:
            # 1. Stop accepting new work
            logger.info("Phase 1: Stopping new work acceptance")
            
            # 2. Shutdown boost manager
            await self.shutdown_boost_manager()
            
            # 3. Shutdown background tasks
            await self.shutdown_background_tasks()
            
            # 4. Run cleanup callbacks
            await self.run_cleanup_callbacks()
            
            # 5. Mark any remaining in-progress jobs as failed
            logger.info("Phase 5: Cleaning up remaining jobs")
            stale_jobs = await self.get_stale_jobs(threshold_minutes=0)  # Get all in-progress jobs
            for job in stale_jobs:
                await self.complete_job(job['job_id'], "Shutdown requested")
            
            logger.info("Graceful shutdown completed successfully")
            
        except Exception as e:
            logger.error(f"Error during graceful shutdown: {e}")
    
    def setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            asyncio.create_task(self.graceful_shutdown())
        
        # Register signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        logger.info("Signal handlers registered for graceful shutdown")

# Global shutdown manager instance
shutdown_manager = GracefulShutdownManager()

@asynccontextmanager
async def job_context(job_id: str, job_type: str, payload: str = None):
    """Context manager for job execution with automatic status tracking."""
    shutdown_manager.init_job_queue()
    
    # Enqueue the job
    await shutdown_manager.enqueue_job(job_id, job_type, payload)
    
    # Start the job
    started = await shutdown_manager.start_job(job_id)
    if not started:
        raise RuntimeError(f"Could not start job {job_id}")
    
    try:
        yield job_id
        # Job completed successfully
        await shutdown_manager.complete_job(job_id)
    except Exception as e:
        # Job failed
        error_msg = str(e)
        await shutdown_manager.complete_job(job_id, error_msg)
        raise