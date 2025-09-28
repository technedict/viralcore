# ViralCore Admin Panel Features - Deployment Guide

## Overview

This deployment guide covers the implementation of two major admin panel features:

1. **Withdrawal Payment Modes** - Automatic vs Manual processing
2. **Boosting Service Provider Management** - Edit likes/views service IDs

## Pre-Deployment Checklist

### 1. Database Backup

**CRITICAL: Always backup your database before deployment.**

```bash
# Create timestamped backup
cp viralcore.db viralcore.db.backup_$(date +%Y%m%d_%H%M%S)

# Or use the migration tool
python3 scripts/migrate_database.py --backup
```

### 2. Environment Verification

Ensure all required dependencies are installed:

```bash
# Check Python dependencies
python3 -c "import telegram, aiohttp, requests, sqlite3"

# Verify API credentials are set
python3 -c "from utils.config import APIConfig; APIConfig.validate()"
```

### 3. Code Validation

Run the integration tests:

```bash
# Run basic integration tests
python3 test_integration.py

# Run existing balance operations tests
python3 test_balance_operations.py
```

## Deployment Steps

### Step 1: Apply Database Migrations

```bash
# Check current migration status
python3 scripts/migrate_database.py --check

# Apply all pending migrations
python3 scripts/migrate_database.py --backup --apply
```

Expected output:
```
✅ Withdrawals table and audit log created
✅ Boosting service providers tables created and seeded
```

### Step 2: Verify Database Schema

```bash
# Verify new tables exist
python3 -c "
import sqlite3
conn = sqlite3.connect('viralcore.db')
cursor = conn.cursor()
cursor.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")
tables = [t[0] for t in cursor.fetchall()]
required_tables = ['withdrawals', 'withdrawal_audit_log', 'boosting_services', 'boosting_service_providers']
for table in required_tables:
    assert table in tables, f'Missing table: {table}'
print('✅ All required tables exist')
conn.close()
"
```

### Step 3: Test Bot Startup

```bash
# Test bot startup (dry run)
python3 -c "
from main_viral_core_bot import main
import asyncio
print('Testing bot imports...')
print('✅ Bot startup test passed')
"
```

### Step 4: Feature Flag Configuration

**Optional:** If you want to gradually roll out features, you can implement feature flags:

```python
# In utils/config.py, add:
ENABLE_MANUAL_WITHDRAWALS = os.getenv('ENABLE_MANUAL_WITHDRAWALS', 'true').lower() == 'true'
ENABLE_SERVICE_PROVIDER_EDITING = os.getenv('ENABLE_SERVICE_PROVIDER_EDITING', 'true').lower() == 'true'
```

### Step 5: Deploy and Monitor

1. **Deploy the code** to your production environment
2. **Restart the bot service**
3. **Monitor logs** for any startup errors
4. **Test basic functionality** with a test admin account

## Feature Usage Guide

### Withdrawal Payment Modes

#### For Users (Backwards Compatible)

**Default Behavior (Automatic):**
- User requests withdrawal → Balance checked → Flutterwave API called → Balance deducted on success
- No change to existing user experience

**Manual Mode (New):**
- Developer can set `payment_mode="manual"` in withdrawal creation
- User balance is **not** deducted until admin approval
- Admin receives notification to approve/reject
- Balance deducted atomically only on approval

#### For Admins

**New Admin Panel Menu:**
1. Go to Admin Panel → **Withdrawal Management**
2. View pending manual withdrawals
3. **Approve** - Deducts balance and marks as completed
4. **Reject** - Marks as rejected, no balance change
5. View withdrawal statistics

**Admin Actions are Idempotent:**
- Multiple approval attempts are safe
- Race conditions are handled with database locking
- All actions are logged in audit trail

### Boosting Service Provider Management

#### Current State
Your system currently uses hardcoded service IDs in `utils/boost_provider_utils.py`:

```python
PROVIDERS = {
    "smmflare": ProviderConfig(like_service_id=8646, view_service_id=8381),
    "plugsmms": ProviderConfig(like_service_id=11023, view_service_id=7750),
    "smmstone": ProviderConfig(like_service_id=6662, view_service_id=5480)
}
```

#### New Flexible System
After deployment, service IDs are stored in the database and can be edited:

**Admin Panel Menu:**
1. Go to Admin Panel → **Service Management**
2. **Current Mappings** - View all provider service IDs
3. **Edit Service IDs** - Change any provider's service ID
4. **Audit Log** - View history of all changes

**Editing Process:**
1. Select provider/service combination to edit
2. Enter new service ID
3. System validates the ID format
4. Confirm changes (shows old → new values)
5. Change is applied and logged

## Testing Procedures

### Manual Testing Checklist

#### Withdrawal Features
- [ ] Create automatic withdrawal (existing flow should work unchanged)
- [ ] Create manual withdrawal and verify admin notification
- [ ] Approve manual withdrawal and verify balance deduction
- [ ] Reject manual withdrawal and verify no balance change
- [ ] Test concurrent admin actions (should be idempotent)
- [ ] Verify audit logging for all actions

#### Service Provider Features
- [ ] View current provider mappings
- [ ] Edit a service ID and verify update
- [ ] Test invalid service ID validation
- [ ] Verify audit logging of changes
- [ ] Confirm boost requests use new service IDs

### Automated Testing

```bash
# Run integration tests
python3 test_integration.py

# Run withdrawal service tests (if dependencies available)
python3 tests/test_withdrawal_service.py

# Run boosting service tests
python3 tests/test_boosting_service_manager.py
```

## Rollback Plan

### If Issues Occur During Deployment

**Immediate Rollback:**
1. Stop the bot service
2. Restore database from backup:
   ```bash
   cp viralcore.db.backup_TIMESTAMP viralcore.db
   ```
3. Deploy previous code version
4. Restart bot service

**Partial Rollback (Feature-Specific):**
1. **Withdraw new features** by reverting specific handlers:
   - Remove new admin menu items from `handlers/admin_handlers.py`
   - Revert withdrawal creation in `handlers/custom_order_handlers.py`
2. **Keep database migrations** (they're backwards compatible)
3. Restart bot

### Post-Rollback Actions
1. Verify bot functionality with backup database
2. Investigate and fix issues in development environment
3. Plan re-deployment with fixes

## Monitoring and Maintenance

### Key Metrics to Monitor

**Withdrawal System:**
- Number of manual vs automatic withdrawals
- Admin response time for manual approvals
- Failed withdrawal rates
- Balance operation errors

**Service Provider System:**
- Boost success rates after service ID changes
- Frequency of service ID updates
- Provider API response times

### Log Analysis

**Important log entries to monitor:**

```bash
# Withdrawal operations
grep "Withdrawal.*created\|approved\|rejected" bot.log

# Service ID changes
grep "Updated provider service ID" bot.log

# Balance operation errors
grep "atomic_balance_update.*failed\|Balance operation failed" bot.log

# Admin actions
grep "Admin.*withdrawal\|Admin.*service" bot.log
```

### Database Maintenance

**Regular cleanup (optional):**

```sql
-- Archive old audit logs (older than 6 months)
DELETE FROM withdrawal_audit_log WHERE created_at < datetime('now', '-6 months');
DELETE FROM boosting_service_audit_log WHERE created_at < datetime('now', '-6 months');

-- Vacuum database to reclaim space
VACUUM;
```

## Troubleshooting

### Common Issues

**1. Migration Fails**
```
Error: table withdrawals already exists
```
**Solution:** Check if partial migration occurred. Manually verify table structure or restore from backup.

**2. Balance Operations Fail**
```
Error: database is locked
```
**Solution:** Ensure proper transaction handling. Check for long-running operations blocking database.

**3. Admin Panel Not Showing New Menus**
```
New menu items not visible
```
**Solution:** Verify admin permissions and handler registration in `main_viral_core_bot.py`.

**4. Service ID Changes Not Taking Effect**
```
Boost requests still using old service IDs
```
**Solution:** Restart bot to reload service configurations. Check database for updated mappings.

### Debug Commands

```bash
# Check database tables
python3 -c "
import sqlite3
conn = sqlite3.connect('viralcore.db')
cursor = conn.cursor() 
cursor.execute('SELECT name FROM sqlite_master WHERE type=\"table\"')
print('Tables:', [t[0] for t in cursor.fetchall()])
"

# Check withdrawal records
python3 -c "
import sqlite3
conn = sqlite3.connect('viralcore.db')
cursor = conn.cursor()
cursor.execute('SELECT COUNT(*) FROM withdrawals')
print('Total withdrawals:', cursor.fetchone()[0])
cursor.execute('SELECT payment_mode, COUNT(*) FROM withdrawals GROUP BY payment_mode')
print('By payment mode:', cursor.fetchall())
"

# Check service mappings
python3 -c "
import sqlite3
conn = sqlite3.connect('viralcore.db')
cursor = conn.cursor()
cursor.execute('SELECT provider_name, provider_service_id FROM boosting_service_providers')
print('Service mappings:', cursor.fetchall())
"
```

## Support

### Getting Help

1. **Check logs** in `bot.log` and `debug.log`
2. **Run diagnostic commands** from troubleshooting section
3. **Verify database integrity** with backup comparison
4. **Test in development environment** with isolated database

### Documentation

- **Database Schema:** Check migration files in `scripts/migrate_database.py`
- **API Reference:** Service classes in `utils/withdrawal_service.py` and `utils/boosting_service_manager.py`
- **Handler Logic:** Admin handlers in `handlers/admin_withdrawal_handlers.py` and `handlers/admin_service_handlers.py`

---

**Remember:** Always test thoroughly in a development environment before deploying to production!