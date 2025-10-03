# ViralCore v2.2.0 - Testing Guide

## Overview
This guide provides comprehensive testing instructions for the new database centralization and enhanced withdrawal features.

## Prerequisites

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

## Test Suite Execution

### 1. Database Centralization Tests

**Test DB directory creation and file migration:**
```bash
python3 tests/test_db_centralization.py
```

**Expected Output:**
```
Testing DB centralization...
==================================================
✅ DB_DIR creation test passed
✅ DB file paths test passed
✅ DB initialization test passed
==================================================
✅ All DB centralization tests passed!
```

**What's tested:**
- DB_DIR is created automatically
- All DB file paths use centralized directory
- DB initialization works correctly
- Tables are created in the right location

### 2. Manual Withdrawal Tests

**Test balance deduction correctness:**
```bash
python3 tests/test_manual_withdrawal.py
```

**Expected Output:**
```
=== Test Case 1: Affiliate Withdrawal ===
Initial affiliate balance: $100.0
Created withdrawal ID: 1
Approval success: True
Balance after withdrawal: $50.0
✅ Test Case 1 PASSED: Affiliate withdrawal correctly deducted balance

=== Test Case 2: Insufficient Balance ===
Large withdrawal approval success: False
✅ Test Case 2 PASSED: Insufficient balance prevented withdrawal

=== Test Case 3: Idempotency ===
Balance after second approval: $40.0
✅ Test Case 3 PASSED: Idempotency prevents double deduction

==================================================
✅ ALL MANUAL WITHDRAWAL TESTS PASSED!
==================================================
```

**What's tested:**
- Balance is correctly deducted for manual withdrawals
- Insufficient balance prevents withdrawal
- Idempotency prevents duplicate deductions
- Withdrawal status updates correctly
- Audit log is created

### 3. Migration Script Tests

**Test database migration (dry run):**
```bash
# Create some test DB files
touch viralcore.db tweets.db

# Run migration script (will fail at startup without config, but migration part works)
./scripts/migrate_and_run.sh
```

**Expected Behavior:**
- Creates `./db` directory
- Moves `.db` files to `./db/`
- Creates backups in `./db/backups/` with timestamps
- Logs all operations clearly

**Check results:**
```bash
ls -la db/
ls -la db/backups/
```

### 4. Notification Service Tests

**Test notification configuration:**
```python
# Create test file: test_notifications.py
import os
os.environ['ADMIN_GROUP_ENDPOINT'] = '-123456789'
os.environ['ADMIN_CONTACTS'] = 'test@example.com'

from utils.notification_service import get_notification_service, NotificationMessage

service = get_notification_service()
print(f"Telegram enabled: {service.telegram_enabled}")
print(f"Email enabled: {service.email_enabled}")
print(f"Telegram groups: {service.telegram_group_ids}")
print(f"Admin emails: {service.admin_emails}")
```

**Expected Output:**
```
Telegram enabled: True
Email enabled: False
Telegram groups: ['-123456789']
Admin emails: ['test@example.com']
```

### 5. Balance Operations Tests

**Test existing balance operations:**
```bash
python3 test_balance_operations.py
```

**What's tested:**
- Atomic balance operations
- Idempotency protection
- Concurrent operation handling
- Balance ledger recording

## Manual Testing Scenarios

### Scenario 1: Fresh Installation

1. **Clone repository:**
   ```bash
   git clone https://github.com/technedict/viralcore.git
   cd viralcore
   ```

2. **Configure:**
   ```bash
   cp .env.example .env
   # Edit .env with real API keys
   ```

3. **Run migration:**
   ```bash
   ./scripts/migrate_and_run.sh
   ```

4. **Verify:**
   - Check `./db` directory exists
   - Check all DB files are in `./db/`
   - Check bot starts successfully

### Scenario 2: Upgrading from v2.1.x

1. **Backup existing database:**
   ```bash
   cp viralcore.db viralcore.db.backup_manual
   ```

2. **Pull updates:**
   ```bash
   git pull origin main
   ```

3. **Run migration:**
   ```bash
   python3 scripts/migrate_database.py --backup --apply
   ```

4. **Verify:**
   - Check original DBs are in `./db/`
   - Check backups are in `./db/backups/`
   - Check no data loss (compare record counts)

### Scenario 3: Withdrawal Flow Testing

**Setup:**
1. Create test user with balance
2. Configure admin approval (keep `DISABLE_ADMIN_APPROVAL=false`)

**Test Manual Withdrawal:**
1. User initiates withdrawal via bot
2. Check withdrawal record created with `status='pending'`
3. Check `admin_approval_state='pending'`
4. Admin approves withdrawal
5. Verify balance deducted
6. Verify withdrawal status updated to `completed`
7. Check audit log entry created

**Test Automatic Withdrawal:**
1. User initiates withdrawal (automatic mode)
2. Check withdrawal created with pending admin approval
3. Admin approves
4. System should call Flutterwave API (mock in test)
5. On success: balance deducted, status = completed
6. On failure: balance restored, error logged, admin notified

**Test Error Notification:**
1. Configure admin notifications
2. Cause withdrawal to fail (invalid bank details)
3. Verify admin receives notification
4. Check `withdrawal_errors` table has error record
5. Verify correlation ID is present

### Scenario 4: Database Locking

**Test concurrent withdrawals:**
```bash
# Run multiple withdrawal approvals simultaneously
python3 -c "
from concurrent.futures import ThreadPoolExecutor
from utils.withdrawal_service import get_withdrawal_service

service = get_withdrawal_service()
with ThreadPoolExecutor(max_workers=5) as executor:
    results = [executor.submit(service.approve_manual_withdrawal, i, 1, 'test') 
               for i in range(1, 6)]
    print([r.result() for r in results])
"
```

**Expected:** No database locked errors, all operations complete

## Environment Variable Testing

Test each new environment variable:

```bash
# Test DB_DIR
export DB_DIR=/tmp/test_db
python3 -c "from utils.db_utils import DB_FILE; print(DB_FILE)"
# Expected: /tmp/test_db/viralcore.db

# Test DISABLE_ADMIN_APPROVAL
export DISABLE_ADMIN_APPROVAL=true
python3 -c "
from utils.withdrawal_service import WithdrawalService
service = WithdrawalService()
w = service.create_withdrawal(1, 10, 16500, 'Test', '123', 'Bank', 'raw', False)
print(f'Approval state: {w.admin_approval_state}')
"
# Expected: Approval state: None (not pending)

# Test notification channels
export ADMIN_GROUP_ENDPOINT=-123,-456
export ADMIN_CONTACTS=a@x.com,b@y.com
python3 -c "
from utils.notification_service import get_notification_service
s = get_notification_service()
print(f'Groups: {s.telegram_group_ids}')
print(f'Emails: {s.admin_emails}')
"
# Expected: Groups: ['-123', '-456'], Emails: ['a@x.com', 'b@y.com']
```

## Performance Testing

### Database Migration Performance

Test migration with large databases:
```bash
# Create large test database
python3 -c "
import sqlite3
conn = sqlite3.connect('large_test.db')
c = conn.cursor()
c.execute('CREATE TABLE test (id INTEGER, data TEXT)')
for i in range(100000):
    c.execute('INSERT INTO test VALUES (?, ?)', (i, 'x'*100))
conn.commit()
"

# Time migration
time python3 -c "
from utils.db_utils import migrate_db_files_to_directory
migrate_db_files_to_directory()
"
```

### Withdrawal Processing Performance

Test withdrawal approval speed:
```bash
python3 -c "
import time
from utils.withdrawal_service import get_withdrawal_service

service = get_withdrawal_service()
# Create 100 test withdrawals
start = time.time()
for i in range(100):
    service.approve_manual_withdrawal(i, 1, 'test')
end = time.time()
print(f'Processed 100 withdrawals in {end-start:.2f}s')
"
```

## Rollback Testing

**Test rollback on automatic withdrawal failure:**
1. Set up test to force Flutterwave API failure
2. Approve automatic withdrawal
3. Verify balance is restored
4. Check withdrawal_errors table
5. Verify admin notification sent

## Security Testing

### SQL Injection Prevention
All queries use parameterized statements ✅

### XSS in Notifications
Test notification messages with special characters:
```python
from utils.notification_service import NotificationMessage

msg = NotificationMessage(
    title="Test <script>alert(1)</script>",
    body="Amount: $100 & user = 'test'"
)
# Verify proper escaping in Telegram, Email, Slack
```

### Access Control
- Test that only admins can approve withdrawals
- Test that users can't approve their own withdrawals
- Verify audit logs record admin actions

## Compatibility Testing

### Python Versions
Test on:
- Python 3.8
- Python 3.9
- Python 3.10
- Python 3.11

### Operating Systems
Test on:
- Ubuntu 20.04/22.04
- macOS
- Windows (WSL)

## Regression Testing

Run all existing tests to ensure no regressions:
```bash
python3 tests/test_job_system.py
python3 tests/test_withdrawal_core.py
python3 test_balance_operations.py
```

All should pass without modifications.

## Sign-off Checklist

- [ ] All unit tests pass
- [ ] Integration tests pass
- [ ] Manual testing scenarios completed
- [ ] Migration tested on existing database
- [ ] No database locking issues observed
- [ ] Notifications work on all configured channels
- [ ] Documentation is accurate
- [ ] No regressions in existing features
- [ ] Performance is acceptable
- [ ] Security review completed

## Reporting Issues

If you encounter any issues during testing:

1. **Capture logs:**
   ```bash
   # Enable debug logging
   export LOG_LEVEL=DEBUG
   python3 main_viral_core_bot.py > debug.log 2>&1
   ```

2. **Include details:**
   - Python version
   - Operating system
   - Full error traceback
   - Steps to reproduce
   - Expected vs actual behavior

3. **Database state:**
   ```bash
   sqlite3 db/viralcore.db "SELECT name FROM sqlite_master WHERE type='table'"
   ```

## Support

For questions or issues:
- Open a GitHub issue
- Include test results and logs
- Tag with appropriate labels (bug, testing, etc.)
