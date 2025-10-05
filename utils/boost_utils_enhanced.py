#!/usr/bin/env python3
"""
Enhanced boost utilities with safe provider error handling and job system integration.
Ensures external provider errors are never leaked to clients.
"""

import asyncio
import aiohttp
import json
import time
import os
from typing import Dict, Optional, Any, Tuple
from enum import Enum
from dataclasses import dataclass

from telegram import Bot
from utils.config import APIConfig
from utils.db_utils import GROUPS_TWEETS_DB_FILE
from utils.notification import get_group_id_from_db, TARGET_NOTIFICATION_GROUP_ID_FROM_DB
from utils.logging import get_logger, correlation_context, log_provider_error, generate_correlation_id
from utils.messaging import render_markdown_v2, safe_send, TEMPLATES
from utils.job_system import job_system, Job, JobStatus, JobType, BoostJobPayload

logger = get_logger(__name__)


class ProviderErrorType(Enum):
    """Classification of provider errors."""
    TRANSIENT = "transient"      # Retry with backoff
    PERMANENT = "permanent"      # Don't retry
    RATE_LIMITED = "rate_limited"  # Back off globally
    INSUFFICIENT_FUNDS = "insufficient_funds"  # Special handling


@dataclass
class ProviderResponse:
    """Standardized provider response."""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error_type: Optional[ProviderErrorType] = None
    error_message: Optional[str] = None
    should_retry: bool = False
    retry_after: Optional[int] = None


@dataclass 
class SafeClientResponse:
    """Safe response to return to clients - no provider internals exposed."""
    status: str  # "accepted", "queued", "failed"
    job_id: Optional[str] = None
    message: Optional[str] = None
    code: Optional[str] = None


class CircuitBreaker:
    """Circuit breaker for provider API protection."""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = 0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    def can_execute(self) -> bool:
        """Check if we can make API calls."""
        if self.state == "CLOSED":
            return True
        elif self.state == "OPEN":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "HALF_OPEN"
                return True
            return False
        else:  # HALF_OPEN
            return True
    
    def record_success(self):
        """Record successful API call."""
        self.failure_count = 0
        self.state = "CLOSED"
    
    def record_failure(self):
        """Record failed API call."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning(f"Circuit breaker opened after {self.failure_count} failures")


class EnhancedBoostService:
    """Enhanced boost service with safe error handling and job system."""
    
    def __init__(self):
        self.bot = Bot(token=APIConfig.TELEGRAM_BOT_TOKEN)
        self.circuit_breaker = CircuitBreaker()
        self.active_jobs: Dict[str, asyncio.Task] = {}
        
        # Retry configuration
        self.max_retries = 3
        self.base_delay = 1.0  # Base delay for exponential backoff
        self.max_delay = 60.0  # Maximum delay
        self.jitter_max = 0.1  # Maximum jitter
    
    async def request_boost(
        self,
        link: str,
        likes: int = 100,
        views: int = 500,
        comments: int = 0,
        user_id: Optional[int] = None,
        correlation_id: Optional[str] = None
    ) -> SafeClientResponse:
        """
        Request a boost job - always returns safe response to client.
        
        Args:
            link: URL to boost
            likes: Number of likes
            views: Number of views
            comments: Number of comments
            user_id: User requesting boost
            correlation_id: Optional correlation ID
            
        Returns:
            SafeClientResponse - never exposes provider internals
        """
        
        if not correlation_id:
            correlation_id = generate_correlation_id()
        
        with correlation_context(correlation_id):
            try:
                # Create job with immutable provider snapshot
                job = await job_system.create_boost_job(
                    link=link,
                    likes=likes,
                    views=views,
                    comments=comments,
                    user_id=user_id,
                    correlation_id=correlation_id
                )
                
                # Start async processing 
                self._start_job_processing(job)
                
                # Always return safe "accepted" response to client
                return SafeClientResponse(
                    status="accepted",
                    job_id=job.job_id,
                    message="Boost request accepted and queued for processing"
                )
                
            except Exception as e:
                # Log internal error but return safe message to client
                logger.error(
                    f"Failed to create boost job: {e}",
                    extra={'correlation_id': correlation_id, 'user_id': user_id}
                )
                
                return SafeClientResponse(
                    status="failed",
                    code="BOOST_TEMPORARILY_UNAVAILABLE", 
                    message="Boost service temporarily unavailable. Please try again later."
                )
    
    def _start_job_processing(self, job: Job):
        """Start async job processing."""
        task = asyncio.create_task(self._process_job(job))
        self.active_jobs[job.job_id] = task
        
        # Clean up completed tasks
        def cleanup(task):
            self.active_jobs.pop(job.job_id, None)
        
        task.add_done_callback(cleanup)
    
    async def _process_job(self, job: Job):
        """Process a boost job with retries and safe error handling."""
        
        correlation_id = job.correlation_id or generate_correlation_id()
        
        with correlation_context(correlation_id):
            try:
                # Update job status
                job_system.update_job_status(job.job_id, JobStatus.IN_PROGRESS)
                
                # Get provider config from job snapshot (prevents service_id leaks)
                provider = job_system.get_provider_from_job(job)
                
                logger.info(
                    f"Processing boost job {job.job_id} with provider {provider.name}",
                    extra={
                        'job_id': job.job_id,
                        'provider_name': provider.name,
                        'correlation_id': correlation_id
                    }
                )
                
                # Execute boost with retries
                payload = BoostJobPayload(**job.payload)
                success = await self._execute_boost_with_retries(job, provider, payload)
                
                if success:
                    job_system.update_job_status(job.job_id, JobStatus.COMPLETED)
                    logger.info(f"Boost job {job.job_id} completed successfully")
                else:
                    job_system.update_job_status(
                        job.job_id, 
                        JobStatus.FAILED,
                        error_message="Failed after all retries"
                    )
                    logger.error(f"Boost job {job.job_id} failed after all retries")
                
            except Exception as e:
                logger.error(
                    f"Unexpected error processing job {job.job_id}: {e}",
                    extra={'job_id': job.job_id, 'correlation_id': correlation_id}
                )
                job_system.update_job_status(
                    job.job_id,
                    JobStatus.FAILED, 
                    error_message=f"Unexpected error: {str(e)[:200]}"
                )
    
    async def _execute_boost_with_retries(
        self,
        job: Job,
        provider,
        payload: BoostJobPayload
    ) -> bool:
        """Execute boost with retry logic and circuit breaker."""
        
        retry_count = 0
        
        while retry_count <= self.max_retries:
            # Check circuit breaker
            if not self.circuit_breaker.can_execute():
                logger.warning("Circuit breaker open - skipping provider API call")
                await self._notify_admin_circuit_breaker(job, provider)
                return False
            
            # Calculate delay with exponential backoff and jitter
            if retry_count > 0:
                delay = min(
                    self.base_delay * (2 ** (retry_count - 1)), 
                    self.max_delay
                )
                jitter = delay * self.jitter_max * (0.5 - asyncio.get_event_loop().time() % 1)
                await asyncio.sleep(delay + jitter)
            
            # Try views boost
            if payload.views > 0:
                response = await self._call_provider_api(
                    provider, 
                    provider.view_service_id,
                    payload.link,
                    payload.views,
                    job.correlation_id
                )
                
                if not response.success:
                    if response.error_type == ProviderErrorType.PERMANENT:
                        logger.warning(f"Permanent error for job {job.job_id} - not retrying")
                        self.circuit_breaker.record_failure()
                        return False
                    elif response.error_type == ProviderErrorType.RATE_LIMITED:
                        logger.warning(f"Rate limited for job {job.job_id}")
                        self.circuit_breaker.record_failure()
                        # Wait for rate limit
                        if response.retry_after:
                            await asyncio.sleep(response.retry_after)
                        retry_count += 1
                        continue
                    elif response.error_type == ProviderErrorType.INSUFFICIENT_FUNDS:
                        await self._notify_admin_insufficient_funds(job, provider)
                        return False
                    else:
                        # Transient error - retry
                        retry_count += 1
                        continue
            
            # Try likes boost  
            if payload.likes > 0:
                response = await self._call_provider_api(
                    provider,
                    provider.like_service_id,
                    payload.link,
                    payload.likes,
                    job.correlation_id
                )
                
                if not response.success:
                    # Same error handling as views
                    if response.error_type == ProviderErrorType.PERMANENT:
                        self.circuit_breaker.record_failure()
                        return False
                    elif response.error_type == ProviderErrorType.RATE_LIMITED:
                        self.circuit_breaker.record_failure()
                        if response.retry_after:
                            await asyncio.sleep(response.retry_after)
                        retry_count += 1
                        continue
                    elif response.error_type == ProviderErrorType.INSUFFICIENT_FUNDS:
                        await self._notify_admin_insufficient_funds(job, provider)
                        return False
                    else:
                        retry_count += 1
                        continue
            
            # Success
            self.circuit_breaker.record_success()
            return True
        
        # All retries exhausted
        logger.error(f"All retries exhausted for job {job.job_id}")
        return False
    
    async def _call_provider_api(
        self,
        provider,
        service_id: int,
        link: str,
        quantity: int,
        correlation_id: str
    ) -> ProviderResponse:
        """
        Call provider API with safe error handling.
        Never leak provider internals to clients.
        
        Uses new Plugsmm adapter for plugsmms provider, legacy method for others.
        """
        
        # Use new adapter for plugsmms if enabled
        use_plugsmm_adapter = (
            provider.name == "plugsmms" and
            os.getenv("PLUGSMM_USE_NEW_API", "true").lower() == "true"
        )
        
        if use_plugsmm_adapter:
            return await self._call_plugsmm_adapter(
                provider, service_id, link, quantity, correlation_id
            )
        else:
            return await self._call_legacy_provider_api(
                provider, service_id, link, quantity, correlation_id
            )
    
    async def _call_plugsmm_adapter(
        self,
        provider,
        service_id: int,
        link: str,
        quantity: int,
        correlation_id: str
    ) -> ProviderResponse:
        """
        Call Plugsmm API using the new adapter.
        """
        try:
            # Import adapter (lazy to avoid circular imports)
            from utils.plugsmm_adapter import create_plugsmm_adapter
            
            adapter = create_plugsmm_adapter(
                api_url=provider.api_url,
                api_key=provider.api_key
            )
            
            # Make request
            response = await adapter.add_order(
                service_id=service_id,
                link=link,
                quantity=quantity,
                correlation_id=correlation_id
            )
            
            # Convert to ProviderResponse
            if response.success:
                return ProviderResponse(
                    success=True,
                    data=response.data
                )
            else:
                # Classify error
                return self._classify_plugsmm_error(response.error, response.raw_response)
                
        except Exception as e:
            logger.error(
                f"Plugsmm adapter error: {e}",
                extra={'correlation_id': correlation_id},
                exc_info=True
            )
            return ProviderResponse(
                success=False,
                error_type=ProviderErrorType.TRANSIENT,
                error_message="Adapter error",
                should_retry=True
            )
    
    def _classify_plugsmm_error(
        self,
        error_msg: Optional[str],
        raw_response: Optional[Dict[str, Any]]
    ) -> ProviderResponse:
        """
        Classify Plugsmm-specific errors.
        """
        if not error_msg:
            error_msg = "Unknown error"
        
        error_lower = error_msg.lower()
        
        # Insufficient funds
        if "not enough funds" in error_lower or "insufficient balance" in error_lower:
            return ProviderResponse(
                success=False,
                error_type=ProviderErrorType.INSUFFICIENT_FUNDS,
                error_message="Insufficient balance",
                should_retry=False
            )
        
        # Invalid service
        if "incorrect service" in error_lower or "invalid service" in error_lower:
            return ProviderResponse(
                success=False,
                error_type=ProviderErrorType.PERMANENT,
                error_message="Invalid service ID",
                should_retry=False
            )
        
        # Invalid API key
        if "incorrect api key" in error_lower or "invalid key" in error_lower or "unauthorized" in error_lower:
            return ProviderResponse(
                success=False,
                error_type=ProviderErrorType.PERMANENT,
                error_message="Invalid API key",
                should_retry=False
            )
        
        # Rate limiting
        if "rate limit" in error_lower or "too many requests" in error_lower:
            return ProviderResponse(
                success=False,
                error_type=ProviderErrorType.RATE_LIMITED,
                error_message="Rate limited",
                should_retry=True,
                retry_after=60
            )
        
        # Duplicate/active order
        if "active order" in error_lower or "duplicate" in error_lower:
            return ProviderResponse(
                success=False,
                error_type=ProviderErrorType.TRANSIENT,
                error_message="Active order exists",
                should_retry=True
            )
        
        # Invalid link
        if "incorrect link" in error_lower or "invalid link" in error_lower or "invalid url" in error_lower:
            return ProviderResponse(
                success=False,
                error_type=ProviderErrorType.PERMANENT,
                error_message="Invalid link",
                should_retry=False
            )
        
        # Network/timeout errors
        if "timeout" in error_lower or "network error" in error_lower:
            return ProviderResponse(
                success=False,
                error_type=ProviderErrorType.TRANSIENT,
                error_message="Network error",
                should_retry=True
            )
        
        # Default to transient for unknown errors
        return ProviderResponse(
            success=False,
            error_type=ProviderErrorType.TRANSIENT,
            error_message=error_msg,
            should_retry=True
        )
    
    async def _call_legacy_provider_api(
        self,
        provider,
        service_id: int,
        link: str,
        quantity: int,
        correlation_id: str
    ) -> ProviderResponse:
        """
        Call provider API using legacy method (for non-plugsmms providers).
        Never leak provider internals to clients.
        """
        
        payload = {
            "key": provider.api_key,
            "action": "add",
            "service": service_id,
            "link": link,
            "quantity": quantity
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    provider.api_url,
                    data=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    
                    response.raise_for_status()
                    data = await response.json()
                    
                    # Log full provider response for debugging
                    log_provider_error(
                        logger, provider.name, data, correlation_id
                    )
                    
                    return self._classify_provider_response(data, provider.name)
                    
        except aiohttp.ClientError as e:
            log_provider_error(logger, provider.name, str(e), correlation_id)
            return ProviderResponse(
                success=False,
                error_type=ProviderErrorType.TRANSIENT,
                error_message="Network error",
                should_retry=True
            )
            
        except asyncio.TimeoutError:
            log_provider_error(logger, provider.name, "Timeout", correlation_id)
            return ProviderResponse(
                success=False,
                error_type=ProviderErrorType.TRANSIENT,
                error_message="Request timeout",
                should_retry=True
            )
            
        except json.JSONDecodeError as e:
            log_provider_error(logger, provider.name, f"Invalid JSON: {e}", correlation_id)
            return ProviderResponse(
                success=False,
                error_type=ProviderErrorType.TRANSIENT,
                error_message="Invalid response format",
                should_retry=True
            )
            
        except Exception as e:
            log_provider_error(logger, provider.name, f"Unexpected error: {e}", correlation_id)
            return ProviderResponse(
                success=False,
                error_type=ProviderErrorType.TRANSIENT,
                error_message="Unexpected error",
                should_retry=True
            )
    
    def _classify_provider_response(self, data: Dict[str, Any], provider_name: str) -> ProviderResponse:
        """Classify provider response and determine retry strategy."""
        
        if "error" not in data:
            # Success
            return ProviderResponse(success=True, data=data)
        
        error_msg = str(data.get("error", "")).lower()
        
        # Insufficient funds
        if "not enough funds" in error_msg or "insufficient balance" in error_msg:
            return ProviderResponse(
                success=False,
                error_type=ProviderErrorType.INSUFFICIENT_FUNDS,
                error_message="Insufficient balance",
                should_retry=False
            )
        
        # Rate limiting
        if "rate limit" in error_msg or "too many requests" in error_msg:
            return ProviderResponse(
                success=False,
                error_type=ProviderErrorType.RATE_LIMITED,
                error_message="Rate limited",
                should_retry=True,
                retry_after=60  # Default 60 seconds
            )
        
        # Active order (transient)
        if "active order" in error_msg:
            return ProviderResponse(
                success=False,
                error_type=ProviderErrorType.TRANSIENT,
                error_message="Active order exists",
                should_retry=True
            )
        
        # Invalid service/auth (permanent)
        if any(term in error_msg for term in ["invalid service", "invalid key", "unauthorized", "forbidden"]):
            return ProviderResponse(
                success=False,
                error_type=ProviderErrorType.PERMANENT,
                error_message="Invalid configuration",
                should_retry=False
            )
        
        # Default to transient for unknown errors
        return ProviderResponse(
            success=False,
            error_type=ProviderErrorType.TRANSIENT,
            error_message="Unknown error",
            should_retry=True
        )
    
    async def _notify_admin_insufficient_funds(self, job: Job, provider):
        """Notify admin about insufficient funds - internal notification only."""
        
        payload = BoostJobPayload(**job.payload)
        
        message = render_markdown_v2(
            TEMPLATES['balance_alert'],
            provider_name=provider.name,
            currency="USD",  # Assuming USD for now
            balance="LOW"
        )
        
        await self._send_admin_notification(message, job.correlation_id)
    
    async def _notify_admin_circuit_breaker(self, job: Job, provider):
        """Notify admin about circuit breaker activation."""
        
        message = render_markdown_v2(
            "🔴 *Provider Circuit Breaker Activated* 🔴\n\n"
            "Provider {provider_name} has been temporarily disabled due to repeated failures\\.\n"
            "Job {job_id} has been queued for retry\\.",
            provider_name=provider.name,
            job_id=job.job_id
        )
        
        await self._send_admin_notification(message, job.correlation_id)
    
    async def _send_admin_notification(self, message: str, correlation_id: str):
        """Send notification to admin group - internal only, never to clients."""
        
        try:
            group_chat_id = await get_group_id_from_db(TARGET_NOTIFICATION_GROUP_ID_FROM_DB)
            
            if group_chat_id is None:
                logger.warning(f"Cannot send admin notification - target group not found")
                return
            
            await safe_send(
                self.bot,
                chat_id=group_chat_id,
                text=message,
                parse_mode='MarkdownV2',
                correlation_id=correlation_id
            )
            
            logger.info("Admin notification sent successfully")
            
        except Exception as e:
            logger.error(f"Failed to send admin notification: {e}")


# Global enhanced boost service instance  
enhanced_boost_service = EnhancedBoostService()