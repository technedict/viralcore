# Manual Test Checklist for Asyncio Fix

## Before Testing
Ensure you have the dependencies installed:
```bash
pip install python-telegram-bot python-dotenv aiosqlite
```

## Test Steps

### 1. Normal Startup Test
**Expected**: Bot starts successfully with no errors
```bash
python main_viral_core_bot.py
```

**Look for these log messages (in order):**
- ✅ "Bot is up and running!"
- ✅ "Performing startup recovery..."
- ✅ "Recovered X stale jobs on startup" (if any jobs recovered)
- ✅ NO "no running event loop" error
- ✅ NO "RuntimeWarning: coroutine 'main.<locals>.startup_recovery' was never awaited"

### 2. Graceful Shutdown Test (Ctrl+C)
**Expected**: Clean shutdown sequence
```bash
python main_viral_core_bot.py
# Wait for "Bot is up and running!" message
# Press Ctrl+C
```

**Look for these log messages:**
- ✅ "Received keyboard interrupt, shutting down..."
- ✅ "Starting graceful shutdown..."
- ✅ "Graceful shutdown completed successfully"

### 3. Exception Handling Test
**Expected**: Even with exceptions, no event loop errors occur

If the bot encounters an exception during startup, you should see:
- ✅ "Unexpected error: [error message]"
- ✅ NO "no running event loop" error in the logs
- ✅ NO "RuntimeWarning: coroutine was never awaited"
- ✅ Graceful shutdown still executes properly

### 4. Signal Handler Test (SIGTERM)
**Expected**: Graceful shutdown via signal
```bash
python main_viral_core_bot.py &
PID=$!
# Wait a moment for startup
sleep 2
kill -TERM $PID
wait $PID
```

**Look for:**
- ✅ "Received signal 15, initiating graceful shutdown..."
- ✅ Graceful shutdown sequence completes

## Success Criteria
All tests should pass with:
- ✅ No "no running event loop" runtime errors
- ✅ No "coroutine was never awaited" warnings  
- ✅ Startup recovery executes successfully
- ✅ Graceful shutdown works correctly
- ✅ Bot functionality remains unchanged

## Automated Test
You can also run the automated test suite:
```bash
python test_startup_simple.py
```
Expected output: "🎉 All tests passed! The fix works correctly."