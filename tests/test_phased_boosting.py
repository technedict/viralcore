#!/usr/bin/env python3
"""
Tests for phased boosting functionality in the enhanced boost service.
"""

import sys
import os
import asyncio
import time
from unittest.mock import Mock, AsyncMock, MagicMock, patch

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock the dependencies before importing
sys.modules['utils.config'] = MagicMock()
sys.modules['utils.db_utils'] = MagicMock()
sys.modules['utils.notification'] = MagicMock()
sys.modules['utils.logging'] = MagicMock()
sys.modules['utils.messaging'] = MagicMock()
sys.modules['utils.job_system'] = MagicMock()

# Mock telegram
sys.modules['telegram'] = MagicMock()

# Mock aiohttp
sys.modules['aiohttp'] = MagicMock()

# Set up mock logger
mock_logger = MagicMock()
sys.modules['utils.logging'].get_logger = MagicMock(return_value=mock_logger)
sys.modules['utils.logging'].correlation_context = MagicMock()
sys.modules['utils.logging'].generate_correlation_id = MagicMock(return_value='test-correlation-id')


async def test_phased_boosting_timing():
    """Test that phased boosting waits the correct amount of time."""
    from utils.boost_utils_enhanced import EnhancedBoostService, FIRST_BOOST_INTERVAL_SECONDS, SECOND_BOOST_INTERVAL_SECONDS
    
    # Create service instance
    service = EnhancedBoostService()
    
    # Mock the _send_boost_with_retries method to track calls and timing
    call_times = []
    original_send = service._send_boost_with_retries
    
    async def mock_send(*args, **kwargs):
        call_times.append(time.time())
        # Return success immediately
        return True
    
    service._send_boost_with_retries = mock_send
    
    # Mock job and provider
    mock_job = MagicMock()
    mock_job.job_id = "test-job-123"
    mock_job.correlation_id = "test-correlation-id"
    
    mock_provider = MagicMock()
    mock_provider.view_service_id = 1
    mock_provider.like_service_id = 2
    
    mock_payload = MagicMock()
    mock_payload.views = 100
    mock_payload.likes = 50
    mock_payload.link = "https://test.com"
    
    # Start timing
    start_time = time.time()
    
    # Execute boost - with very short intervals for testing
    # Temporarily override the intervals
    import utils.boost_utils_enhanced as boost_module
    original_first = boost_module.FIRST_BOOST_INTERVAL_SECONDS
    original_second = boost_module.SECOND_BOOST_INTERVAL_SECONDS
    
    # Use 1 second intervals for testing
    boost_module.FIRST_BOOST_INTERVAL_SECONDS = 1
    boost_module.SECOND_BOOST_INTERVAL_SECONDS = 1
    
    try:
        result = await service._execute_boost_with_retries(mock_job, mock_provider, mock_payload)
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Should have called _send_boost_with_retries 4 times:
        # 1. First half views (after 1 sec delay)
        # 2. First half likes (after 1 sec delay)
        # 3. Second half views (after 1 sec delay)
        # 4. Second half likes (after 1 sec delay)
        assert len(call_times) == 4, f"Expected 4 calls, got {len(call_times)}"
        
        # Total time should be at least 2 seconds (2 intervals of 1 second each)
        assert total_time >= 2.0, f"Expected at least 2 seconds, got {total_time}"
        
        # Result should be True (success)
        assert result == True, f"Expected success, got {result}"
        
        print(f"✓ Phased boosting test passed - 4 calls made over {total_time:.2f} seconds")
        
    finally:
        # Restore original intervals
        boost_module.FIRST_BOOST_INTERVAL_SECONDS = original_first
        boost_module.SECOND_BOOST_INTERVAL_SECONDS = original_second
    
    return True


async def test_phased_boosting_splits_correctly():
    """Test that views and likes are split correctly between batches."""
    from utils.boost_utils_enhanced import EnhancedBoostService
    
    # Create service instance
    service = EnhancedBoostService()
    
    # Mock the _send_boost_with_retries method to track quantities
    call_log = []
    
    async def mock_send(job, provider, service_id, link, quantity, boost_type):
        call_log.append({
            'service_id': service_id,
            'quantity': quantity,
            'type': boost_type
        })
        return True
    
    service._send_boost_with_retries = mock_send
    
    # Mock job and provider
    mock_job = MagicMock()
    mock_job.job_id = "test-job-456"
    mock_job.correlation_id = "test-correlation-id"
    
    mock_provider = MagicMock()
    mock_provider.view_service_id = 1
    mock_provider.like_service_id = 2
    
    mock_payload = MagicMock()
    mock_payload.views = 100
    mock_payload.likes = 50
    mock_payload.link = "https://test.com"
    
    # Temporarily override the intervals for faster testing
    import utils.boost_utils_enhanced as boost_module
    original_first = boost_module.FIRST_BOOST_INTERVAL_SECONDS
    original_second = boost_module.SECOND_BOOST_INTERVAL_SECONDS
    boost_module.FIRST_BOOST_INTERVAL_SECONDS = 0.1
    boost_module.SECOND_BOOST_INTERVAL_SECONDS = 0.1
    
    try:
        result = await service._execute_boost_with_retries(mock_job, mock_provider, mock_payload)
        
        # Check that we have 4 calls
        assert len(call_log) == 4, f"Expected 4 calls, got {len(call_log)}"
        
        # First batch should have half the quantities
        views_first = [c for c in call_log if 'first half' in c['type'] and c['service_id'] == 1]
        likes_first = [c for c in call_log if 'first half' in c['type'] and c['service_id'] == 2]
        
        assert len(views_first) == 1, "Expected 1 first half views call"
        assert views_first[0]['quantity'] == 50, f"Expected 50 views in first batch, got {views_first[0]['quantity']}"
        
        assert len(likes_first) == 1, "Expected 1 first half likes call"
        assert likes_first[0]['quantity'] == 25, f"Expected 25 likes in first batch, got {likes_first[0]['quantity']}"
        
        # Second batch should have remaining quantities
        views_second = [c for c in call_log if 'second half' in c['type'] and c['service_id'] == 1]
        likes_second = [c for c in call_log if 'second half' in c['type'] and c['service_id'] == 2]
        
        assert len(views_second) == 1, "Expected 1 second half views call"
        assert views_second[0]['quantity'] == 50, f"Expected 50 views in second batch, got {views_second[0]['quantity']}"
        
        assert len(likes_second) == 1, "Expected 1 second half likes call"
        assert likes_second[0]['quantity'] == 25, f"Expected 25 likes in second batch, got {likes_second[0]['quantity']}"
        
        print("✓ Phased boosting correctly splits views and likes into two batches")
        
    finally:
        # Restore original intervals
        boost_module.FIRST_BOOST_INTERVAL_SECONDS = original_first
        boost_module.SECOND_BOOST_INTERVAL_SECONDS = original_second
    
    return True


def main():
    """Run all tests."""
    print("Starting phased boosting tests...\n")
    
    async def run_all_tests():
        try:
            # Run tests
            await test_phased_boosting_timing()
            await test_phased_boosting_splits_correctly()
            
            print("\n✅ All phased boosting tests passed!")
            return 0
            
        except Exception as e:
            print(f"\n❌ Test failed: {e}")
            import traceback
            traceback.print_exc()
            return 1
    
    # Run async tests
    return asyncio.run(run_all_tests())


if __name__ == "__main__":
    exit(main())
