#!/usr/bin/env python3
"""
Basic tests for the job system functionality.
"""

import sys
import os
import asyncio

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.job_system import job_system, JobStatus, JobType, ServiceProviderMismatchError
from utils.logging import setup_logging

def test_job_creation():
    """Test basic job creation."""
    print("Testing job creation...")
    
    async def _test():
        # Create a job
        job = await job_system.create_boost_job(
            link="https://example.com/test",
            likes=50,
            views=200,
            user_id=12345
        )
        
        assert job.job_id is not None
        assert job.status == JobStatus.QUEUED
        assert job.job_type == JobType.BOOST
        assert job.provider_snapshot is not None
        
        print(f"✓ Job created: {job.job_id}")
        print(f"✓ Provider snapshot: {job.provider_snapshot.provider_name}")
        
        return job
    
    return asyncio.run(_test())


def test_provider_validation():
    """Test provider service ID validation.""" 
    print("Testing provider validation...")
    
    # Test valid provider
    try:
        valid = job_system.validate_provider_service_id("smmflare", 8381, "view")
        assert valid == True
        print("✓ Valid provider/service ID accepted")
    except ServiceProviderMismatchError:
        print("✗ Valid provider/service ID rejected")
        raise
    
    # Test invalid service ID
    try:
        job_system.validate_provider_service_id("smmflare", 9999, "view")
        print("✗ Invalid service ID was accepted")
        assert False, "Should have raised ServiceProviderMismatchError"
    except ServiceProviderMismatchError:
        print("✓ Invalid service ID properly rejected")


def main():
    """Run all tests."""
    print("Starting job system tests...")
    
    # Setup logging
    setup_logging(console_log_level=30)  # WARNING level to reduce noise
    
    try:
        # Initialize job system
        job_system._init_database()
        
        # Run tests
        test_job_creation()
        test_provider_validation()
        
        print("\n✅ All job system tests passed!")
        return 0
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())