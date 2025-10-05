# Likes Group Message Payload Templates

## Overview

This document defines the message payload structure for the Likes Group. These templates are implementation-agnostic and show the required fields and format.

## Message Format

All Likes Group messages use the following structure:

### Template

```
🎯 New Post - Likes Needed 🎯

🆔 ID: `{post_id}`
🔗 {content}

❤️ Likes Needed: `{likes_needed}`

🔍 Correlation ID: `{correlation_id}`
⏰ Timestamp: `{timestamp}`
```

### Field Definitions

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| `post_id` | string | Yes | Unique identifier for the post | `123456789` (Twitter) or hash of link (Telegram) |
| `content` | string | Yes | The post link or content to display | `https://x.com/user/status/123456789` |
| `likes_needed` | integer | Yes | Number of likes needed for this post | `50` |
| `correlation_id` | string | Yes | UUID for tracking and debugging | `abc-123-def-456-ghi-789` |
| `timestamp` | string | Yes | UTC timestamp when sent | `2025-10-05 15:30:00 UTC` |

## Examples

### Twitter/X Post Example

```
🎯 New Post - Likes Needed 🎯

🆔 ID: `1856789012345678901`
🔗 https://x.com/viralcore/status/1856789012345678901

❤️ Likes Needed: `75`

🔍 Correlation ID: `a1b2c3d4-e5f6-7890-1234-567890abcdef`
⏰ Timestamp: `2025-10-05 15:30:00 UTC`
```

**Derivation:**
- `post_id`: Extracted from Twitter URL (tweet ID)
- `content`: Full Twitter/X URL
- `likes_needed`: From user's tier (e.g., t3 → 75 likes)
- `correlation_id`: Generated UUID v4
- `timestamp`: Server time in UTC when message sent

### Telegram Post Example

```
🎯 New Post - Likes Needed 🎯

🆔 ID: `https://t.me/mychannel/456`
🔗 https://t.me/mychannel/456

❤️ Likes Needed: `25`

🔍 Correlation ID: `b2c3d4e5-f6a7-8901-2345-678901bcdefg`
⏰ Timestamp: `2025-10-05 16:45:00 UTC`
```

**Derivation:**
- `post_id`: The Telegram link itself (used as unique identifier)
- `content`: Full Telegram URL
- `likes_needed`: From user's plan quantity (reactions target)
- `correlation_id`: Generated UUID v4
- `timestamp`: Server time in UTC when message sent

## Comparison with Group 1 Messages

### Group 1 (Comments Group) Message

**Format:**
```
🚨 New Link Submission 🚨

👤 ID: `12345`
🔗 https://x.com/user/status/123456789

*Targets:*
  Comments: `5`
  Retweets: `10`
_This post is now in the queue_
```

**Key Differences:**
- Group 1 includes user ID, comments, and retweets metrics
- Group 1 does NOT include likes_needed
- Group 1 does NOT include correlation ID or timestamp
- Likes Group has a different emoji identifier (🎯 vs 🚨)

### Group 2 (Likes Group) Message

**Format:**
```
🎯 New Post - Likes Needed 🎯

🆔 ID: `123456789`
🔗 https://x.com/user/status/123456789

❤️ Likes Needed: `30`

🔍 Correlation ID: `abc-123-def`
⏰ Timestamp: `2025-10-05 15:30:00 UTC`
```

**Key Differences:**
- Likes Group includes post_id (not user_id)
- Likes Group has likes_needed (NOT comments/retweets)
- Likes Group includes correlation_id for tracking
- Likes Group includes UTC timestamp
- Likes Group does NOT include "in the queue" footer

## Tier-to-Likes Mapping

For reference, here's how `likes_needed` is derived from user tiers:

### Twitter/X Posts

| Tier | Likes Needed | Comments | Retweets | Views |
|------|--------------|----------|----------|-------|
| t1 | 30 | 5 | 10 | 2000 |
| t2 | 50 | 10 | 20 | 5000 |
| t3 | 75 | 15 | 30 | 7000 |
| t4 | 100 | 20 | 40 | 10000 |
| t5 | 150 | 30 | 60 | 15000 |
| custom | varies | varies | varies | varies |

**Example:** A user with tier `t3` submitting a Twitter post will generate a Likes Group message with `likes_needed: 75`.

### Telegram Posts

For Telegram posts, `likes_needed` is equal to the `quantity` field from the user's plan (target reactions).

**Example:** A user with 25 target reactions will generate a Likes Group message with `likes_needed: 25`.

## Implementation Notes

### Markdown Escaping

When using Telegram MarkdownV2 format:
- Special characters in URLs may be escaped: `https://x\.com/user/status/123`
- Backticks protect field values from markdown parsing
- Emojis do not need escaping

### Correlation ID Generation

Correlation IDs should be:
- Unique per message (UUID v4 recommended)
- Logged with the message for traceability
- Included in error logs for debugging

### Timestamp Format

- Always use UTC timezone
- ISO 8601-like format: `YYYY-MM-DD HH:MM:SS UTC`
- Generated at send time (not post creation time)

## Validation Rules

A valid Likes Group message must:
1. Include all 5 required fields (post_id, content, likes_needed, correlation_id, timestamp)
2. Have `likes_needed` as a positive integer
3. Have a valid correlation_id (UUID format recommended)
4. Have a timestamp in the specified format
5. Use the correct emoji identifier (🎯)

## Error Handling

If a field is missing or invalid:
- Log the error with correlation_id
- Increment `posts_failed_group2` metric
- Do NOT send incomplete message
- Do NOT block Group 1 send

## Future Enhancements

Potential additions to the payload (not in initial release):
- `user_id`: Submitter's user ID (for correlation with Group 1)
- `tier`: User's tier name (for admin context)
- `retry_count`: Number of send attempts (for debugging)
- `priority`: Priority level (for future prioritization)

## Sample JSON Representation

For systems that need structured data:

```json
{
  "post_id": "1856789012345678901",
  "content": "https://x.com/viralcore/status/1856789012345678901",
  "likes_needed": 75,
  "correlation_id": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
  "timestamp": "2025-10-05T15:30:00Z",
  "post_type": "twitter"
}
```

**Note:** This JSON is for reference only. The actual Telegram message uses the formatted text template shown above.
