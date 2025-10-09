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
    mock_payload.views = 2500  # Will require 3 batches (1k, 1k, 500)
    mock_payload.likes = 50
    mock_payload.link = "https://test.com"
    
    # Start timing
    start_time = time.time()
    
    # Execute boost - with very short intervals for testing
    # Temporarily override the intervals
    import utils.boost_utils_enhanced as boost_module
    original_first = boost_module.FIRST_BOOST_INTERVAL_SECONDS
    original_second = boost_module.SECOND_BOOST_INTERVAL_SECONDS
    
    # Use 0.5 second intervals for testing
    boost_module.FIRST_BOOST_INTERVAL_SECONDS = 0.5
    boost_module.SECOND_BOOST_INTERVAL_SECONDS = 0.5
    
    try:
        result = await service._execute_boost_with_retries(mock_job, mock_provider, mock_payload)
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Should have called _send_boost_with_retries 4 times:
        # 1. Batch 1: 1000 views
        # 2. Batch 2: 1000 views
        # 3. Batch 3: 500 views
        # 4. Batch 3: 50 likes (with final batch)
        assert len(call_times) == 4, f"Expected 4 calls, got {len(call_times)}"
        
        # Total time should be at least 1.5 seconds (3 intervals of 0.5 seconds each)
        assert total_time >= 1.5, f"Expected at least 1.5 seconds, got {total_time}"
        
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
    mock_payload.views = 2500  # Will require 3 batches (1k, 1k, 500)
    mock_payload.likes = 150
    mock_payload.link = "https://test.com"
    
    # Temporarily override the intervals for faster testing
    import utils.boost_utils_enhanced as boost_module
    original_first = boost_module.FIRST_BOOST_INTERVAL_SECONDS
    original_second = boost_module.SECOND_BOOST_INTERVAL_SECONDS
    boost_module.FIRST_BOOST_INTERVAL_SECONDS = 0.1
    boost_module.SECOND_BOOST_INTERVAL_SECONDS = 0.1
    
    try:
        result = await service._execute_boost_with_retries(mock_job, mock_provider, mock_payload)
        
        # Check that we have 4 calls: 3 view batches + 1 likes batch
        assert len(call_log) == 4, f"Expected 4 calls, got {len(call_log)}"
        
        # First batch should have 1000 views
        views_batch_1 = [c for c in call_log if 'batch 1' in c['type'] and c['service_id'] == 1]
        assert len(views_batch_1) == 1, "Expected 1 view batch 1 call"
        assert views_batch_1[0]['quantity'] == 1000, f"Expected 1000 views in batch 1, got {views_batch_1[0]['quantity']}"
        
        # Second batch should have 1000 views
        views_batch_2 = [c for c in call_log if 'batch 2' in c['type'] and c['service_id'] == 1]
        assert len(views_batch_2) == 1, "Expected 1 view batch 2 call"
        assert views_batch_2[0]['quantity'] == 1000, f"Expected 1000 views in batch 2, got {views_batch_2[0]['quantity']}"
        
        # Third batch should have 500 views
        views_batch_3 = [c for c in call_log if 'batch 3' in c['type'] and c['service_id'] == 1]
        assert len(views_batch_3) == 1, "Expected 1 view batch 3 call"
        assert views_batch_3[0]['quantity'] == 500, f"Expected 500 views in batch 3, got {views_batch_3[0]['quantity']}"
        
        # All likes should be sent with the final batch
        likes_calls = [c for c in call_log if c['service_id'] == 2]
        assert len(likes_calls) == 1, f"Expected 1 likes call, got {len(likes_calls)}"
        assert likes_calls[0]['quantity'] == 150, f"Expected 150 likes, got {likes_calls[0]['quantity']}"
        assert 'final batch' in likes_calls[0]['type'], "Likes should be sent with final batch"
        
        print("✓ Phased boosting correctly sends views in 1k batches and all likes with final batch")
        
    finally:
        # Restore original intervals
        boost_module.FIRST_BOOST_INTERVAL_SECONDS = original_first
        boost_module.SECOND_BOOST_INTERVAL_SECONDS = original_second
    
    return True


async def test_phased_boosting_small_views():
    """Test that views less than 1k are sent in a single batch with all likes."""
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
    mock_job.job_id = "test-job-789"
    mock_job.correlation_id = "test-correlation-id"
    
    mock_provider = MagicMock()
    mock_provider.view_service_id = 1
    mock_provider.like_service_id = 2
    
    mock_payload = MagicMock()
    mock_payload.views = 500  # Less than 1k
    mock_payload.likes = 100
    mock_payload.link = "https://test.com"
    
    # Temporarily override the intervals for faster testing
    import utils.boost_utils_enhanced as boost_module
    original_first = boost_module.FIRST_BOOST_INTERVAL_SECONDS
    boost_module.FIRST_BOOST_INTERVAL_SECONDS = 0.1
    
    try:
        result = await service._execute_boost_with_retries(mock_job, mock_provider, mock_payload)
        
        # Check that we have 2 calls: 1 view batch + 1 likes batch
        assert len(call_log) == 2, f"Expected 2 calls, got {len(call_log)}"
        
        # First batch should have 500 views
        views_batch = [c for c in call_log if c['service_id'] == 1]
        assert len(views_batch) == 1, "Expected 1 view batch call"
        assert views_batch[0]['quantity'] == 500, f"Expected 500 views, got {views_batch[0]['quantity']}"
        
        # All likes should be sent with the final (only) batch
        likes_calls = [c for c in call_log if c['service_id'] == 2]
        assert len(likes_calls) == 1, f"Expected 1 likes call, got {len(likes_calls)}"
        assert likes_calls[0]['quantity'] == 100, f"Expected 100 likes, got {likes_calls[0]['quantity']}"
        
        print("✓ Small view count correctly sends in single batch with all likes")
        
    finally:
        # Restore original intervals
        boost_module.FIRST_BOOST_INTERVAL_SECONDS = original_first
    
    return True


def main():
    """Run all tests."""
    print("Starting phased boosting tests...\n")
    
    async def run_all_tests():
        try:
            # Run tests
            await test_phased_boosting_timing()
            await test_phased_boosting_splits_correctly()
            await test_phased_boosting_small_views()
            
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
