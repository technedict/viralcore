# Deployment Guide - ViralCore v2.1.0

## Service ID Leak Fix & Enhanced Security Update

This deployment guide covers the rollout of critical security fixes and enhanced features.

## Pre-Deployment Checklist

### 1. System Health Check
```bash
# Check current system status
python3 scripts/check_serviceid_mismatches.py --verbose --output pre_deploy_check.csv

# Backup current database
python3 scripts/migrate_database.py --backup

# Verify current balance consistency
python3 scripts/reconcile_balances.py --verbose
```

### 2. Dependencies
Ensure these packages are installed:
```bash
pip install python-dotenv aiohttp python-telegram-bot requests
```

### 3. Configuration Review
- Verify all provider API keys are current in `.env`
- Check `settings/provider_config.json` exists and contains valid active provider
- Confirm admin user IDs are correctly configured

## Deployment Steps

### 1. Stop Current Bot
```bash
# Stop the bot service (adapt to your setup)
sudo systemctl stop viralcore-bot
# OR
pkill -f main_viral_core_bot.py
```

### 2. Deploy Code
```bash
git checkout fix/boost-provider-serviceid-leak-refactor-logging-markdown
git pull origin fix/boost-provider-serviceid-leak-refactor-logging-markdown
```

### 3. Initialize New Database Tables
```bash
python3 -c "
from utils.job_system import job_system
job_system._init_database()
print('✅ Job system database initialized')
"
```

### 4. Test Core Functionality
```bash
# Test logging system
python3 -c "
from utils.logging import setup_logging, get_logger
setup_logging()
logger = get_logger('test')
logger.info('INFO test - should go to debug.log and console')
logger.warning('WARNING test - should go to bot.log and console')
print('✅ Logging system working')
"

# Test job system
python3 tests/test_job_system.py

# Test provider snapshot system
python3 -c "
import asyncio
from utils.job_system import job_system
from utils.boost_provider_utils import get_active_provider

async def test():
    job = await job_system.create_boost_job('https://example.com/test', 10, 50)
    print(f'✅ Job created: {job.job_id}')
    print(f'✅ Provider snapshot: {job.provider_snapshot.provider_name}')

asyncio.run(test())
"
```

### 5. Start Bot
```bash
# Start the bot service
sudo systemctl start viralcore-bot
# OR
nohup python3 main_viral_core_bot.py > /dev/null 2>&1 &
```

## Post-Deployment Validation

### 1. Immediate Checks (0-5 minutes)
```bash
# Check bot is running
ps aux | grep main_viral_core_bot.py

# Verify logging is working correctly
tail -f bot.log    # Should contain only WARNING/ERROR messages
tail -f debug.log  # Should contain INFO/DEBUG messages

# Check for startup errors
tail -20 bot.log | grep ERROR
```

### 2. Service ID Leak Prevention (5-15 minutes)
```bash
# Test provider switching doesn't affect existing jobs
python3 -c "
import asyncio
from utils.job_system import job_system
from utils.boost_provider_utils import get_active_provider, ProviderConfig

async def test_no_leak():
    # Create job with current provider
    original_provider = get_active_provider()
    job = await job_system.create_boost_job('https://example.com/leak_test', 25, 100)
    
    print(f'Job created with provider: {job.provider_snapshot.provider_name}')
    print(f'Original service IDs: {job.provider_snapshot.view_service_id}, {job.provider_snapshot.like_service_id}')
    
    # Switch provider
    providers = ['smmflare', 'plugsmms', 'smmstone'] 
    new_provider = [p for p in providers if p != original_provider.name][0]
    ProviderConfig.set_active_provider_name(new_provider)
    
    # Verify job still uses original snapshot
    retrieved = job_system.get_job(job.job_id)
    assert retrieved.provider_snapshot.provider_name == original_provider.name
    
    # Reset provider
    ProviderConfig.set_active_provider_name(original_provider.name)
    print('✅ Service ID leak prevention working')

asyncio.run(test_no_leak())
"
```

### 3. Message Template Validation (15-30 minutes)  
Test message rendering in a test chat:
```bash
# Test MarkdownV2 templates don't cause parse errors
python3 -c "
from utils.messaging import render_markdown_v2, TEMPLATES

# Test all templates render without errors
for name, template in TEMPLATES.items():
    try:
        rendered = render_markdown_v2(template, 
            provider_name='test', 
            link='https://example.com',
            amount='100.50',
            currency='USD',
            balance='500.00'
        )
        print(f'✅ Template {name} renders correctly')
    except Exception as e:
        print(f'❌ Template {name} failed: {e}')
"
```

### 4. System Health Monitoring (30+ minutes)
```bash
# Run reconciliation check
python3 scripts/check_serviceid_mismatches.py --verbose --output post_deploy_check.csv

# Monitor for any new service ID mismatches
diff pre_deploy_check.csv post_deploy_check.csv

# Check for any parse errors in logs
grep -i "parse.*error" bot.log debug.log || echo "✅ No parse errors found"

# Monitor circuit breaker status
grep -i "circuit.*breaker" bot.log debug.log || echo "✅ No circuit breaker issues"
```

## Rollback Procedure

If issues are detected, rollback immediately:

### 1. Stop New Bot
```bash
sudo systemctl stop viralcore-bot
# OR
pkill -f main_viral_core_bot.py
```

### 2. Restore Previous Code
```bash
git checkout main  # or previous stable branch
```

### 3. Restore Database (if needed)
```bash
# Find most recent backup
ls -la *.db.backup_* | tail -1

# Restore (replace TIMESTAMP with actual timestamp)
cp viralcore.db.backup_TIMESTAMP viralcore.db
```

### 4. Restart Previous Version
```bash
sudo systemctl start viralcore-bot
```

## Monitoring & Alerting

### Key Metrics to Monitor
- Service ID mismatch count (should be 0)
- MarkdownV2 parse error rate (should be 0) 
- Provider API error rates
- Circuit breaker activations
- Job creation vs completion rates

### Log Monitoring
```bash
# Monitor for critical errors
tail -f bot.log | grep ERROR

# Monitor for service ID issues
tail -f bot.log debug.log | grep -i "service.*id\|provider"

# Monitor for message parse errors  
tail -f bot.log debug.log | grep -i "parse.*error"
```

### Alert Conditions
Set up alerts for:
- More than 5 service ID mismatches per hour
- More than 10 MarkdownV2 parse errors per hour
- Circuit breaker activation
- Provider API error rate > 20%
- Job failure rate > 10%

## Feature Flags

The new enhanced boost service can be disabled if needed:
```python
# In utils/boost_utils.py, modify BoostManager.__init__()
self._use_enhanced = False  # Force disable enhanced service
```

## Support Contacts

For deployment issues:
1. Check logs with correlation IDs for API errors
2. Run reconciliation scripts to identify data issues  
3. Use export tools to backup data before major changes
4. Contact development team with specific error correlation IDs

## Success Criteria

Deployment is successful when:
- ✅ Bot starts without errors
- ✅ Logging routes to correct files (WARNING/ERROR → bot.log, INFO/DEBUG → debug.log)
- ✅ Service ID leak prevention test passes
- ✅ Message templates render without parse errors
- ✅ Provider switching works without affecting existing jobs
- ✅ No increase in service ID mismatches post-deployment
- ✅ All reconciliation scripts run successfully