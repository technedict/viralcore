#!/usr/bin/env python3
# utils/graceful_shutdown.py
# Graceful shutdown management for background tasks and services

import signal
import asyncio
import logging
import sqlite3
from typing import Dict, List, Optional, Set, Any
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

        # Event and loop are set when the runtime loop is available.
        # We avoid creating asyncio primitives at import time to prevent
        # binding them to the wrong loop.
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self.shutdown_event: Optional[asyncio.Event] = None

        # Optionally store a reference to the telegram Application so we can
        # stop polling/close httpx client gracefully before cancelling tasks.
        self.app: Optional[Any] = None
        
    def set_app(self, app: Any):
        """
        Attach the telegram.ext.Application instance so graceful shutdown
        can stop polling and close the bot's HTTP client early.
        Call this from your main after building the app:
            shutdown_manager.set_app(app)
        """
        self.app = app
        # If loop is already running, ensure shutdown_event exists and is bound to it
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None:
            self._loop = loop
            if self.shutdown_event is None:
                self.shutdown_event = asyncio.Event()
            logger.debug("GracefulShutdownManager: app attached and shutdown_event bound to running loop")

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
                if await self.retry_job(job_id):
                    recovered_count += 1
                    logger.info(f"Recovered stale job for retry: {job_id}")
            else:
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
        for task in list(self.background_tasks):
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
                logger.error(f"Error in cleanup callback {getattr(callback,'__name__',str(callback))}: {e}")
    
    async def _try_stop_updater_polling_and_close_client(self, wait_timeout: float = 5.0):
        """
        Robustly stop the Updater polling and close the HTTP client.

        Steps:
        - call updater.stop_polling() if available (may be sync or async)
        - if updater.shutdown() exists, await it
        - wait briefly for updater to report not running (polling tasks finished)
        - scan running asyncio tasks for polling_action_cb tasks, cancel & await them
        - finally, close httpx AsyncClient used by telegram Request
        """
        try:
            if self.app is None:
                logger.debug("_try_stop_updater_polling_and_close_client: no app attached")
            else:
                updater = getattr(self.app, "updater", None)

                # 1) Ask updater to stop polling
                if updater is not None:
                    logger.info("GracefulShutdownManager: requesting updater.stop_polling()")
                    try:
                        res = getattr(updater, "stop_polling", None)
                        if res is not None:
                            maybe = res()
                            if asyncio.iscoroutine(maybe):
                                await maybe
                        # Some clients also provide `is_running` or `running` flags
                    except Exception as e:
                        logger.warning(f"Exception while calling updater.stop_polling(): {e}")

                    # 2) If updater.shutdown() exists, await it (clean internal shutdown)
                    shutdown_coro = getattr(updater, "shutdown", None)
                    if shutdown_coro is not None:
                        try:
                            logger.info("GracefulShutdownManager: awaiting updater.shutdown()")
                            await shutdown_coro()
                        except Exception as e:
                            logger.warning(f"updater.shutdown() raised: {e}")

                    # 3) Wait for the updater to finish by checking for a short period.
                    # Some PTB builds set updater.running or updater.is_running; poll for that.
                    waited = 0.0
                    poll_interval = 0.05
                    max_wait = wait_timeout
                    while waited < max_wait:
                        running = False
                        try:
                            running = bool(getattr(updater, "is_running", False) or getattr(updater, "running", False))
                        except Exception:
                            running = False
                        if not running:
                            break
                        await asyncio.sleep(poll_interval)
                        waited += poll_interval

                # 4) If polling tasks still exist (polling_action_cb), cancel them directly.
                # Search all tasks and cancel those that look like the Updater polling coroutine.
                tasks = list(asyncio.all_tasks(loop=self._loop)) if self._loop is not None else list(asyncio.all_tasks())
                polling_tasks = []
                for t in tasks:
                    coro = t.get_coro()
                    # Check repr for the polling callback name used in PTB: 'polling_action_cb' or similar
                    if coro is not None and ("polling_action_cb" in repr(coro) or "polling_action_cb" in str(getattr(coro, "__qualname__", ""))):
                        polling_tasks.append(t)

                if polling_tasks:
                    logger.info(f"Found {len(polling_tasks)} polling task(s). Cancelling and awaiting them.")
                    for t in polling_tasks:
                        if not t.done():
                            t.cancel()
                    try:
                        await asyncio.wait_for(asyncio.gather(*polling_tasks, return_exceptions=True), timeout=wait_timeout)
                    except asyncio.TimeoutError:
                        logger.warning("Timeout while waiting for polling tasks to cancel")
                    except Exception as e:
                        logger.warning(f"Error while awaiting cancelled polling tasks: {e}")

                # 5) Close the HTTP client used by telegram Request
                bot = getattr(self.app, "bot", None)
                if bot is not None:
                    req = getattr(bot, "request", None)
                    client = None
                    if req is not None:
                        client = getattr(req, "_client", None) or getattr(req, "client", None)
                    if client is not None:
                        logger.info("GracefulShutdownManager: closing telegram HTTP client")
                        try:
                            # Prefer async close if available
                            aclose = getattr(client, "aclose", None)
                            if asyncio.iscoroutinefunction(aclose):
                                await aclose()
                            elif asyncio.iscoroutine(aclose):
                                await aclose
                            else:
                                close = getattr(client, "close", None)
                                if callable(close):
                                    close()
                        except Exception as e:
                            logger.warning(f"Error while closing telegram HTTP client: {e}")

        except Exception as e:
            logger.exception(f"Error in _try_stop_updater_polling_and_close_client: {e}")

    
    async def graceful_shutdown(self):
        """Perform complete graceful shutdown sequence."""
        if self.shutdown_requested:
            logger.warning("Shutdown already in progress")
            return
        
        self.shutdown_requested = True
        logger.info("Starting graceful shutdown...")
        
        try:
            # Stop updater polling and close HTTP client as first step to avoid
            # httpx.ReadError spurious exceptions in polling tasks.
            await self._try_stop_updater_polling_and_close_client()

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
        
        finally:
            # Ensure any waiter is unblocked so main can continue/shutdown.
            if self.shutdown_event is not None and isinstance(self.shutdown_event, asyncio.Event):
                try:
                    if self._loop is not None:
                        self._loop.call_soon_threadsafe(self.shutdown_event.set)
                    else:
                        # Attempt to set directly
                        if not self.shutdown_event.is_set():
                            self.shutdown_event.set()
                except Exception:
                    try:
                        self.shutdown_event.set()
                    except Exception:
                        pass
    
    def setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        # Bind to the currently running loop and create an Event bound to it.
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop at the time of setup. We'll capture loop on first signal if needed.
            loop = None

        if loop is not None:
            self._loop = loop
            # Create the event bound to the running loop
            if self.shutdown_event is None:
                self.shutdown_event = asyncio.Event()
            logger.debug("Shutdown event created and bound to running loop")

        def _schedule_shutdown(loop_to_use: asyncio.AbstractEventLoop):
            """Helper to schedule the graceful_shutdown coroutine on the given loop."""
            try:
                loop_to_use.call_soon_threadsafe(lambda: loop_to_use.create_task(self.graceful_shutdown()))
            except Exception as e:
                logger.error(f"Failed to schedule graceful_shutdown on loop: {e}")

        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            # Determine loop to use: prefer captured loop, otherwise try to fetch running loop
            loop_to_use = self._loop
            if loop_to_use is None:
                try:
                    loop_to_use = asyncio.get_running_loop()
                    self._loop = loop_to_use
                    # ensure we have an event bound to this loop
                    if self.shutdown_event is None:
                        self.shutdown_event = asyncio.Event()
                except RuntimeError:
                    loop_to_use = None

            if loop_to_use is not None:
                _schedule_shutdown(loop_to_use)
                # Also set the shutdown_event to unblock waiters
                try:
                    loop_to_use.call_soon_threadsafe(lambda: self.shutdown_event.set())
                except Exception:
                    try:
                        self.shutdown_event.set()
                    except Exception:
                        pass
            else:
                # No loop available; attempt synchronous call as a last resort
                try:
                    asyncio.run(self.graceful_shutdown())
                except Exception as e:
                    logger.error(f"Error running graceful_shutdown synchronously as fallback: {e}")

        # Register signal handlers (POSIX)
        try:
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
            logger.info("Signal handlers registered for graceful shutdown")
        except Exception as e:
            logger.error(f"Failed to register signal handlers: {e}")

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
