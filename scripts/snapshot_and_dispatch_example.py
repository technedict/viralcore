#!/usr/bin/env python3
"""
Snapshot and Dispatch Example Script

Demonstrates the proper pattern for job creation and worker dispatch
using immutable provider snapshots to prevent service_id leaks.
"""

import sys
import os
import asyncio
import json
from datetime import datetime

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.job_system import job_system, Job, JobStatus, JobType
from utils.boost_utils_enhanced import enhanced_boost_service
from utils.boost_provider_utils import get_active_provider, PROVIDERS
from utils.logging import get_logger, setup_logging, correlation_context

# Setup logging
setup_logging(console_log_level=20)  # INFO level
logger = get_logger(__name__)


async def example_job_creation():
    """Example: Create a boost job with immutable provider snapshot."""
    
    logger.info("=== Job Creation Example ===")
    
    correlation_id = "example_001"
    
    with correlation_context(correlation_id):
        # Show current active provider
        current_provider = get_active_provider()
        logger.info(f"Current active provider: {current_provider.name}")
        logger.info(f"View Service ID: {current_provider.view_service_id}")
        logger.info(f"Like Service ID: {current_provider.like_service_id}")
        
        # Create job - this captures immutable snapshot
        job = await job_system.create_boost_job(
            link="https://example.com/post123",
            likes=50,
            views=200,
            comments=0,
            user_id=12345,
            correlation_id=correlation_id
        )
        
        logger.info(f"Created job: {job.job_id}")
        logger.info(f"Job provider snapshot: {job.provider_snapshot.provider_name}")
        logger.info(f"Snapshot view service ID: {job.provider_snapshot.view_service_id}")
        logger.info(f"Snapshot like service ID: {job.provider_snapshot.like_service_id}")
        
        return job


async def example_provider_switch_during_job():
    """Example: Show what happens when provider is switched after job creation."""
    
    logger.info("=== Provider Switch During Job Example ===")
    
    correlation_id = "example_002"
    
    with correlation_context(correlation_id):
        # Create job with current provider
        job = await job_system.create_boost_job(
            link="https://example.com/post456",
            likes=25,
            views=100,
            correlation_id=correlation_id
        )
        
        original_provider = job.provider_snapshot.provider_name
        logger.info(f"Job created with provider: {original_provider}")
        
        # Simulate provider switch (this would happen in admin handler)
        from utils.boost_provider_utils import ProviderConfig
        
        # Switch to a different provider
        new_provider_name = None
        for name in PROVIDERS.keys():
            if name != original_provider:
                new_provider_name = name
                break
        
        if new_provider_name:
            logger.info(f"Switching active provider to: {new_provider_name}")
            ProviderConfig.set_active_provider_name(new_provider_name)
            
            # Get current active provider (now different)
            current_provider = get_active_provider()
            logger.info(f"New active provider: {current_provider.name}")
            
            # Retrieve job - snapshot should be unchanged
            retrieved_job = job_system.get_job(job.job_id)
            logger.info(f"Job still uses original provider: {retrieved_job.provider_snapshot.provider_name}")
            
            # Show that worker will use snapshot, not current provider
            worker_provider = job_system.get_provider_from_job(retrieved_job)
            logger.info(f"Worker will use provider: {worker_provider.name}")
            logger.info(f"Worker view service ID: {worker_provider.view_service_id}")
            logger.info(f"Worker like service ID: {worker_provider.like_service_id}")
            
            # Reset to original provider
            ProviderConfig.set_active_provider_name(original_provider)
        
        return job


async def example_job_dispatch():
    """Example: Dispatch job using snapshot (prevents service_id leak)."""
    
    logger.info("=== Job Dispatch Example ===")
    
    correlation_id = "example_003"
    
    with correlation_context(correlation_id):
        # Create job
        job = await job_system.create_boost_job(
            link="https://example.com/post789",
            likes=75,
            views=300,
            correlation_id=correlation_id
        )
        
        logger.info(f"Dispatching job: {job.job_id}")
        
        # Show how worker gets provider config from snapshot
        worker_provider = job_system.get_provider_from_job(job)
        
        logger.info(f"Worker provider config:")
        logger.info(f"  Name: {worker_provider.name}")
        logger.info(f"  API URL: {worker_provider.api_url}")
        logger.info(f"  View Service ID: {worker_provider.view_service_id}")
        logger.info(f"  Like Service ID: {worker_provider.like_service_id}")
        
        # Show job payload
        payload = job.payload
        logger.info(f"Job payload: {json.dumps(payload, indent=2)}")
        
        # This is what the worker would do:
        # 1. Get provider config from job snapshot (not current active provider)
        # 2. Use service IDs from snapshot
        # 3. Use current API key for security
        
        logger.info("Worker would now make API calls using snapshot service IDs")
        
        return job


async def example_idempotency():
    """Example: Demonstrate idempotency key usage."""
    
    logger.info("=== Idempotency Example ===")
    
    correlation_id = "example_004"
    
    with correlation_context(correlation_id):
        # Create job with specific idempotency key
        idempotency_key = "boost_example_post_001"
        
        job1 = await job_system.create_boost_job(
            link="https://example.com/post001",
            likes=100,
            views=500,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id
        )
        
        logger.info(f"First job created: {job1.job_id}")
        
        # Try to create same job again
        job2 = await job_system.create_boost_job(
            link="https://example.com/post001",
            likes=100,
            views=500,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id
        )
        
        # Should get existing job
        existing_job = job_system.get_job_by_idempotency_key(idempotency_key)
        
        if existing_job:
            logger.info(f"Idempotency worked - existing job: {existing_job.job_id}")
        else:
            logger.warning("Idempotency failed - new job created")


async def example_safe_client_response():
    """Example: Show safe client responses that don't leak provider internals."""
    
    logger.info("=== Safe Client Response Example ===")
    
    correlation_id = "example_005"
    
    with correlation_context(correlation_id):
        # Request boost through enhanced service
        response = await enhanced_boost_service.request_boost(
            link="https://example.com/client_post",
            likes=50,
            views=200,
            user_id=98765,
            correlation_id=correlation_id
        )
        
        logger.info("Client Response:")
        logger.info(f"  Status: {response.status}")
        logger.info(f"  Job ID: {response.job_id}")
        logger.info(f"  Message: {response.message}")
        
        if response.code:
            logger.info(f"  Code: {response.code}")
        
        logger.info("Note: No provider internals exposed to client")


async def example_error_handling():
    """Example: Show how provider errors are handled safely."""
    
    logger.info("=== Error Handling Example ===")
    
    correlation_id = "example_006"
    
    with correlation_context(correlation_id):
        # This would normally trigger provider API calls
        # Here we just show the pattern
        
        logger.info("Provider errors are:")
        logger.info("1. Logged with full details for debugging")
        logger.info("2. Classified as TRANSIENT, PERMANENT, RATE_LIMITED, etc.")
        logger.info("3. Mapped to safe client responses")
        logger.info("4. Never expose raw provider error messages to clients")
        
        # Example safe error responses:
        safe_responses = [
            "Boost request accepted and queued for processing",
            "Boost service temporarily unavailable. Please try again later.",
            "Request failed due to invalid parameters. Please check and retry.",
        ]
        
        for response in safe_responses:
            logger.info(f"Safe response: {response}")


async def main():
    """Run all examples."""
    
    logger.info("Starting snapshot and dispatch examples...")
    
    try:
        # Initialize job system
        job_system._init_database()
        
        # Run examples
        await example_job_creation()
        await example_provider_switch_during_job()
        await example_job_dispatch()
        await example_idempotency()
        await example_safe_client_response()
        await example_error_handling()
        
        logger.info("All examples completed successfully")
        
    except Exception as e:
        logger.error(f"Example failed: {e}", exc_info=True)
        return 1
    
    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))