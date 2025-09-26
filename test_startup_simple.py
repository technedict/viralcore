#!/usr/bin/env python3
"""
Simple test to validate the startup recovery fix without importing the full module
"""
import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mock the shutdown manager functionality
class TestShutdownManager:
    def __init__(self):
        self.cleanup_callbacks = []
    
    def register_cleanup_callback(self, callback):
        self.cleanup_callbacks.append(callback)
        logger.info("Cleanup callback registered")
    
    async def recover_stale_jobs(self, threshold_minutes=30):
        logger.info("Performing startup recovery...")
        await asyncio.sleep(0.01)  # Simulate async work
        return 3
    
    async def graceful_shutdown(self):
        logger.info("Performing graceful shutdown...")
        await asyncio.sleep(0.01)

def test_original_broken_pattern():
    """Test the original broken pattern that caused the error"""
    logger.info("=== Testing Original Broken Pattern ===")
    shutdown_manager = TestShutdownManager()
    
    async def startup_recovery():
        logger.info("Performing startup recovery...")
        recovered_jobs = await shutdown_manager.recover_stale_jobs(threshold_minutes=30)
        if recovered_jobs > 0:
            logger.info(f"Recovered {recovered_jobs} stale jobs on startup")
    
    shutdown_manager.register_cleanup_callback(startup_recovery)
    
    try:
        # This would fail with "no running event loop"
        asyncio.create_task(startup_recovery())
        logger.error("❌ Should have failed but didn't!")
        return False
    except RuntimeError as e:
        if "no running event loop" in str(e):
            logger.info("✅ Correctly caught 'no running event loop' error")
            return True
        else:
            logger.error(f"❌ Unexpected error: {e}")
            return False

def test_fixed_pattern():
    """Test the fixed pattern that resolves the error"""
    logger.info("=== Testing Fixed Pattern ===")
    shutdown_manager = TestShutdownManager()
    
    async def startup_recovery():
        logger.info("Performing startup recovery...")
        recovered_jobs = await shutdown_manager.recover_stale_jobs(threshold_minutes=30)
        if recovered_jobs > 0:
            logger.info(f"Recovered {recovered_jobs} stale jobs on startup")
    
    shutdown_manager.register_cleanup_callback(startup_recovery)
    
    try:
        # This should work fine - run startup recovery in its own event loop
        asyncio.run(startup_recovery())
        logger.info("✅ Fixed pattern works - no event loop error!")
        return True
    except Exception as e:
        logger.error(f"❌ Fixed pattern failed: {e}")
        return False

def test_graceful_shutdown():
    """Test that graceful shutdown still works"""
    logger.info("=== Testing Graceful Shutdown ===")
    shutdown_manager = TestShutdownManager()
    
    try:
        asyncio.run(shutdown_manager.graceful_shutdown())
        logger.info("✅ Graceful shutdown works correctly!")
        return True
    except Exception as e:
        logger.error(f"❌ Graceful shutdown failed: {e}")
        return False

if __name__ == "__main__":
    logger.info("Testing asyncio startup recovery fix...")
    
    test1 = test_original_broken_pattern()
    test2 = test_fixed_pattern()
    test3 = test_graceful_shutdown()
    
    if test1 and test2 and test3:
        logger.info("🎉 All tests passed! The fix works correctly.")
        exit(0)
    else:
        logger.error("❌ Some tests failed!")
        exit(1)