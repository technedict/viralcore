# Likes Group Feature - Runbook

## Overview

The Likes Group is a second independent admin group that receives every post with a `likes_needed` metric. It operates independently from Group 1 (the existing comment groups) and is exempt from rotation logic.

## Configuration

### Environment Variables

Add these to your `.env` file:

```bash
# Enable/disable Likes Group (default: false)
ADMIN_LIKES_GROUP_ENABLED=true

# Telegram chat ID for Likes Group (required when enabled)
ADMIN_LIKES_GROUP_CHAT_ID=-1001234567890
```

### Requirements

1. A dedicated Telegram group for likes tracking
2. The bot must be added to the group with send message permissions
3. Get the group chat ID (usually a negative number starting with -100)

## Manual Verification Steps

### 1. Enable Likes Group in Staging

```bash
# In your .env file
ADMIN_LIKES_GROUP_ENABLED=true
ADMIN_LIKES_GROUP_CHAT_ID=-1001234567890  # Replace with your group ID

# Restart the bot
python3 main_viral_core_bot.py
```

### 2. Create a Test Post (Twitter/X)

1. Send a Twitter link to the bot in a private chat
2. Follow the prompts to submit the post
3. Verify that:
   - ✅ Group 1 receives the post with comments/retweets metrics (unchanged behavior)
   - ✅ Likes Group receives the post with `likes_needed` metric
   - ✅ Both messages are sent successfully

**Expected Likes Group Message Format:**
```
🎯 New Post - Likes Needed 🎯

🆔 ID: `123456789`
🔗 https://x.com/user/status/123456789

❤️ Likes Needed: `50`

🔍 Correlation ID: `abc-123-def-456`
⏰ Timestamp: `2025-10-05 15:30:00 UTC`
```

### 3. Verify Rotation Exclusion

1. Submit multiple posts in sequence (5-10 posts)
2. Observe Group 1 behavior:
   - Should rotate through COMMENT_GROUP_IDS as before
   - Only selected groups receive posts based on quantity/rotation
3. Observe Likes Group behavior:
   - Should receive EVERY post
   - No rotation logic applies
   - All posts sent immediately

### 4. Test Failure Handling

#### Simulate Likes Group Failure

```bash
# Temporarily set invalid chat ID
ADMIN_LIKES_GROUP_CHAT_ID=-999999999

# Submit a test post
# Expected: Group 1 send succeeds, Likes Group fails gracefully
```

Check logs for:
```
[LikesGroup] Failed to send post ... to Likes Group: ...
```

**Verify:**
- ✅ Group 1 still received the post
- ✅ Likes Group failure logged but didn't crash
- ✅ Metrics show `posts_failed_group2` incremented

#### Test Network Timeout

1. Temporarily block outgoing connections to Telegram API
2. Submit a post
3. Verify Group 1 still succeeds

### 5. Test Deduplication

1. Submit the same post twice (if possible in test environment)
2. Verify Likes Group receives it only once
3. Check logs for deduplication message:
   ```
   [LikesGroup] Duplicate post {post_id}, skipping send
   ```

### 6. Verify Metrics

Access metrics (if exposed via admin interface):

```python
from utils.likes_group import get_metrics

metrics = get_metrics()
print(metrics)
# Expected output:
# {
#   'posts_sent_group1': 10,
#   'posts_sent_group2': 10,
#   'posts_failed_group2': 0,
#   'posts_deduped_group2': 0
# }
```

## Monitoring

### Log Messages to Monitor

**Success:**
```
[LikesGroup] Successfully sent post to Likes Group
  post_id: 123456789
  likes_needed: 50
  correlation_id: abc-123-def
  status: success
```

**Failure:**
```
[LikesGroup] Failed to send post ... to Likes Group: [error details]
  status: failed
  error: Network timeout
```

**Deduplication:**
```
[LikesGroup] Duplicate post 123456789, skipping send
```

### Metrics to Track

- `posts_sent_group1`: Total posts sent to Group 1 (should match pre-feature count)
- `posts_sent_group2`: Total posts sent to Likes Group
- `posts_failed_group2`: Failed sends to Likes Group
- `posts_deduped_group2`: Duplicate posts rejected

### Expected Ratios

- `posts_sent_group2` ≈ `posts_sent_group1` (should receive every post)
- `posts_failed_group2` should be low (<1% in production)
- `posts_deduped_group2` should be 0 under normal operation

## Troubleshooting

### Likes Group Not Receiving Posts

**Check:**
1. `ADMIN_LIKES_GROUP_ENABLED=true` in `.env`
2. `ADMIN_LIKES_GROUP_CHAT_ID` is set correctly
3. Bot has send message permissions in the group
4. Group chat ID is correct (use `/start` in group to verify)

**Verify:**
```bash
# In Python shell
from settings.bot_settings import ADMIN_LIKES_GROUP_ENABLED, ADMIN_LIKES_GROUP_CHAT_ID
print(f"Enabled: {ADMIN_LIKES_GROUP_ENABLED}")
print(f"Chat ID: {ADMIN_LIKES_GROUP_CHAT_ID}")
```

### High Failure Rate

**Possible causes:**
- Network issues with Telegram API
- Invalid chat ID
- Bot removed from group
- Bot lacks send permissions

**Check logs for specific error:**
```bash
grep "LikesGroup.*Failed" bot.log | tail -20
```

### Duplicate Posts

If posts are being duplicated:
1. Check if multiple bot instances are running
2. Verify deduplication cache is working:
   ```python
   from utils.likes_group import _sent_posts_cache
   print(len(_sent_posts_cache))  # Should have recent posts
   ```

## Emergency Procedures

### Disable Likes Group

**Quick disable (no deploy):**
```bash
# Set in .env
ADMIN_LIKES_GROUP_ENABLED=false

# Restart bot
systemctl restart viralcore  # or your restart command
```

**Verify disabled:**
```bash
grep "LikesGroup.*Feature disabled" bot.log
```

### Clear Deduplication Cache

If needed to reset dedup cache (use with caution):
```python
from utils.likes_group import clear_dedup_cache
clear_dedup_cache()
```

### Rollback Steps

1. **Disable feature:**
   ```bash
   ADMIN_LIKES_GROUP_ENABLED=false
   ```

2. **Restart service:**
   ```bash
   systemctl restart viralcore
   ```

3. **Verify:**
   - Group 1 still works normally
   - No Likes Group sends happening
   - No errors in logs

4. **If needed, revert code:**
   ```bash
   git revert <commit-hash>
   git push origin main
   ```

## Testing Checklist

Before deploying to production:

- [ ] Staging environment configured correctly
- [ ] Test Twitter post sends to both groups
- [ ] Test Telegram post sends to both groups
- [ ] Verify Group 1 behavior unchanged
- [ ] Verify Likes Group receives every post (no rotation)
- [ ] Test failure handling (Group 1 unaffected)
- [ ] Test deduplication works
- [ ] Verify metrics tracking
- [ ] Test emergency disable procedure
- [ ] Test rollback procedure
- [ ] Load test with multiple posts (10+)
- [ ] Verify logs are clean and informative

## Contact

For issues or questions about this feature:
- Check logs: `tail -f bot.log | grep LikesGroup`
- Review metrics via admin interface
- Contact: [your team contact info]
