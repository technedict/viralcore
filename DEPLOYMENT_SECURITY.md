# Security-Focused Deployment Guide

## 🚨 **CRITICAL: Security Fixes Deployment**

This release contains **CRITICAL SECURITY FIXES** that require immediate attention.

### **Pre-Deployment Security Actions**

#### 1. **API Key Rotation (MANDATORY)**
All API keys were previously exposed in git history and must be rotated:

```bash
# Rotate these keys IMMEDIATELY:
- TELEGRAM_BOT_TOKEN (get new token from @BotFather)
- FLUTTERWAVE_API_KEY (rotate in Flutterwave dashboard)  
- BSC_API_KEY / SOL_API_KEY / TRX_GRID_API_KEY (rotate in provider dashboards)
- BITLY_ACCESS_TOKEN (rotate in Bitly account)
- All boost provider API keys (PLUGSMMS, SMMFLARE, SMMSTONE)
```

#### 2. **Environment Setup**
```bash
# DO NOT copy .env.backup to production - it contains exposed keys
# Instead, create new .env with rotated keys:

cp .env.example .env
# Manually populate .env with NEW rotated API keys
```

### **Deployment Steps**

#### **Step 1: Staging Deployment**
```bash
# 1. Deploy to staging
git checkout audit-refactor-security-backcompat
pip install -r requirements.txt

# 2. Configure with ROTATED keys
cp .env.example .env
# Edit .env with NEW API keys (not the old exposed ones)

# 3. Test critical functions
python -c "from utils.config import APIConfig; APIConfig.validate()"
python -c "from utils.messaging import safe_send; print('Messaging OK')"
python scripts/performance_audit.py

# 4. Run balance operations test
python test_balance_operations.py

# 5. Run messaging tests  
python tests/test_messaging.py
```

#### **Step 2: Production Deployment**
```bash
# 1. Stop bot service
sudo systemctl stop viralcore-bot

# 2. Backup current deployment
cp -r /opt/viralcore /opt/viralcore.backup.$(date +%Y%m%d_%H%M%S)

# 3. Deploy new version
git checkout audit-refactor-security-backcompat
pip install -r requirements.txt

# 4. Configure with NEW rotated keys
cp .env.example .env
# Populate with ROTATED API keys

# 5. Verify configuration
python -c "from utils.config import APIConfig; APIConfig.validate()"

# 6. Test database migrations (indexes are added automatically)
python -c "from utils.db_utils import init_main_db; init_main_db()"

# 7. Start bot service
sudo systemctl start viralcore-bot

# 8. Monitor logs
tail -f bot.log
tail -f debug.log
```

### **Post-Deployment Verification**

#### **1. Security Verification**
```bash
# Ensure no secrets in logs
grep -i "token\|key\|secret\|password" bot.log | grep -v "REDACTED"
# Should return no results

# Verify structured logging
head -5 bot.log
# Should show JSON formatted logs

# Check log file separation
wc -l bot.log debug.log
# bot.log should be smaller (WARNING/ERROR only)
```

#### **2. Functionality Tests**
```bash
# Test balance operations
python -c "
from utils.balance_operations import atomic_balance_update
result = atomic_balance_update(99999, 'affiliate', 0.01, 'test', 'deployment_test')
print(f'Balance test: {result}')
"

# Test messaging system
python -c "
from utils.messaging import render_markdown_v2
result = render_markdown_v2('Hello *{name}*!', name='test_user')
print(f'Messaging test: {result}')
"
```

#### **3. Performance Verification**
```bash
# Run performance audit
python scripts/performance_audit.py

# Check database indexes
sqlite3 viralcore.db ".schema" | grep -i index
# Should show new performance indexes
```

### **Monitoring & Alerts**

#### **Set up monitoring for:**
- API key usage (ensure old keys are not being used)
- Error rates in bot.log
- Database performance with new indexes
- Memory usage (should be stable or improved)

### **Rollback Procedure**

If issues are encountered:

#### **Quick Rollback**
```bash
# 1. Stop service
sudo systemctl stop viralcore-bot

# 2. Restore backup
rm -rf /opt/viralcore
mv /opt/viralcore.backup.YYYYMMDD_HHMMSS /opt/viralcore

# 3. Restore old configuration (with OLD keys - security risk!)
# Only for emergency rollback - ROTATE KEYS AGAIN ASAP

# 4. Start service
sudo systemctl start viralcore-bot
```

#### **Post-Rollback Actions**
- Investigate the issue in staging
- Keep API key rotation (don't revert to exposed keys)
- Plan fix deployment

### **Security Incident Response**

If API key compromise is suspected:

1. **Immediate Actions**:
   - Rotate all API keys immediately
   - Review access logs for suspicious activity
   - Monitor for unusual API usage patterns

2. **Investigation**:
   - Check git commit history for any remaining exposed secrets
   - Review server access logs
   - Audit all third-party service activities

3. **Communication**:
   - Document incident
   - Notify stakeholders of any potential data exposure
   - Update security procedures based on learnings

### **Success Criteria**

✅ Bot operational with new security fixes
✅ No API keys visible in logs (all show as REDACTED)  
✅ bot.log contains only WARNING/ERROR in JSON format
✅ All balance operations working with proper idempotency
✅ Message templating working without parse errors
✅ Performance audit shows expected optimizations
✅ All old API keys rotated and new keys active

### **Support**

For deployment issues:
1. Check logs: `tail -f bot.log debug.log`
2. Verify configuration: `python -c "from utils.config import APIConfig; APIConfig.validate()"`
3. Test specific components with provided test scripts
4. Review this deployment guide for missed steps