#!/usr/bin/env python3
"""
Job system with immutable provider snapshots to prevent service_id leaks.
Implements the canonical source of truth for provider configurations at job creation time.
"""

import json
import sqlite3
import uuid
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

from utils.db_utils import get_connection, DB_FILE
from utils.logging import get_logger, correlation_context, generate_correlation_id
from utils.boost_provider_utils import get_active_provider, ProviderConfig, PROVIDERS

logger = get_logger(__name__)


class JobStatus(Enum):
    """Job status enumeration."""
    QUEUED = "queued"
    IN_PROGRESS = "in_progress" 
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


class JobType(Enum):
    """Job type enumeration."""
    BOOST = "boost"
    BALANCE_CHECK = "balance_check"
    PROVIDER_SWITCH = "provider_switch"


@dataclass
class ProviderSnapshot:
    """Immutable snapshot of provider configuration at job creation time."""
    provider_id: str
    provider_name: str
    api_url: str
    api_key_hash: str  # Hashed for security, not the actual key
    view_service_id: int
    like_service_id: int
    snapshot_timestamp: str
    
    @classmethod
    def from_provider_config(cls, provider: ProviderConfig) -> 'ProviderSnapshot':
        """Create snapshot from active provider config."""
        import hashlib
        
        # Hash the API key for security (we'll store actual key separately)
        api_key_hash = hashlib.sha256(provider.api_key.encode()).hexdigest()[:16]
        
        return cls(
            provider_id=provider.name,
            provider_name=provider.name,
            api_url=provider.api_url,
            api_key_hash=api_key_hash,
            view_service_id=provider.view_service_id,
            like_service_id=provider.like_service_id,
            snapshot_timestamp=datetime.utcnow().isoformat()
        )


@dataclass 
class BoostJobPayload:
    """Payload for boost jobs."""
    link: str
    likes: int
    views: int
    comments: int
    user_id: Optional[int] = None
    correlation_id: Optional[str] = None


@dataclass
class Job:
    """Job with immutable provider snapshot."""
    job_id: str
    job_type: JobType
    status: JobStatus
    provider_snapshot: ProviderSnapshot
    payload: Dict[str, Any]
    idempotency_key: str
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    error_message: Optional[str] = None
    correlation_id: Optional[str] = None


class JobSystemError(Exception):
    """Base exception for job system errors."""
    pass


class ServiceProviderMismatchError(JobSystemError):
    """Raised when provider_id and service_id don't match."""
    pass


class JobSystem:
    """Job system with provider snapshot and concurrency control."""
    
    def __init__(self):
        self._init_database()
    
    def _init_database(self):
        """Initialize job system database tables."""
        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            
            # Jobs table with provider snapshots
            c.execute('''
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    job_type TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    provider_snapshot TEXT NOT NULL,  -- JSON snapshot
                    payload TEXT NOT NULL,           -- JSON payload  
                    idempotency_key TEXT UNIQUE NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    error_message TEXT,
                    correlation_id TEXT,
                    UNIQUE(idempotency_key)
                )
            ''')
            
            # Indices for performance
            c.execute('CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_jobs_type ON jobs(job_type)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_jobs_idempotency ON jobs(idempotency_key)')
            
            conn.commit()
        
        logger.info("Job system database initialized")
    
    def validate_provider_service_id(self, provider_id: str, service_id: int, service_type: str) -> bool:
        """
        Validate that service_id belongs to provider_id.
        
        Args:
            provider_id: Provider identifier
            service_id: Service ID to validate
            service_type: Type of service ('view' or 'like')
            
        Returns:
            True if valid, False otherwise
            
        Raises:
            ServiceProviderMismatchError: If validation fails
        """
        if provider_id not in PROVIDERS:
            raise ServiceProviderMismatchError(f"Unknown provider: {provider_id}")
        
        provider = PROVIDERS[provider_id]
        expected_service_id = None
        
        if service_type == 'view':
            expected_service_id = provider.view_service_id
        elif service_type == 'like':
            expected_service_id = provider.like_service_id
        else:
            raise ServiceProviderMismatchError(f"Unknown service type: {service_type}")
        
        if service_id != expected_service_id:
            raise ServiceProviderMismatchError(
                f"Service ID mismatch for provider {provider_id}: "
                f"expected {expected_service_id} for {service_type}, got {service_id}"
            )
        
        return True
    
    async def create_boost_job(
        self,
        link: str,
        likes: int = 100,
        views: int = 500,
        comments: int = 0,
        user_id: Optional[int] = None,
        idempotency_key: Optional[str] = None,
        correlation_id: Optional[str] = None
    ) -> Job:
        """
        Create a boost job with immutable provider snapshot.
        
        Args:
            link: URL to boost
            likes: Number of likes
            views: Number of views  
            comments: Number of comments
            user_id: User ID creating the job
            idempotency_key: Optional idempotency key
            correlation_id: Optional correlation ID
            
        Returns:
            Created job with provider snapshot
        """
        
        if not correlation_id:
            correlation_id = generate_correlation_id()
            
        if not idempotency_key:
            idempotency_key = f"boost_{link}_{likes}_{views}_{correlation_id}"
        
        with correlation_context(correlation_id):
            # Get current provider and create immutable snapshot
            provider = get_active_provider()
            provider_snapshot = ProviderSnapshot.from_provider_config(provider)
            
            # Create job payload
            payload = BoostJobPayload(
                link=link,
                likes=likes, 
                views=views,
                comments=comments,
                user_id=user_id,
                correlation_id=correlation_id
            )
            
            job = Job(
                job_id=str(uuid.uuid4()),
                job_type=JobType.BOOST,
                status=JobStatus.QUEUED,
                provider_snapshot=provider_snapshot,
                payload=asdict(payload),
                idempotency_key=idempotency_key,
                created_at=datetime.utcnow().isoformat(),
                correlation_id=correlation_id
            )
            
            # Store job with SELECT FOR UPDATE locking to handle concurrency
            await self._store_job_with_locking(job)
            
            logger.info(
                f"Created boost job {job.job_id} for provider {provider.name}",
                extra={
                    'job_id': job.job_id,
                    'provider_name': provider.name,
                    'user_id': user_id,
                    'correlation_id': correlation_id
                }
            )
            
            return job
    
    async def _store_job_with_locking(self, job: Job):
        """Store job with database locking for concurrency control."""
        
        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            
            try:
                # Use exclusive transaction for concurrency control
                c.execute("BEGIN EXCLUSIVE")
                
                # Check for existing job with same idempotency key
                c.execute(
                    "SELECT job_id, status FROM jobs WHERE idempotency_key = ?",
                    (job.idempotency_key,)
                )
                existing = c.fetchone()
                
                if existing:
                    logger.info(f"Job with idempotency key {job.idempotency_key} already exists: {existing['job_id']}")
                    # Return existing job rather than creating duplicate
                    return
                
                # Insert new job
                c.execute('''
                    INSERT INTO jobs (
                        job_id, job_type, status, provider_snapshot, payload,
                        idempotency_key, created_at, correlation_id, max_retries
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    job.job_id,
                    job.job_type.value,
                    job.status.value,
                    json.dumps(asdict(job.provider_snapshot)),
                    json.dumps(job.payload),
                    job.idempotency_key,
                    job.created_at,
                    job.correlation_id,
                    job.max_retries
                ))
                
                conn.commit()
                
            except sqlite3.IntegrityError as e:
                conn.rollback()
                if "idempotency_key" in str(e):
                    logger.info(f"Idempotent job creation - key already exists: {job.idempotency_key}")
                else:
                    raise JobSystemError(f"Failed to store job: {e}")
            except Exception as e:
                conn.rollback()
                raise JobSystemError(f"Failed to store job: {e}")
    
    def get_job(self, job_id: str) -> Optional[Job]:
        """Retrieve job by ID."""
        
        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
            row = c.fetchone()
            
            if not row:
                return None
            
            return self._row_to_job(row)
    
    def get_job_by_idempotency_key(self, idempotency_key: str) -> Optional[Job]:
        """Retrieve job by idempotency key."""
        
        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM jobs WHERE idempotency_key = ?", (idempotency_key,))
            row = c.fetchone()
            
            if not row:
                return None
            
            return self._row_to_job(row)
    
    def get_pending_jobs(self, job_type: Optional[JobType] = None, limit: int = 100) -> List[Job]:
        """Get pending jobs for processing."""
        
        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            
            query = "SELECT * FROM jobs WHERE status = ? ORDER BY created_at ASC LIMIT ?"
            params = [JobStatus.QUEUED.value, limit]
            
            if job_type:
                query = "SELECT * FROM jobs WHERE status = ? AND job_type = ? ORDER BY created_at ASC LIMIT ?"
                params = [JobStatus.QUEUED.value, job_type.value, limit]
            
            c.execute(query, params)
            rows = c.fetchall()
            
            return [self._row_to_job(row) for row in rows]
    
    def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        error_message: Optional[str] = None,
        increment_retry: bool = False
    ) -> bool:
        """Update job status."""
        
        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            
            now = datetime.utcnow().isoformat()
            
            if status == JobStatus.IN_PROGRESS:
                c.execute('''
                    UPDATE jobs 
                    SET status = ?, started_at = ?
                    WHERE job_id = ?
                ''', (status.value, now, job_id))
                
            elif status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
                retry_clause = ""
                params = [status.value, now, error_message, job_id]
                
                if increment_retry:
                    retry_clause = ", retry_count = retry_count + 1"
                
                c.execute(f'''
                    UPDATE jobs 
                    SET status = ?, completed_at = ?, error_message = ? {retry_clause}
                    WHERE job_id = ?
                ''', params)
            else:
                c.execute('''
                    UPDATE jobs 
                    SET status = ?, error_message = ?
                    WHERE job_id = ?
                ''', (status.value, error_message, job_id))
            
            return c.rowcount > 0
    
    def _row_to_job(self, row) -> Job:
        """Convert database row to Job object."""
        
        provider_snapshot = ProviderSnapshot(**json.loads(row['provider_snapshot'])) 
        
        return Job(
            job_id=row['job_id'],
            job_type=JobType(row['job_type']),
            status=JobStatus(row['status']),
            provider_snapshot=provider_snapshot,
            payload=json.loads(row['payload']),
            idempotency_key=row['idempotency_key'],
            created_at=row['created_at'],
            started_at=row['started_at'],
            completed_at=row['completed_at'],
            retry_count=row['retry_count'],
            max_retries=row['max_retries'],
            error_message=row['error_message'],
            correlation_id=row['correlation_id']
        )
    
    def get_provider_from_job(self, job: Job) -> ProviderConfig:
        """
        Get actual provider config from job snapshot.
        Always use the API key from current config, but service IDs from snapshot.
        """
        snapshot = job.provider_snapshot
        
        # Get current provider config for API key (in case it changed)
        if snapshot.provider_id in PROVIDERS:
            current_provider = PROVIDERS[snapshot.provider_id]
            
            # Create a provider config using snapshot service IDs but current API key
            return ProviderConfig(
                name=snapshot.provider_name,
                api_url=snapshot.api_url,
                api_key=current_provider.api_key,  # Use current API key
                view_service_id=snapshot.view_service_id,  # Use snapshot service IDs
                like_service_id=snapshot.like_service_id
            )
        else:
            raise JobSystemError(f"Provider {snapshot.provider_id} no longer exists in config")


# Global job system instance
job_system = JobSystem()