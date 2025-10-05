# Plugsmm Integration - Quick Reference

## ✅ Status: Ready for Deployment

All verification checks passed. The integration is backwards compatible and ready for staging/production deployment.

## Quick Start

### 1. Set Environment Variable
```bash
export PLUGSMMS_API_KEY="your_actual_api_key_here"
export PLUGSMM_USE_NEW_API=true
```

### 2. Verify Installation
```bash
python3 scripts/verify_plugsmm_integration.py
```

### 3. Run Tests
```bash
# Unit tests
python3 -m unittest tests.test_plugsmm_adapter -v

# All tests
python3 -m unittest discover -s tests -p "test_plugsmm*.py" -v
```

### 4. Deploy
```bash
# Restart your bot
systemctl restart viralcore-bot
# or
./scripts/restart_bot.sh
```

### 5. Monitor
```bash
# Watch for Plugsmm API calls
tail -f logs/bot.log | grep -i "Plugsmm"

# Check success rate
grep "Plugsmm API" logs/bot.log | grep -c "success"
```

## Emergency Rollback

If issues occur, rollback in < 1 minute:

```bash
# Disable new adapter
export PLUGSMM_USE_NEW_API=false

# Restart bot
systemctl restart viralcore-bot
```

## Key Files

| File | Purpose |
|------|---------|
| `utils/plugsmm_adapter.py` | New adapter implementation |
| `utils/boost_utils_enhanced.py` | Integration with boost service |
| `PLUGSMM_API_MAPPING.md` | API changes documentation |
| `PLUGSMM_DEPLOYMENT_RUNBOOK.md` | Detailed deployment guide |
| `PLUGSMM_PR_SUMMARY.md` | Complete PR summary |
| `tests/test_plugsmm_adapter.py` | Unit tests (16 tests) |
| `scripts/verify_plugsmm_integration.py` | Verification script |

## Feature Flags

| Variable | Default | Purpose |
|----------|---------|---------|
| `PLUGSMM_USE_NEW_API` | `true` | Enable new adapter |
| `PLUGSMM_ENABLE_ORDER_TRACKING` | `true` | Enable order tracking |

## Common Commands

```bash
# Check configuration
echo $PLUGSMM_USE_NEW_API
echo $PLUGSMMS_API_KEY | head -c 10

# Verify integration
python3 scripts/verify_plugsmm_integration.py

# Run unit tests
python3 -m unittest tests.test_plugsmm_adapter

# Monitor logs
tail -f logs/bot.log | grep -E "(Plugsmm|Provider API)"

# Check error rate
total=$(grep "Plugsmm API request" logs/bot.log | wc -l)
errors=$(grep "Plugsmm API.*error" logs/bot.log | wc -l)
echo "Error rate: $errors / $total"

# Check circuit breaker
grep "Circuit breaker" logs/bot.log | tail -5
```

## Test Results

### Unit Tests
- ✅ 16/16 tests passing
- Coverage: All adapter methods
- Errors: All error scenarios tested

### Integration Tests
- ✅ Mock provider implemented
- ✅ End-to-end flows tested
- ✅ Error scenarios validated

### Verification
- ✅ 8/8 checks passed
- Configuration ✓
- Adapter creation ✓
- Feature flags ✓
- Payload construction ✓
- Error classification ✓
- Backwards compatibility ✓
- Documentation ✓
- Test coverage ✓

## What Changed

### New Features
✅ PHP-compatible URL encoding
✅ Comprehensive error classification
✅ Order status tracking (API ready)
✅ Balance checking (API ready)
✅ Refill operations (API ready)
✅ Cancel operations (API ready)
✅ Detailed logging with correlation IDs
✅ Feature flag for rollback

### What Stayed the Same
✅ API endpoint (`https://plugsmmservice.com/api/v2`)
✅ Authentication method (`key` parameter)
✅ Core add order functionality
✅ Internal API signatures
✅ Other providers (smmflare, smmstone)
✅ Error handling and retry logic
✅ Circuit breaker protection

## Support

### Documentation
- [API Mapping](PLUGSMM_API_MAPPING.md) - API changes reference
- [Deployment Runbook](PLUGSMM_DEPLOYMENT_RUNBOOK.md) - Detailed deployment guide
- [PR Summary](PLUGSMM_PR_SUMMARY.md) - Complete overview
- [README](README.md#plugsmmservice-integration) - Configuration guide

### Troubleshooting
1. Check logs: `tail -f logs/bot.log | grep Plugsmm`
2. Verify config: `python3 scripts/verify_plugsmm_integration.py`
3. Check feature flag: `echo $PLUGSMM_USE_NEW_API`
4. Review runbook: `PLUGSMM_DEPLOYMENT_RUNBOOK.md`

### Emergency Rollback
```bash
export PLUGSMM_USE_NEW_API=false
systemctl restart viralcore-bot
```

## Next Steps

1. **Staging Deployment**
   - Deploy with `PLUGSMM_USE_NEW_API=true`
   - Test boost requests
   - Monitor for 1-2 hours
   - Verify error handling

2. **Production Canary**
   - Deploy to production
   - Monitor closely for 1 hour
   - Check metrics (success rate, latency)
   - Verify admin notifications

3. **Full Rollout**
   - Monitor for 24 hours
   - Document any issues
   - Plan Phase 2 features

4. **Phase 2 (Future)**
   - Automated order tracking
   - Background balance monitoring
   - Refill automation
   - Drip-feed campaigns

## Metrics to Monitor

### Success Criteria
- ✅ Request success rate > 95%
- ✅ Average latency < 2 seconds
- ✅ Circuit breaker: CLOSED
- ✅ No provider internals leaked to users

### Red Flags
- ❌ Error rate > 10%
- ❌ Circuit breaker: OPEN for > 2 minutes
- ❌ HTTP 401/403 errors (auth issue)
- ❌ All requests failing

## Contact

- **Development**: Review PLUGSMM_PR_SUMMARY.md
- **Deployment**: Follow PLUGSMM_DEPLOYMENT_RUNBOOK.md
- **Provider Issues**: https://plugsmmservice.com/support

---

**Ready to Deploy** ✅
**All Checks Passed** ✅
**Backwards Compatible** ✅
**Rollback Ready** ✅
