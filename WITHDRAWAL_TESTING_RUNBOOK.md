# Withdrawal System Testing Runbook

This runbook provides step-by-step instructions for testing the three main withdrawal system enhancements:
1. Telegram admin notifications for Flutterwave errors
2. Consolidated automatic withdrawal process
3. User notifications on approval/rejection

## Prerequisites

- Python 3.8+
- SQLite3
- All dependencies installed: `pip install -r requirements.txt`
- Access to the repository: `/home/runner/work/viralcore/viralcore`
- Telegram bot token configured
- Test Telegram group for admin notifications

## Configuration Setup

### 1. Configure Admin Telegram Notifications

Edit your `.env` file:

```bash
# Telegram admin group for error notifications
ADMIN_TELEGRAM_CHAT_ID=-1001234567890  # Your test Telegram group ID

# Or use the legacy name (both work):
ADMIN_GROUP_ENDPOINT=-1001234567890

# Toggle for testing
ENABLE_TELEGRAM_NOTIFICATIONS=true

# Disable all notifications for testing
DISABLE_NOTIFICATIONS=false
```

**How to get your Telegram Group ID:**

1. Add your bot to a Telegram group
2. Send a message in the group
3. Visit: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
4. Look for `"chat":{"id":-1001234567890}` in the response
5. Use that negative number as your `ADMIN_TELEGRAM_CHAT_ID`

### 2. Configure Database

```bash
cd /home/runner/work/viralcore/viralcore

# Initialize database if needed
python3 -c "
from utils.db_utils import init_main_db
from utils.balance_operations import init_operations_ledger
from utils.withdrawal_settings import init_withdrawal_settings_table

init_main_db()
init_operations_ledger()
init_withdrawal_settings_table()
"
```

## Test 1: Telegram Admin Notifications for Flutterwave Errors

### Objective
Verify that Flutterwave API errors are sent to the admin Telegram group with structured information.

### Test Steps

**1.1 Test with Mock Flutterwave Error**

Create a test script to simulate a Flutterwave error:

```bash
cat > /tmp/test_flutterwave_error.py << 'EOF'
import sys
import asyncio
sys.path.insert(0, '/home/runner/work/viralcore/viralcore')

from utils.notification_service import get_notification_service, NotificationMessage

async def test_error_notification():
    """Simulate a Flutterwave error notification."""
    
    notification = NotificationMessage(
        title="❌ Withdrawal 123 Failed",
        body="""
Withdrawal request failed with error.

**User ID:** 12345
**Amount:** $50.00 USD / ₦75000 NGN
**Account:** Test User - ****5678
**Bank:** GTBank
**Error Code:** INSUFFICIENT_BALANCE
**Error:** Insufficient balance in Flutterwave account
**Payment Mode:** automatic
""".strip(),
        correlation_id="test_error_123",
        priority="high",
        metadata={
            "withdrawal_id": 123,
            "user_id": 12345,
            "amount_usd": 50.0,
            "error_code": "INSUFFICIENT_BALANCE",
            "timestamp": "2024-01-15T10:30:00Z"
        }
    )
    
    service = get_notification_service()
    print(f"Telegram enabled: {service.telegram_enabled}")
    print(f"Telegram groups: {service.telegram_group_ids}")
    
    if not service.telegram_enabled:
        print("\n❌ ERROR: Telegram notifications not enabled!")
        print("Please check ADMIN_TELEGRAM_CHAT_ID in .env")
        return
    
    print("\nSending test notification...")
    result = await service.send_notification(notification)
    
    print(f"\nResult: {result}")
    if result.get("telegram"):
        print("✅ SUCCESS: Notification sent to Telegram!")
    else:
        print("❌ FAILED: Could not send to Telegram")
        print("Check bot token and group ID")

asyncio.run(test_error_notification())
EOF

python3 /tmp/test_flutterwave_error.py
```

**Expected Output:**
```
Telegram enabled: True
Telegram groups: ['-1001234567890']

Sending test notification...

Result: {'telegram': True}
✅ SUCCESS: Notification sent to Telegram!
```

**Verify in Telegram:**
- Check your admin Telegram group
- You should see a message with the withdrawal error details
- Message should be formatted with markdown (bold fields, etc.)

**1.2 Test Deduplication**

Run the same test script twice quickly:

```bash
python3 /tmp/test_flutterwave_error.py
sleep 1
python3 /tmp/test_flutterwave_error.py
```

**Expected:**
- First run: Notification sent
- Second run: Notification skipped (duplicate detected)
- Check logs for "Duplicate notification detected" message

**1.3 Test with Real Withdrawal Error (Integration Test)**

This requires triggering an actual withdrawal failure:

```bash
cat > /tmp/test_real_withdrawal_error.py << 'EOF'
import sys
import os
sys.path.insert(0, '/home/runner/work/viralcore/viralcore')

# Set test environment
os.environ['FLUTTERWAVE_API_KEY'] = 'test_invalid_key'  # Force API error

from utils.withdrawal_service import get_withdrawal_service
from utils.db_utils import get_connection, DB_FILE

# Create test user and withdrawal
with get_connection(DB_FILE) as conn:
    c = conn.cursor()
    
    # Create test user
    c.execute('''
        INSERT OR REPLACE INTO users (id, username, affiliate_balance)
        VALUES (99999, 'test_user', 100.0)
    ''')
    conn.commit()

# Create withdrawal
service = get_withdrawal_service()
withdrawal = service.create_withdrawal(
    user_id=99999,
    amount_usd=50.0,
    amount_ngn=75000.0,
    account_name="Test User",
    account_number="1234567890",
    bank_name="GTBank",
    bank_details_raw="Test User, 1234567890, GTBank",
    is_affiliate_withdrawal=True,
    payment_mode="automatic"
)

print(f"Created withdrawal {withdrawal.id}")

# Try to approve (will fail due to invalid API key)
success = service.approve_withdrawal_by_mode(
    withdrawal_id=withdrawal.id,
    admin_id=2,  # Admin user
    reason="Test automatic approval"
)

print(f"Approval result: {success}")
print("Check your Telegram group for error notification!")
EOF

python3 /tmp/test_real_withdrawal_error.py
```

**Expected:**
- Withdrawal created
- Approval fails (invalid API key)
- Admin Telegram group receives error notification
- Error notification includes correlation ID, error details

## Test 2: Consolidated Automatic Withdrawal Process

### Objective
Verify that the consolidated automatic withdrawal process works correctly and backward compatibility is maintained.

### Test Steps

**2.1 Test Consolidated Process (Main Path)**

```bash
cat > /tmp/test_consolidated_withdrawal.py << 'EOF'
import sys
sys.path.insert(0, '/home/runner/work/viralcore/viralcore')

from utils.withdrawal_service import get_withdrawal_service
from utils.db_utils import get_connection, DB_FILE

# Create test user
with get_connection(DB_FILE) as conn:
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO users (id, username, affiliate_balance)
        VALUES (88888, 'test_auto_user', 200.0)
    ''')
    conn.commit()

service = get_withdrawal_service()

# Create automatic withdrawal
withdrawal = service.create_withdrawal(
    user_id=88888,
    amount_usd=75.0,
    amount_ngn=112500.0,
    account_name="Test Auto User",
    account_number="9876543210",
    bank_name="Access Bank",
    bank_details_raw="Test Auto User, 9876543210, Access Bank",
    is_affiliate_withdrawal=True,
    payment_mode="automatic"
)

print(f"✅ Created automatic withdrawal {withdrawal.id}")
print(f"   Payment mode: {withdrawal.payment_mode.value}")
print(f"   Status: {withdrawal.status.value}")
print(f"   Admin approval: {withdrawal.admin_approval_state}")

# Approve using consolidated method
print("\n📋 Approving via consolidated approve_withdrawal_by_mode...")
success = service.approve_withdrawal_by_mode(
    withdrawal_id=withdrawal.id,
    admin_id=2,
    reason="Test consolidated automatic approval"
)

print(f"\n{'✅' if success else '❌'} Approval result: {success}")

# Check final state
final_withdrawal = service.get_withdrawal(withdrawal.id)
print(f"\n📊 Final withdrawal state:")
print(f"   Status: {final_withdrawal.status.value}")
print(f"   Admin approval: {final_withdrawal.admin_approval_state.value if final_withdrawal.admin_approval_state else 'None'}")
print(f"   Flutterwave ref: {final_withdrawal.flutterwave_reference}")

# Check balance was deducted
with get_connection(DB_FILE) as conn:
    c = conn.cursor()
    c.execute('SELECT affiliate_balance FROM users WHERE id = ?', (88888,))
    final_balance = c.fetchone()[0]
    print(f"   User balance after: ${final_balance}")
    print(f"   Expected: $125.0 (200 - 75)")
EOF

python3 /tmp/test_consolidated_withdrawal.py
```

**Expected Output:**
```
✅ Created automatic withdrawal 456
   Payment mode: automatic
   Status: pending
   Admin approval: None

📋 Approving via consolidated approve_withdrawal_by_mode...

✅ Approval result: True

📊 Final withdrawal state:
   Status: completed (or processing if Flutterwave succeeds)
   Admin approval: approved
   Flutterwave ref: VCW_456_abc12345
   User balance after: $125.0
   Expected: $125.0 (200 - 75)
```

**2.2 Test Backward Compatibility Shim**

```bash
cat > /tmp/test_deprecated_method.py << 'EOF'
import sys
sys.path.insert(0, '/home/runner/work/viralcore/viralcore')

from utils.withdrawal_service import get_withdrawal_service, AdminApprovalState
from utils.db_utils import get_connection, DB_FILE

# Create approved withdrawal for testing deprecated method
with get_connection(DB_FILE) as conn:
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO users (id, username, affiliate_balance)
        VALUES (77777, 'test_deprecated', 100.0)
    ''')
    conn.commit()

service = get_withdrawal_service()

withdrawal = service.create_withdrawal(
    user_id=77777,
    amount_usd=25.0,
    amount_ngn=37500.0,
    account_name="Test Deprecated",
    account_number="1111111111",
    bank_name="UBA",
    bank_details_raw="Test Deprecated, 1111111111, UBA",
    is_affiliate_withdrawal=True,
    payment_mode="automatic"
)

# Manually approve it first
with get_connection(DB_FILE) as conn:
    c = conn.cursor()
    c.execute('''
        UPDATE withdrawals 
        SET admin_approval_state = 'approved'
        WHERE id = ?
    ''', (withdrawal.id,))
    conn.commit()

# Reload withdrawal
withdrawal = service.get_withdrawal(withdrawal.id)

print(f"Testing deprecated process_automatic_withdrawal...")
print(f"Withdrawal {withdrawal.id} is approved: {withdrawal.admin_approval_state == AdminApprovalState.APPROVED}")

# Call deprecated method - should log warning and forward to new method
try:
    result = service.process_automatic_withdrawal(withdrawal)
    print(f"✅ Deprecated method returned: {result}")
    print("Check logs for deprecation warning")
except Exception as e:
    print(f"Method behavior: {e}")
EOF

python3 /tmp/test_deprecated_method.py 2>&1 | grep -E "DEPRECATED|✅|Withdrawal"
```

**Expected:**
- Deprecation warning in logs
- Method still works (calls consolidated process)
- Returns expected result

**2.3 Test Approval Gating (Security)**

Verify that automatic withdrawal cannot be executed without approval:

```bash
cat > /tmp/test_approval_gating.py << 'EOF'
import sys
sys.path.insert(0, '/home/runner/work/viralcore/viralcore')

from utils.withdrawal_service import get_withdrawal_service
from utils.db_utils import get_connection, DB_FILE

# Create test user
with get_connection(DB_FILE) as conn:
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO users (id, username, affiliate_balance)
        VALUES (66666, 'test_security', 100.0)
    ''')
    conn.commit()

service = get_withdrawal_service()

withdrawal = service.create_withdrawal(
    user_id=66666,
    amount_usd=30.0,
    amount_ngn=45000.0,
    account_name="Test Security",
    account_number="2222222222",
    bank_name="Zenith",
    bank_details_raw="Test Security, 2222222222, Zenith",
    is_affiliate_withdrawal=True,
    payment_mode="automatic"
)

print(f"Created unapproved withdrawal {withdrawal.id}")
print(f"Admin approval state: {withdrawal.admin_approval_state}")

# Try to execute without approval - should fail
try:
    result = service.execute_approved_automatic_withdrawal(withdrawal)
    print(f"❌ SECURITY ISSUE: Method executed without approval! Result: {result}")
except ValueError as e:
    print(f"✅ SECURITY OK: Method correctly rejected unapproved withdrawal")
    print(f"   Error: {e}")
EOF

python3 /tmp/test_approval_gating.py
```

**Expected:**
```
Created unapproved withdrawal 789
Admin approval state: None

✅ SECURITY OK: Method correctly rejected unapproved withdrawal
   Error: Cannot process withdrawal 789 - admin approval required. Current state: None
```

## Test 3: User Notifications on Approval/Rejection

### Objective
Verify that users receive notifications when their withdrawal is approved or rejected.

### Test Steps

**3.1 Test User Approval Notification**

```bash
cat > /tmp/test_user_approval_notification.py << 'EOF'
import sys
import asyncio
sys.path.insert(0, '/home/runner/work/viralcore/viralcore')

from utils.notification_service import notify_user_withdrawal_approved

async def test_approval_notification():
    """Test sending approval notification to user."""
    
    # Note: This will attempt to send to user ID 12345's Telegram
    # Make sure this user exists in your database
    
    result = await notify_user_withdrawal_approved(
        user_id=12345,  # Replace with actual test user ID
        withdrawal_id=999,
        amount_usd=50.0,
        amount_ngn=75000.0,
        bank_name="GTBank",
        account_number="1234567890",
        payment_mode="automatic",
        correlation_id="test_approval_999"
    )
    
    print(f"Notification sent: {result}")
    
    if result:
        print("✅ User should receive approval notification")
        print("Check the user's Telegram for the message")
    else:
        print("❌ Notification failed - check logs")

asyncio.run(test_approval_notification())
EOF

python3 /tmp/test_user_approval_notification.py
```

**Expected:**
- User receives Telegram message
- Message includes withdrawal amount, bank details (masked), status
- Message is formatted correctly with emoji

**3.2 Test User Rejection Notification**

```bash
cat > /tmp/test_user_rejection_notification.py << 'EOF'
import sys
import asyncio
sys.path.insert(0, '/home/runner/work/viralcore/viralcore')

from utils.notification_service import notify_user_withdrawal_rejected

async def test_rejection_notification():
    """Test sending rejection notification to user."""
    
    result = await notify_user_withdrawal_rejected(
        user_id=12345,  # Replace with actual test user ID
        withdrawal_id=888,
        amount_usd=100.0,
        amount_ngn=150000.0,
        bank_name="Access Bank",
        account_number="9876543210",
        reason="Insufficient balance in admin account",
        correlation_id="test_rejection_888"
    )
    
    print(f"Notification sent: {result}")
    
    if result:
        print("✅ User should receive rejection notification")
        print("Check the user's Telegram for the message")
    else:
        print("❌ Notification failed - check logs")

asyncio.run(test_rejection_notification())
EOF

python3 /tmp/test_user_rejection_notification.py
```

**Expected:**
- User receives Telegram message
- Message includes reason for rejection
- Message includes next steps

**3.3 Test Notification Idempotency**

```bash
cat > /tmp/test_notification_idempotency.py << 'EOF'
import sys
import asyncio
sys.path.insert(0, '/home/runner/work/viralcore/viralcore')

from utils.notification_service import notify_user_withdrawal_approved
from utils.db_utils import get_connection, DB_FILE

async def test_idempotency():
    """Test that same notification won't be sent twice."""
    
    # Send notification first time
    print("Sending notification (attempt 1)...")
    result1 = await notify_user_withdrawal_approved(
        user_id=12345,
        withdrawal_id=777,
        amount_usd=25.0,
        amount_ngn=37500.0,
        bank_name="UBA",
        account_number="5555555555",
        payment_mode="manual",
        correlation_id="test_idemp_777"
    )
    print(f"First attempt result: {result1}")
    
    # Check database record
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('''
            SELECT COUNT(*) FROM user_notifications 
            WHERE withdrawal_id = 777
        ''')
        count = c.fetchone()[0]
        print(f"Records in DB: {count}")
    
    # Try to send same notification again
    print("\nSending notification (attempt 2)...")
    result2 = await notify_user_withdrawal_approved(
        user_id=12345,
        withdrawal_id=777,
        amount_usd=25.0,
        amount_ngn=37500.0,
        bank_name="UBA",
        account_number="5555555555",
        payment_mode="manual",
        correlation_id="test_idemp_777"
    )
    print(f"Second attempt result: {result2}")
    
    # Check database - should still be 1 record
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('''
            SELECT COUNT(*) FROM user_notifications 
            WHERE withdrawal_id = 777
        ''')
        final_count = c.fetchone()[0]
        print(f"Final records in DB: {final_count}")
    
    if final_count == 1:
        print("✅ Idempotency working: notification sent only once")
    else:
        print(f"❌ Idempotency issue: {final_count} records instead of 1")

asyncio.run(test_idempotency())
EOF

python3 /tmp/test_notification_idempotency.py
```

**Expected:**
- First attempt: Notification sent
- Second attempt: Record updated but user doesn't receive duplicate
- Database: Only 1 record exists (UNIQUE constraint prevents duplicates)

## Test 4: Integration Test - Full Withdrawal Flow

### Objective
Test complete workflow from creation to user notification.

```bash
cat > /tmp/test_full_withdrawal_flow.py << 'EOF'
import sys
import asyncio
sys.path.insert(0, '/home/runner/work/viralcore/viralcore')

from utils.withdrawal_service import get_withdrawal_service
from utils.db_utils import get_connection, DB_FILE

async def test_full_flow():
    """Test complete withdrawal flow with all notifications."""
    
    # Setup: Create test user
    user_id = 55555
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('''
            INSERT OR REPLACE INTO users (id, username, affiliate_balance)
            VALUES (?, 'test_full_flow', 150.0)
        ''', (user_id,))
        conn.commit()
    
    service = get_withdrawal_service()
    
    # Step 1: User creates withdrawal
    print("📝 Step 1: Creating withdrawal...")
    withdrawal = service.create_withdrawal(
        user_id=user_id,
        amount_usd=60.0,
        amount_ngn=90000.0,
        account_name="Full Flow Test",
        account_number="3333333333",
        bank_name="First Bank",
        bank_details_raw="Full Flow Test, 3333333333, First Bank",
        is_affiliate_withdrawal=True,
        payment_mode="automatic"
    )
    print(f"   ✅ Withdrawal {withdrawal.id} created")
    
    # Step 2: Admin approves (this triggers user notification)
    print("\n👤 Step 2: Admin approving withdrawal...")
    
    # Note: In real flow, admin handler calls approve_withdrawal_by_mode
    # which then triggers user notification
    success = service.approve_withdrawal_by_mode(
        withdrawal_id=withdrawal.id,
        admin_id=2,
        reason="Approved by test admin"
    )
    print(f"   {'✅' if success else '❌'} Approval: {success}")
    
    # Manually trigger user notification (in real system, admin handler does this)
    from utils.notification_service import notify_user_withdrawal_approved
    
    print("\n📧 Step 3: Sending user notification...")
    notif_result = await notify_user_withdrawal_approved(
        user_id=user_id,
        withdrawal_id=withdrawal.id,
        amount_usd=withdrawal.amount_usd,
        amount_ngn=withdrawal.amount_ngn,
        bank_name=withdrawal.bank_name,
        account_number=withdrawal.account_number,
        payment_mode=withdrawal.payment_mode.value,
        correlation_id=f"full_flow_{withdrawal.id}"
    )
    print(f"   {'✅' if notif_result else '❌'} User notification: {notif_result}")
    
    # Step 4: Verify final state
    print("\n📊 Step 4: Verifying final state...")
    final_withdrawal = service.get_withdrawal(withdrawal.id)
    print(f"   Withdrawal status: {final_withdrawal.status.value}")
    print(f"   Admin approval: {final_withdrawal.admin_approval_state.value if final_withdrawal.admin_approval_state else 'None'}")
    
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('SELECT affiliate_balance FROM users WHERE id = ?', (user_id,))
        final_balance = c.fetchone()[0]
        print(f"   User balance: ${final_balance} (expected: $90.0)")
        
        c.execute('''
            SELECT status FROM user_notifications 
            WHERE withdrawal_id = ?
        ''', (withdrawal.id,))
        notif_row = c.fetchone()
        if notif_row:
            print(f"   User notification logged: {notif_row[0]}")
        else:
            print("   ❌ No notification record found")
    
    print("\n" + "="*60)
    print("FULL FLOW TEST COMPLETE")
    print("Check:")
    print("- User's Telegram for approval notification")
    print("- Admin Telegram group for any error notifications")
    print("- Database for audit records")

asyncio.run(test_full_flow())
EOF

python3 /tmp/test_full_withdrawal_flow.py
```

## Verification Checklist

After running all tests, verify:

### Goal 1: Telegram Admin Notifications
- [ ] Admin Telegram group receives Flutterwave error notifications
- [ ] Notifications include structured error details
- [ ] Correlation IDs are present
- [ ] Deduplication prevents spam
- [ ] Can be toggled on/off via environment variable

### Goal 2: Consolidated Automatic Withdrawal
- [ ] `approve_withdrawal_by_mode` works for automatic mode
- [ ] Deprecated `process_automatic_withdrawal` still works (logs warning)
- [ ] Approval gating prevents unapproved execution
- [ ] Balance deducted atomically before external API call
- [ ] Error handling centralizes notifications

### Goal 3: User Notifications
- [ ] Users receive approval notifications
- [ ] Users receive rejection notifications
- [ ] Notifications are formatted correctly
- [ ] Account numbers are masked
- [ ] Idempotency prevents duplicates
- [ ] Notifications logged in database

## Rollback Procedures

If issues occur:

### Disable Telegram Notifications
```bash
# In .env file:
ENABLE_TELEGRAM_NOTIFICATIONS=false

# Or disable all notifications:
DISABLE_NOTIFICATIONS=true
```

### Revert to Old Automatic Withdrawal
The old `process_automatic_withdrawal` still exists as a shim, so no code changes needed for rollback.

### Re-run Pending Withdrawals
```bash
python3 -c "
from utils.withdrawal_service import get_withdrawal_service
from utils.withdrawal_service import WithdrawalStatus

service = get_withdrawal_service()

# Get all processing withdrawals
withdrawals = service.get_withdrawals_by_status(WithdrawalStatus.PROCESSING)

for w in withdrawals:
    print(f'Withdrawal {w.id}: {w.status.value}')
    # Manually review and re-approve if needed
"
```

## Troubleshooting

### Telegram Notifications Not Received

**Check:**
1. Bot token is correct in `.env`
2. Bot is added to the admin group
3. Group ID is correct (use negative number for groups)
4. `ENABLE_TELEGRAM_NOTIFICATIONS=true`
5. Bot has permission to send messages in group

**Debug:**
```bash
python3 -c "
from utils.notification_service import get_notification_service
service = get_notification_service()
print(f'Telegram enabled: {service.telegram_enabled}')
print(f'Group IDs: {service.telegram_group_ids}')
"
```

### User Notifications Not Working

**Check:**
1. User exists in database with valid ID
2. User's Telegram account is linked (user.id = chat_id)
3. Bot can send messages to user (user must have started bot)

**Debug:**
```bash
python3 -c "
from utils.db_utils import get_connection, DB_FILE

with get_connection(DB_FILE) as conn:
    c = conn.cursor()
    c.execute('SELECT id, username FROM users WHERE id = ?', (12345,))
    user = c.fetchone()
    print(f'User: {user}')
"
```

### Duplicate Notifications

**Check database:**
```bash
sqlite3 db/viralcore.db "
SELECT * FROM user_notifications 
WHERE withdrawal_id = 123
ORDER BY created_at DESC;
"
```

The UNIQUE constraint should prevent duplicates, but check for any violations.

## Production Monitoring

After deployment, monitor:

```bash
# Check for Flutterwave errors
grep "Flutterwave.*error" bot.log | tail -20

# Check user notifications sent
sqlite3 db/viralcore.db "
SELECT notification_type, COUNT(*) 
FROM user_notifications 
GROUP BY notification_type;
"

# Check notification failures
sqlite3 db/viralcore.db "
SELECT * FROM user_notifications 
WHERE status = 'failed' 
ORDER BY created_at DESC 
LIMIT 10;
"

# Monitor admin notifications
grep "Sent error notification" bot.log | tail -10
```

## Contact & Support

For issues:
1. Check structured logs with correlation IDs
2. Verify configuration in `.env`
3. Run test scripts to isolate issue
4. Use correlation IDs to trace specific flows
5. Contact development team with specific correlation IDs and test results
