# ViralCore Implementation Runbook

This runbook provides reproduction steps, verification procedures, and rollback instructions for the new features and fixes implemented.

## Table of Contents
1. [Scheduled Split-Send Behavior](#1-scheduled-split-send-behavior)
2. [Admin Broadcast with Images](#2-admin-broadcast-with-images)
3. [Payment NOTOK Fixes](#3-payment-notok-fixes)
4. [Groups.db Persistence](#4-groupsdb-persistence)
5. [Duplicate Link Submissions](#5-duplicate-link-submissions)

---

## 1. Scheduled Split-Send Behavior

### Overview
Links submitted are now sent to groups in two halves:
- First half: 30 minutes after submission
- Second half: 60 minutes after submission (30 minutes after first half)

### How to Reproduce Original Issue
```bash
# Before the fix, links were sent immediately without split timing
# 1. Submit a link via bot
# 2. Observe that all groups receive the message immediately
# 3. No delay or split behavior
```

### How to Verify Fix

#### Manual Verification
1. Submit a Twitter/X link through the bot
2. Check the database for scheduled sends:
   ```bash
   sqlite3 ./db/viralcore.db "SELECT * FROM scheduled_sends ORDER BY run_at;"
   ```
3. Verify:
   - Two sets of sends are scheduled
   - First half has `run_at` ~30 minutes from now
   - Second half has `run_at` ~60 minutes from now
   - Both share the same `correlation_id`

#### Automated Testing
```bash
# Run scheduled send tests
python3 -m pytest tests/test_scheduled_sends.py -v
```

### Verify Restart Resilience
1. Submit a link (creates scheduled sends)
2. Stop the bot: `Ctrl+C`
3. Wait a few seconds
4. Restart the bot: `python3 main_viral_core_bot.py`
5. Check logs - worker should pick up existing scheduled sends
6. Verify sends still execute at scheduled times

### Monitoring
Check logs for these events:
```
scheduled_send_created: submission=xxx, correlation_id=yyy, first_half=3 groups at ..., second_half=3 groups at ...
scheduled_send_executed: send_id=xxx, submission_id=yyy, correlation_id=zzz
scheduled_send_failed: send_id=xxx, submission_id=yyy, correlation_id=zzz, error=...
```

### Rollback
If issues arise:
1. Stop the bot
2. Revert to previous code version
3. Clear scheduled sends (optional):
   ```bash
   sqlite3 ./db/viralcore.db "DELETE FROM scheduled_sends;"
   ```
4. Restart bot

### Configuration
```bash
# .env configuration
SCHEDULED_SEND_CHECK_INTERVAL=60  # Check for due sends every 60 seconds
```

---

## 2. Admin Broadcast with Images

### Overview
Admins can now attach images to broadcast messages.

### How to Reproduce Original Issue
```bash
# Before the fix:
# 1. Access admin panel → Content & Replies → Broadcast Message
# 2. Try to send a photo - only text was supported
# 3. Photo would be ignored
```

### How to Verify Fix

#### Manual Verification
1. Login as admin
2. Send `/start` and navigate to Admin Panel
3. Select "Content & Replies" → "Broadcast Message"
4. Send a photo with caption (e.g., "Test broadcast with image")
5. Verify:
   - Bot acknowledges receipt
   - All users receive the photo with caption
   - Stats show successful sends

#### Test Without Image
1. Follow steps 1-3 above
2. Send text-only message (no photo)
3. Verify text-only broadcast still works

#### Test Failures
1. Check that failed sends are counted
2. Verify admin sees: "✅ Broadcast sent to X users. ⚠️ Failed to send to Y users."

### Monitoring
Check logs:
```
Broadcast completed: sent=X, failed=Y, has_image=True/False
```

### Rollback
If issues arise:
1. Revert `handlers/admin_message_handlers.py` changes
2. Remove photo handler from `main_viral_core_bot.py`
3. Restart bot

### Documentation
- Images are validated by Telegram (size, format)
- Supported formats: JPEG, PNG, GIF (up to 10MB)
- Caption length: up to 1024 characters

---

## 3. Payment NOTOK Fixes

### Overview
Improved crypto payment verification to eliminate false NOTOK failures.

### Common NOTOK Causes Addressed
1. Address normalization (case sensitivity)
2. Amount precision and tolerance
3. Token symbol variants (USDT, BSC-USD, USD)
4. Transaction age validation
5. Comprehensive logging

### How to Reproduce Original Issue
```bash
# Before the fix:
# 1. User makes valid crypto payment
# 2. Submits transaction hash
# 3. Bot returns "NOTOK" even though payment is valid
# 4. Causes: address mismatch, amount rounding, token symbol variation
```

### How to Verify Fix

#### Manual Verification
1. Use test/sandbox crypto payment
2. Submit transaction hash through bot
3. Check logs for detailed verification steps:
   ```
   Attempt X/3 to check BSC transaction for hash: ...
   Comparing: <tx_hash> == <expected> and <to_address> == <wallet>
   ```
4. Verify payment is accepted

#### Test Address Normalization
```bash
# BSC addresses should be case-insensitive
# Test with different case variations
```

#### Automated Testing
```bash
python3 -m pytest tests/test_payment_verification.py -v
```

### Monitoring
Check logs for:
```
[PaymentHandler] Crypto verification: status=success/error
[PaymentHandler] Found transaction with matching hash
[PaymentHandler] Token symbol check: received=USDT, accepted variants=[USDT, BSC-USD, USD]
```

### Create Replay Script (TODO)
For debugging NOTOK failures:
```python
# TODO: Create scripts/replay_payment.py
# Should accept:
# - Transaction hash
# - Expected amount
# - Wallet address
# And replay verification logic with detailed output
```

### Rollback
If verification becomes too lenient:
1. Revert `handlers/payment_handler.py` changes
2. Adjust tolerance values in code
3. Restart bot

---

## 4. Groups.db Persistence

### Overview
Ensures groups.db file persists across restarts.

### How to Reproduce Original Issue
```bash
# Before the fix (if DB_DIR was set to /tmp):
# 1. Add data to groups.db
# 2. Restart bot or server
# 3. Data is lost (ephemeral storage)
```

### How to Verify Fix

#### Check DB Location
```bash
# Verify DB_DIR is not ephemeral
echo $DB_DIR  # Should be ./db or another persistent path
ls -la ./db/groups.db  # File should exist
```

#### Test Persistence
```bash
# 1. Add a group to groups.db
sqlite3 ./db/groups.db "INSERT INTO groups (group_id, group_name) VALUES (999, 'test_group');"

# 2. Verify insertion
sqlite3 ./db/groups.db "SELECT * FROM groups WHERE group_id=999;"

# 3. Restart the bot
pkill -f main_viral_core_bot.py
python3 main_viral_core_bot.py &

# 4. Verify data still exists after restart
sqlite3 ./db/groups.db "SELECT * FROM groups WHERE group_id=999;"

# 5. Cleanup
sqlite3 ./db/groups.db "DELETE FROM groups WHERE group_id=999;"
```

#### Check Startup Warnings
On startup, if DB_DIR points to ephemeral storage:
```
⚠️  DB_DIR is set to ephemeral storage: /tmp/db
Database files will be lost on restart. Set DB_DIR to persistent storage.
```

### Automated Testing
```bash
python3 -m pytest tests/test_db_centralization.py -v
```

### Configuration
```bash
# .env configuration
DB_DIR=./db  # Use persistent directory (default)
# DB_DIR=/tmp/db  # DO NOT USE - ephemeral storage
```

### Rollback
No rollback needed - this is a safety check only.

---

## 5. Duplicate Link Submissions

### Overview
Users can now submit the same link multiple times.

### How to Reproduce Original Issue
```bash
# Before the fix:
# 1. Submit a Twitter link: https://twitter.com/user/status/123
# 2. Bot processes it successfully
# 3. Submit the same link again
# 4. Bot rejects: "❌ This link has already been submitted."
```

### How to Verify Fix

#### Manual Verification
1. Submit a Twitter/X link through the bot
2. Wait for confirmation
3. Submit the **same link** again
4. Verify:
   - Bot accepts the submission
   - Second submission is processed normally
   - Both submissions appear in database

#### Database Verification
```bash
# Check for duplicate tweet submissions
sqlite3 ./db/tweets.db "SELECT tweet_id, COUNT(*) as count FROM tweets GROUP BY tweet_id HAVING count > 1;"

# Check for duplicate Telegram submissions
sqlite3 ./db/tg.db "SELECT tg_link, COUNT(*) as count FROM telegram_posts GROUP BY tg_link HAVING count > 1;"
```

#### Automated Testing
```bash
python3 -m pytest tests/test_duplicate_links.py -v
```

### Anti-Abuse Considerations
Duplicate submissions are allowed, but abuse is prevented by:
1. **Balance/Post Limits**: Users need remaining posts/balance
2. **Purchase System**: Each submission consumes a post credit
3. **Rate Limiting**: (TODO: Implement if needed)

### Monitoring
No specific monitoring needed. Standard submission logs apply.

### Rollback
If spam becomes an issue:
1. Revert duplicate check removal in `handlers/link_submission_handlers.py`
2. Restore uniqueness checks:
   ```python
   c.execute("SELECT 1 FROM tweets WHERE tweet_id = ?", (tweet_id,))
   if c.fetchone():
       await update.message.reply_text("❌ This link has already been submitted.")
       return
   ```
3. Consider adding rate limiting instead

---

## General Procedures

### Running All Tests
```bash
# Run all new tests
python3 -m pytest tests/test_scheduled_sends.py -v
python3 -m pytest tests/test_duplicate_links.py -v
python3 -m pytest tests/test_payment_verification.py -v

# Run all existing tests
python3 -m pytest tests/ -v
```

### Checking Logs
```bash
# View recent logs
tail -f bot.log
tail -f debug.log

# Search for specific events
grep "scheduled_send" bot.log
grep "Broadcast completed" bot.log
grep "NOTOK" bot.log
```

### Database Inspection
```bash
# Check scheduled sends
sqlite3 ./db/viralcore.db "SELECT * FROM scheduled_sends ORDER BY created_at DESC LIMIT 10;"

# Check recent submissions
sqlite3 ./db/tweets.db "SELECT * FROM tweets ORDER BY id DESC LIMIT 10;"
```

### Emergency Rollback
```bash
# 1. Stop the bot
pkill -f main_viral_core_bot.py

# 2. Restore from backup
cp ./db/backups/viralcore.db.backup_TIMESTAMP ./db/viralcore.db

# 3. Revert to previous code version
git checkout <previous-commit-hash>

# 4. Restart bot
python3 main_viral_core_bot.py
```

---

## Support Contacts

For issues or questions:
1. Check logs with correlation IDs
2. Review this runbook
3. Consult README.md for configuration
4. Contact development team with:
   - Correlation ID
   - Timestamp
   - Log excerpts
   - Steps to reproduce

---

## Changelog

### v2.3.0 (Current)
- ✅ Scheduled split-send behavior (30 min + 30 min)
- ✅ Admin broadcast with image support
- ✅ Groups.db persistence verification
- ✅ Duplicate link submission support
- 🔄 Payment NOTOK fixes (in progress)
