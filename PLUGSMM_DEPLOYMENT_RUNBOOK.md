# Plugsmmservice API Update - Deployment Runbook

## Overview

This runbook describes how to deploy, test, monitor, and rollback the updated Plugsmmservice integration.

## Pre-Deployment Checklist

- [ ] Review `PLUGSMM_API_MAPPING.md` for API changes
- [ ] Verify `PLUGSMMS_API_KEY` is set in production environment
- [ ] Backup production database: `cp viralcore.db viralcore.db.backup_$(date +%Y%m%d_%H%M%S)`
- [ ] Review recent provider errors in logs
- [ ] Ensure admin notification channel is active
- [ ] Verify monitoring/alerting is functional

## Configuration

### Environment Variables

#### Required
- `PLUGSMMS_API_KEY` - Your Plugsmm provider API key

#### Optional (Feature Toggles)
- `PLUGSMM_USE_NEW_API=true` - Enable new adapter (default: true)
- `PLUGSMM_ENABLE_ORDER_TRACKING=true` - Enable order tracking (default: true)

### Feature Toggle Strategy

The integration uses a feature flag for gradual rollout:

```bash
# Enable new API (default)
PLUGSMM_USE_NEW_API=true

# Disable new API (rollback to legacy)
PLUGSMM_USE_NEW_API=false
```

## Staging Deployment

### Step 1: Deploy to Staging

```bash
# Navigate to repository
cd /home/runner/work/viralcore/viralcore

# Pull latest changes
git pull origin main

# Install/update dependencies (if needed)
pip3 install -r requirements.txt

# Set environment variables for staging
export PLUGSMM_USE_NEW_API=true
export PLUGSMMS_API_KEY="your_staging_api_key"

# Restart the bot
./scripts/restart_bot.sh  # or your deployment script
```

### Step 2: Verify Staging

```bash
# Test 1: Run adapter tests
python3 -m unittest tests.test_plugsmm_adapter -v

# Test 2: Check bot startup
tail -f logs/bot.log | grep -i "plugsmm"

# Test 3: Trigger a test boost request
# Use the admin panel or Telegram bot interface
# Expected: Boost request should succeed with proper logging

# Test 4: Check provider response logging
grep "Plugsmm API" logs/bot.log | tail -20
```

### Step 3: Test Scenarios

#### Scenario 1: Successful Boost
```
Action: Create a boost request (100 views)
Expected: 
  - Order submitted successfully
  - Provider order ID returned
  - Logs show "Plugsmm API success"
  - User receives confirmation
```

#### Scenario 2: Insufficient Funds
```
Action: Create a boost with low balance
Expected:
  - Error properly classified as INSUFFICIENT_FUNDS
  - Admin notification sent
  - User receives generic "service unavailable" message
  - No provider internals leaked
```

#### Scenario 3: Invalid Service ID
```
Action: Attempt boost with wrong service_id
Expected:
  - Error classified as PERMANENT
  - Not retried
  - Admin notification sent
  - Logged for investigation
```

#### Scenario 4: Network Error
```
Action: Simulate network timeout (disconnect from API)
Expected:
  - Error classified as TRANSIENT
  - Retry with exponential backoff
  - Circuit breaker may activate after threshold
  - Logs show retry attempts
```

## Production Deployment

### Step 1: Enable Monitoring

```bash
# Before deployment, ensure monitoring is active
# Check these metrics are being collected:
# - provider_requests_count
# - provider_requests_failed
# - provider_requests_success
# - provider_avg_latency
# - circuit_breaker_state
```

### Step 2: Deploy with Feature Flag

```bash
# Set feature flag to ENABLED
export PLUGSMM_USE_NEW_API=true

# Restart bot
systemctl restart viralcore-bot  # or your service name

# Or if using a script:
./scripts/restart_bot.sh
```

### Step 3: Monitor Deployment

```bash
# Monitor logs for 5-10 minutes
tail -f logs/bot.log | grep -E "(Plugsmm|Provider API)"

# Watch for:
# ✅ "Plugsmm API success" messages
# ✅ Proper error classification
# ❌ Unhandled exceptions
# ❌ "Invalid JSON response"
# ❌ Repeated "HTTP 500" errors
```

### Step 4: Verify Health

```bash
# Check recent provider calls
grep "Plugsmm API request" logs/bot.log | tail -50

# Check error rate
total=$(grep "Plugsmm API request" logs/bot.log | wc -l)
errors=$(grep "Plugsmm API.*error" logs/bot.log | wc -l)
echo "Error rate: $errors / $total"

# Error rate should be < 5% under normal conditions
```

## Monitoring Checklist

### Key Metrics to Watch

1. **Request Success Rate**
   - Target: > 95%
   - Alert if: < 90% for 5 minutes

2. **Average Latency**
   - Target: < 2 seconds
   - Alert if: > 5 seconds for 5 minutes

3. **Circuit Breaker State**
   - Should be: CLOSED
   - Alert if: OPEN for > 2 minutes

4. **Error Distribution**
   - TRANSIENT errors should auto-retry
   - PERMANENT errors should not retry
   - RATE_LIMITED should back off

### Log Patterns to Monitor

```bash
# Success pattern
grep "Plugsmm API success" logs/bot.log

# Error patterns
grep "Plugsmm API.*HTTP 500" logs/bot.log  # Server errors
grep "Plugsmm API.*timeout" logs/bot.log   # Timeouts
grep "Invalid JSON response" logs/bot.log  # Parse errors
grep "Circuit breaker open" logs/bot.log   # Circuit breaker
```

## Troubleshooting

### Issue 1: All Requests Failing

**Symptoms:**
- All Plugsmm requests return errors
- Logs show "HTTP 401" or "Invalid API key"

**Diagnosis:**
```bash
# Check API key is set
echo $PLUGSMMS_API_KEY | head -c 10

# Check adapter is using correct key
grep "api_key" logs/bot.log | grep plugsmm
```

**Resolution:**
1. Verify `PLUGSMMS_API_KEY` in environment
2. Check key hasn't expired with provider
3. Test key with provider's test endpoint
4. If key is invalid, update and restart

### Issue 2: Intermittent Timeouts

**Symptoms:**
- Requests sometimes succeed, sometimes timeout
- Logs show "Request timeout after Xs"

**Diagnosis:**
```bash
# Check timeout frequency
grep "timeout" logs/bot.log | grep Plugsmm | wc -l

# Check network latency
ping plugsmmservice.com
curl -w "@curl-format.txt" -o /dev/null -s https://plugsmmservice.com/api/v2
```

**Resolution:**
1. Check network connectivity to provider
2. Increase timeout if needed (default: 30s)
3. Contact provider if consistent timeouts
4. Consider using alternative provider temporarily

### Issue 3: Circuit Breaker Stuck Open

**Symptoms:**
- Circuit breaker remains OPEN
- All requests skipped
- Logs show "Circuit breaker open - skipping provider API call"

**Diagnosis:**
```bash
# Check circuit breaker state
grep "Circuit breaker" logs/bot.log | tail -20

# Check recent failures
grep "record_failure" logs/bot.log | tail -20
```

**Resolution:**
1. Wait for recovery timeout (default: 60s)
2. If persistent, investigate root cause of failures
3. Restart bot to reset circuit breaker if needed
4. Consider increasing failure threshold if too sensitive

### Issue 4: Invalid JSON Responses

**Symptoms:**
- Logs show "Invalid JSON response"
- Provider returns HTML or malformed JSON

**Diagnosis:**
```bash
# Check response previews in logs
grep "response_preview" logs/bot.log | grep Plugsmm | tail -10

# Check HTTP status codes
grep "status_code" logs/bot.log | grep Plugsmm | tail -20
```

**Resolution:**
1. Provider API may be down - check provider status page
2. Verify API endpoint URL is correct
3. Check if provider changed response format
4. Enable rollback if issue persists

### Issue 5: Provider API Errors Not Classified

**Symptoms:**
- Errors classified as "Unknown error"
- Not properly retried or handled

**Diagnosis:**
```bash
# Check unclassified errors
grep "Unknown error" logs/bot.log | tail -20

# Get full error messages
grep "Plugsmm API.*error" logs/bot.log | tail -20
```

**Resolution:**
1. Review new error patterns
2. Update `_classify_plugsmm_error` method
3. Add new error patterns to classification logic
4. Deploy updated classification

## Rollback Procedure

### Quick Rollback (Feature Flag)

**No code changes needed - just disable feature flag:**

```bash
# Disable new API
export PLUGSMM_USE_NEW_API=false

# Restart bot
systemctl restart viralcore-bot
# or
./scripts/restart_bot.sh

# Verify legacy adapter is used
grep "using legacy adapter" logs/bot.log
```

**Recovery time: < 1 minute**

### Full Rollback (Code Revert)

**If feature flag doesn't work:**

```bash
# 1. Stop the bot
systemctl stop viralcore-bot

# 2. Revert to previous commit
git log --oneline | head -10  # Find previous commit
git revert HEAD  # or git reset --hard <commit-hash>

# 3. Restart bot
systemctl start viralcore-bot

# 4. Verify rollback
tail -f logs/bot.log | grep -i plugsmm
```

**Recovery time: 2-5 minutes**

### Database Rollback

**Not required - no database schema changes made.**

If needed to restore from backup:
```bash
# Stop bot
systemctl stop viralcore-bot

# Restore database
cp viralcore.db.backup_YYYYMMDD_HHMMSS viralcore.db

# Restart bot
systemctl start viralcore-bot
```

## Post-Deployment Verification

### Success Criteria

- [ ] All existing boost requests continue to work
- [ ] Error rate < 5%
- [ ] Average latency < 2 seconds
- [ ] Circuit breaker remains CLOSED
- [ ] Admin notifications work for critical errors
- [ ] Provider errors properly classified and logged
- [ ] No provider internals leaked to users
- [ ] Rollback capability verified

### Verification Commands

```bash
# Check success rate (last 100 requests)
success=$(grep "Plugsmm API success" logs/bot.log | tail -100 | wc -l)
total=$(grep "Plugsmm API request" logs/bot.log | tail -100 | wc -l)
echo "Success rate: $success / $total"

# Check error distribution
echo "Error types:"
grep "error_type=" logs/bot.log | grep -oP 'error_type=\K\w+' | sort | uniq -c

# Check circuit breaker state
grep "Circuit breaker" logs/bot.log | tail -1

# Check admin notifications
grep "Admin notification sent" logs/bot.log | tail -10
```

## Known Issues and Limitations

### Current Limitations

1. **Order Tracking**: Partially implemented
   - Order IDs are returned but not persisted
   - Status checking available but not automated
   - Future enhancement: Add background job to track order status

2. **Refill Operations**: Not integrated
   - API methods available but not wired to UI
   - Future enhancement: Add admin command for refills

3. **Balance Monitoring**: Not automated
   - Balance check API available
   - Future enhancement: Periodic balance checks with alerts

### Expected Behavior

1. **Encoding Changes**: The new adapter uses PHP-compatible URL encoding
   - This may fix encoding issues with special characters in links
   - No visible change for most users

2. **Error Messages**: More specific error classification
   - Users still see generic messages (security)
   - Admins see detailed error info in logs/notifications

3. **Retry Logic**: Unchanged
   - Same retry/backoff strategy
   - Circuit breaker thresholds unchanged

## Support and Escalation

### First Response

1. Check logs: `tail -100 logs/bot.log`
2. Check metrics: error rate, latency, circuit breaker
3. Try common troubleshooting steps above

### Escalation Path

If issue persists:
1. Enable rollback using feature flag
2. Notify development team with:
   - Error logs (last 100 lines)
   - Metrics (success rate, error types)
   - Steps to reproduce
3. File incident report with correlation IDs

### Emergency Contacts

- **Development Team**: [Your team contact]
- **Provider Support**: https://plugsmmservice.com/support
- **Admin Notifications**: Telegram group configured in env

## Next Steps (Future Enhancements)

### Phase 2: Order Tracking (Recommended)

```bash
# 1. Add database migration for order tracking
python3 scripts/migrate_database.py --add-column provider_order_id

# 2. Enable order tracking
export PLUGSMM_ENABLE_ORDER_TRACKING=true

# 3. Add background job for status checks
# (Implementation TBD)
```

### Phase 3: Advanced Features

- [ ] Automated balance monitoring
- [ ] Refill operations in admin panel
- [ ] Drip-feed campaign support
- [ ] Multi-provider load balancing

## Appendix

### API Endpoint Reference

- **Production**: `https://plugsmmservice.com/api/v2`
- **Staging**: Use production endpoint with test API key

### Configuration Files

- Environment: `.env` (not in git)
- Provider config: `settings/provider_config.json`
- Service mappings: Database table `boosting_service_providers`

### Related Documentation

- `PLUGSMM_API_MAPPING.md` - API changes and mapping
- `README.md` - General setup and configuration
- `DEPLOYMENT.md` - General deployment guide
- `WITHDRAWAL_TESTING_RUNBOOK.md` - Example runbook format

---

**Document Version**: 1.0
**Last Updated**: $(date +%Y-%m-%d)
**Author**: Copilot Agent
