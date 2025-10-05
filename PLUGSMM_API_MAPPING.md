# Plugsmmservice API Mapping: Old → New

## Overview
This document maps the differences between the old Plugsmmservice integration and the new v2 API as documented in the provider's PHP example code.

## API Endpoint
- **Old**: `https://plugsmmservice.com/api/v2`
- **New**: `https://plugsmmservice.com/api/v2`
- **Status**: ✅ No change required

## Authentication
- **Old**: `key` parameter in POST body
- **New**: `key` parameter in POST body
- **Status**: ✅ No change required

## Request Format
- **Old**: POST with form-encoded data
- **New**: POST with form-encoded data (URL-encoded key=value pairs)
- **Status**: ✅ No change required

## Core Operations

### 1. Add Order (Boost Request)

#### Old Implementation
```python
payload = {
    "key": api_key,
    "action": "add",
    "service": service_id,
    "link": link,
    "quantity": quantity
}
```

#### New API Requirements
```python
payload = {
    "key": api_key,
    "action": "add",
    "service": service_id,
    "link": link,
    "quantity": quantity
}
```

**Additional optional parameters supported by new API:**
- `runs` (integer): For drip-feed campaigns
- `interval` (integer): Time between runs in minutes
- `comments` (string): Custom comments (newline separated)
- `usernames` (string): For mentions (comma or newline separated)
- `hashtags` (string): For mentions with hashtags
- `username` (string): For mentions of user followers
- `min`, `max` (integer): For subscriptions
- `posts` (integer): Number of old posts (subscriptions)
- `old_posts` (integer): Number of old posts (new subscription format)
- `delay` (integer): Delay for subscriptions
- `expiry` (string): Expiry date (subscriptions)
- `answer_number` (string): For polls
- `groups` (string): For group invites (newline separated)

**Status**: ⚠️ **Current implementation is compatible but doesn't use optional features**

### 2. Order Status

#### Old Implementation
Not explicitly implemented in current code (only add order is used)

#### New API
```python
# Single order status
{
    "key": api_key,
    "action": "status",
    "order": order_id
}

# Multiple orders status
{
    "key": api_key,
    "action": "status",
    "orders": "1,2,3"  # comma-separated
}
```

**Status**: ➕ **New feature to add**

### 3. Services List

#### New API
```python
{
    "key": api_key,
    "action": "services"
}
```

**Status**: ➕ **New feature to add**

### 4. Refill Operations

#### New API
```python
# Refill single order
{
    "key": api_key,
    "action": "refill",
    "order": order_id
}

# Refill multiple orders
{
    "key": api_key,
    "action": "refill",
    "orders": "1,2,3"  # comma-separated
}

# Refill status
{
    "key": api_key,
    "action": "refill_status",
    "refill": refill_id
}

# Multiple refill statuses
{
    "key": api_key,
    "action": "refill_status",
    "refills": "1,2,3"  # comma-separated
}
```

**Status**: ➕ **New features to add**

### 5. Cancel Orders

#### New API
```python
{
    "key": api_key,
    "action": "cancel",
    "orders": "1,2,3"  # comma-separated
}
```

**Status**: ➕ **New feature to add**

### 6. Balance Check

#### New API
```python
{
    "key": api_key,
    "action": "balance"
}
```

**Status**: ➕ **New feature to add**

## Response Format

### Success Response
- **Expected**: JSON object with order details
- **Example**: `{"order": 123, "status": "success"}`
- **Current handling**: Checks for absence of "error" field

### Error Response
- **Expected**: JSON object with "error" field
- **Example**: `{"error": "Not enough funds in the balance"}`
- **Current handling**: ✅ Properly handles error field

## Error Codes and Messages

### Known Error Messages (from provider)
1. **Insufficient Funds**: "Not enough funds in the balance"
2. **Invalid Service**: Service ID doesn't exist
3. **Invalid Key**: Authentication failed
4. **Rate Limiting**: Too many requests
5. **Active Order**: Duplicate order exists

**Current Error Mapping**: ✅ Already handles these cases

## Content-Type and Encoding

### Old Implementation
```python
async with session.post(provider.api_url, data=payload, ...)
```
- Uses aiohttp default: `application/x-www-form-urlencoded`

### New API Requirements
```php
curl_setopt($ch, CURLOPT_POSTFIELDS, join('&', $_post));
```
- Expects: `application/x-www-form-urlencoded` with manual encoding

**Status**: ⚠️ **Potential issue - need to verify encoding**

## Breaking Changes

### None Identified
The new API is **backwards compatible** with our current implementation for the "add" action.

## Additions Required

1. **URL Encoding**: Ensure proper URL encoding of parameters (PHP uses `urlencode`)
2. **Order Tracking**: Add ability to track order IDs returned from provider
3. **Status Checking**: Implement order status queries
4. **Balance Monitoring**: Implement balance check
5. **Extended Parameters**: Support optional parameters for different boost types

## Migration Strategy

### Phase 1: Fix Current Issues (Immediate)
- ✅ Verify URL encoding of parameters
- ✅ Update response parsing if needed
- ✅ Enhance error handling for provider-specific messages

### Phase 2: Add Monitoring (High Priority)
- ➕ Implement balance check endpoint
- ➕ Implement order status tracking
- ➕ Store provider order IDs in database

### Phase 3: Enhanced Features (Medium Priority)
- ➕ Support refill operations
- ➕ Support cancel operations
- ➕ Support drip-feed (runs/interval)

## Configuration Changes

### Environment Variables
- ✅ `PLUGSMMS_API_KEY` - Already configured
- ➕ `PLUGSMM_USE_NEW_API` - Feature toggle (default: true)
- ➕ `PLUGSMM_ENABLE_ORDER_TRACKING` - Enable status checks (default: true)

### Database Schema
- ➕ Add `provider_order_id` column to boost jobs table (for status tracking)
- ➕ Add `provider_response` JSON column (for debugging)

## Rollback Plan

1. **Toggle Feature Flag**: Set `PLUGSMM_USE_NEW_API=false`
2. **No Database Migration Required**: New columns are optional
3. **Backwards Compatible**: Old code paths remain unchanged

## Testing Requirements

### Unit Tests
- ✅ Test payload construction with URL encoding
- ✅ Test response parsing
- ✅ Test error classification
- ➕ Test status checking
- ➕ Test balance checking

### Integration Tests
- ✅ Test add order with mock provider
- ➕ Test order status query
- ➕ Test balance query
- ✅ Test error scenarios

## Risk Assessment

### Low Risk ✅
- Current "add" action is fully compatible
- No breaking changes in request format
- Error handling already robust

### Medium Risk ⚠️
- URL encoding might differ between Python and PHP
- Response format variations not documented
- Rate limiting specifics unknown

### Mitigation
- Add comprehensive logging for all requests/responses
- Implement feature toggle for gradual rollout
- Add correlation IDs to all provider calls
- Monitor circuit breaker metrics

## Success Criteria

- [ ] All existing boost requests continue to work
- [ ] Provider errors are properly classified and logged
- [ ] Admin notifications work for critical errors
- [ ] Order tracking implemented (Phase 2)
- [ ] Balance monitoring implemented (Phase 2)
- [ ] Zero downtime during migration
- [ ] Rollback capability verified
