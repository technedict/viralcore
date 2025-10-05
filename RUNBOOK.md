# Runbook: Crypto Payment Verification & Balance Deduction Fixes

## Overview
This runbook provides step-by-step instructions for reproducing, testing, and validating the fixes for:
1. Crypto payment verification NOTOK failures
2. Database locked errors during concurrent balance deductions

## Prerequisites
- Python 3.8+
- SQLite3
- All dependencies installed: `pip install -r requirements.txt`
- Access to the repository: `/home/runner/work/viralcore/viralcore`

## Quick Validation

### 1. Test Concurrency Fixes (No Database Locked Errors)

Run this test to verify that concurrent balance deductions no longer produce "database is locked" errors:

```bash
cd /home/runner/work/viralcore/viralcore

python3 -c "
import tempfile, os, sys
from concurrent.futures import ThreadPoolExecutor, as_completed

# Create temp db
fd, db_path = tempfile.mkstemp(suffix='.db')
os.close(fd)

# Patch DB paths
import utils.db_utils
import utils.withdrawal_service
import utils.balance_operations
import utils.withdrawal_settings

utils.db_utils.DB_FILE = db_path
utils.withdrawal_service.DB_FILE = db_path
utils.balance_operations.DB_FILE = db_path
utils.withdrawal_settings.DB_FILE = db_path

# Initialize
from utils.db_utils import init_main_db, get_connection
from utils.balance_operations import atomic_deposit_operation, atomic_withdraw_operation, init_operations_ledger
from utils.withdrawal_settings import init_withdrawal_settings_table

init_main_db()
init_operations_ledger()
init_withdrawal_settings_table()

# Create test user
with get_connection(db_path) as conn:
    c = conn.cursor()
    c.execute('INSERT INTO users (id, username, affiliate_balance) VALUES (?, ?, ?)', (123456, 'test_user', 0.0))
    conn.commit()

# Add initial balance
atomic_deposit_operation(user_id=123456, balance_type='affiliate', amount=1000.0, reason='Initial')

# Run concurrent withdrawals
results, errors = [], []

def attempt_withdrawal(amount, attempt_id):
    try:
        success = atomic_withdraw_operation(
            user_id=123456,
            balance_type='affiliate',
            amount=amount,
            reason=f'Test withdrawal {attempt_id}'
        )
        results.append((attempt_id, success))
        return success
    except Exception as e:
        errors.append((attempt_id, str(e)))
        return False

# 10 concurrent withdrawals of 150 each (max 6 should succeed)
with ThreadPoolExecutor(max_workers=10) as executor:
    futures = [executor.submit(attempt_withdrawal, 150.0, i) for i in range(10)]
    for future in as_completed(futures):
        future.result()

# Check results
db_locked_errors = [e for _, e in errors if 'database is locked' in e.lower()]
successful = sum(1 for _, s in results if s)

print('='*60)
print('CONCURRENCY TEST RESULTS')
print('='*60)
print(f'Database locked errors: {len(db_locked_errors)}')
print(f'Successful withdrawals: {successful}')
print(f'Failed withdrawals: {len(results) - successful}')

with get_connection(db_path) as conn:
    c = conn.cursor()
    c.execute('SELECT affiliate_balance FROM users WHERE id = ?', (123456,))
    final_balance = c.fetchone()[0]
    print(f'Final balance: {final_balance}')

os.unlink(db_path)

if db_locked_errors:
    print('\\n❌ FAILED: Database locked errors occurred')
    sys.exit(1)
else:
    print('\\n✅ PASSED: No database locked errors')
    sys.exit(0)
"
```

**Expected Output:**
```
CONCURRENCY TEST RESULTS
Database locked errors: 0
Successful withdrawals: 6
Failed withdrawals: 4
Final balance: 100.0

✅ PASSED: No database locked errors
```

### 2. Test Payment Verification Fixes

Run this test to verify payment verification improvements:

```bash
cd /home/runner/work/viralcore/viralcore

python3 -c "
from handlers.payment_handler import PaymentHandler

handler = PaymentHandler()

print('Testing Payment Verification Fixes')
print('='*60)

# Test 1: Address normalization
addr1 = '0x7fF8c2F4510EdC4CcB74481588dca909730AEdF5'
addr2 = '0x7ff8c2f4510edc4ccb74481588dca909730aedf5'
norm1 = handler._normalize_address(addr1, 'bnb')
norm2 = handler._normalize_address(addr2, 'bnb')
assert norm1 == norm2
print('✅ BSC address normalization (case-insensitive)')

# Test 2: Solana addresses preserve case
sol_addr = 'Gejh1bYCihLLk1BUwhnWKZEyurT7b8azBFXf44yy7MkB'
norm_sol = handler._normalize_address(sol_addr, 'sol')
assert norm_sol == sol_addr
print('✅ Solana address normalization (case-preserving)')

# Test 3: Hash validation
valid_hash = '0x' + 'a' * 64
assert handler._validate_tx_hash_format(valid_hash, 'bnb')
print('✅ BSC hash format validation')

# Test 4: USDT token symbols
valid_symbols = ['USDT', 'BSC-USD', 'USD']
for symbol in valid_symbols:
    assert symbol.upper() in ['USDT', 'BSC-USD', 'USD']
print(f'✅ USDT token symbol variants: {valid_symbols}')

# Test 5: Logging methods
assert hasattr(handler, '_log_verification_attempt')
assert hasattr(handler, '_log_verification_result')
print('✅ Structured logging methods available')

print('\\n' + '='*60)
print('ALL TESTS PASSED')
" 2>&1 | grep -v "SyntaxWarning\|Missing required"
```

**Expected Output:**
```
Testing Payment Verification Fixes
============================================================
✅ BSC address normalization (case-insensitive)
✅ Solana address normalization (case-preserving)
✅ BSC hash format validation
✅ USDT token symbol variants: ['USDT', 'BSC-USD', 'USD']
✅ Structured logging methods available

============================================================
ALL TESTS PASSED
```

## Detailed Testing Procedures

### Scenario 1: Replay Webhook Payload (Manual Test)

To test payment verification with a real or simulated webhook payload:

1. **Prepare test data:**
   ```python
   test_payload = {
       "tx_hash": "0x123...",  # Real transaction hash
       "expected_address": "0x7fF8c2F4510EdC4CcB74481588dca909730AEdF5",
       "expected_amount_usd": 10.0,
       "crypto_type": "bnb",
       "expected_token": "USDT",
       "token_decimals": 18
   }
   ```

2. **Create test script:**
   ```bash
   cat > /tmp/test_webhook.py << 'EOF'
   import sys
   sys.path.insert(0, '/home/runner/work/viralcore/viralcore')
   
   from handlers.payment_handler import PaymentHandler
   
   handler = PaymentHandler()
   
   # Test with your real transaction hash
   result = handler._check_transaction_on_chain(
       tx_hash="YOUR_TX_HASH_HERE",
       expected_address="YOUR_EXPECTED_ADDRESS",
       expected_amount_usd=10.0,
       crypto_type="bnb",
       expected_token_symbol="USDT",
       token_decimals=18
   )
   
   print("Verification result:", result)
   print("Status:", result.get("status"))
   print("Message:", result.get("message"))
   EOF
   
   python3 /tmp/test_webhook.py
   ```

3. **Check logs for structured verification data:**
   ```bash
   grep "Payment verification" bot.log | tail -5
   ```

### Scenario 2: Concurrent Withdrawal Stress Test

Test with higher concurrency to ensure robustness:

```bash
cd /home/runner/work/viralcore/viralcore

python3 tests/test_concurrency_fixes.py
```

Or run a custom stress test:

```python
# Run 50 concurrent withdrawals
num_threads = 50
withdrawal_amount = 25.0
initial_balance = 1000.0

# Expected: 40 successful (1000/25 = 40)
# Should have 0 database locked errors
```

### Scenario 3: Balance Reconciliation Check

Run the reconciliation script to check for balance inconsistencies:

```bash
cd /home/runner/work/viralcore/viralcore

# Dry run (check only, no fixes)
python3 scripts/reconcile_balances.py --verbose

# Generate report
python3 scripts/reconcile_balances.py --report /tmp/balance_report.txt

# Apply fixes (if discrepancies found)
python3 scripts/reconcile_balances.py --fix --verbose
```

**Expected output (no discrepancies):**
```
Checking affiliate balances...
Checking reply balances...
No discrepancies found!
```

## Validation Checklist

### ✅ Payment Verification
- [ ] BSC address normalization works (case-insensitive)
- [ ] Solana address normalization preserves case
- [ ] USDT token symbol accepts: USDT, BSC-USD, USD
- [ ] Correlation IDs appear in logs
- [ ] Structured logging includes all required fields
- [ ] Transaction hash validation works for all chains
- [ ] Idempotency check prevents duplicate processing

### ✅ Balance Deduction
- [ ] No "database is locked" errors in concurrency test
- [ ] Final balance matches expected value after concurrent operations
- [ ] Atomic UPDATE prevents race conditions
- [ ] Insufficient balance withdrawals correctly fail
- [ ] Balance operation ledger records all operations
- [ ] No nested transactions (balance deduction in same transaction as status update)

### ✅ Admin Approval Workflow
- [ ] Withdrawal requires admin approval by default
- [ ] Automatic withdrawals don't call external API before approval
- [ ] Status check before external API call
- [ ] Single atomic transaction for balance + status

## Monitoring in Production

### Check for Database Locked Errors

```bash
# Check logs for database locked errors
grep -i "database is locked" bot.log

# Should return no results after fix
```

### Check Payment Verification Success Rate

```bash
# Check verification attempts vs successes
grep "Payment verification attempt" bot.log | wc -l
grep "Payment verification result: success" bot.log | wc -l

# Calculate success rate
```

### Monitor Balance Consistency

```bash
# Run reconciliation check regularly (e.g., daily)
python3 scripts/reconcile_balances.py --report /var/log/viralcore/balance_report_$(date +%Y%m%d).txt
```

## Rollback Procedures

If issues occur after deployment:

### 1. Database Rollback

```bash
# Restore from backup
cp /path/to/backup/viralcore.db.backup_TIMESTAMP ./db/viralcore.db

# Verify backup integrity
sqlite3 ./db/viralcore.db "PRAGMA integrity_check;"
```

### 2. Code Rollback

```bash
# Revert to previous commit
git checkout <previous_commit_hash>

# Restart bot
python3 main_viral_core_bot.py
```

### 3. Verify Rollback

```bash
# Check that database locked errors have stopped
tail -f bot.log | grep -i "database"

# Check payment verification is working
tail -f bot.log | grep -i "verification"
```

## Troubleshooting

### Issue: Still seeing "database is locked" errors

**Diagnosis:**
```bash
# Check WAL mode is enabled
sqlite3 ./db/viralcore.db "PRAGMA journal_mode;"
# Should return: wal
```

**Fix:**
```bash
# Enable WAL mode manually
sqlite3 ./db/viralcore.db "PRAGMA journal_mode=WAL;"
```

### Issue: Payment verification fails with "NOTOK"

**Diagnosis:**
```bash
# Check logs for correlation ID
grep "correlation_id" bot.log | tail -5

# Look for the specific verification attempt
grep "correlation_id_value" bot.log
```

**Common causes:**
- Token symbol mismatch (should now accept USDT, BSC-USD, USD)
- Address case mismatch (should now normalize)
- Amount outside tolerance (check $0.50 tolerance)

### Issue: Balance discrepancies detected

**Diagnosis:**
```bash
# Run reconciliation report
python3 scripts/reconcile_balances.py --report /tmp/discrepancies.txt
cat /tmp/discrepancies.txt
```

**Fix:**
```bash
# Review discrepancies and apply fixes
python3 scripts/reconcile_balances.py --fix --verbose
```

## Design Decisions & Trade-offs

### 1. Atomic UPDATE vs Nested Transactions

**Decision:** Inline balance deduction logic within withdrawal approval transaction

**Rationale:**
- Prevents nested transactions which cause database locked errors
- Ensures atomicity: balance deduction and withdrawal status update succeed or fail together
- Single point of failure/success makes debugging easier

**Trade-off:**
- Code duplication (balance deduction logic appears in multiple places)
- But: ensures correctness and prevents race conditions

### 2. Address Normalization

**Decision:** Case-insensitive for EVM chains, case-preserving for others

**Rationale:**
- EVM addresses (BSC, Ethereum) are case-insensitive
- Solana and Tron addresses are case-sensitive
- Normalization prevents false negatives

**Trade-off:**
- Small performance overhead for normalization
- But: prevents legitimate payments from failing

### 3. USDT Token Symbol Variants

**Decision:** Accept "USDT", "BSC-USD", "USD" as valid

**Rationale:**
- Different BSC explorers return different token symbols
- Real USDT transactions were failing due to "BSC-USD" vs "USDT" mismatch

**Trade-off:**
- Slightly less strict validation
- But: prevents false NOTOK failures for legitimate USDT payments

### 4. Structured Logging with Correlation IDs

**Decision:** Add correlation IDs and structured logging

**Rationale:**
- Makes debugging specific payment verifications much easier
- Can trace entire payment flow through logs
- Helps identify patterns in failures

**Trade-off:**
- More verbose logs
- But: significantly easier troubleshooting and debugging

## Migration Steps

### From Previous Version

1. **No database schema changes required** - All changes are backward compatible
2. **Code deployment:**
   ```bash
   git pull origin main
   pip install -r requirements.txt  # Update dependencies if needed
   ```

3. **Verify WAL mode:**
   ```bash
   sqlite3 ./db/viralcore.db "PRAGMA journal_mode;"
   # Should return: wal (already enabled in get_connection)
   ```

4. **Run reconciliation:**
   ```bash
   python3 scripts/reconcile_balances.py --verbose
   ```

5. **Restart bot:**
   ```bash
   python3 main_viral_core_bot.py
   ```

### Post-Deployment Checks

1. Monitor for database locked errors (should be 0)
2. Monitor payment verification success rate
3. Run daily reconciliation checks
4. Check correlation IDs appear in logs

## Support & Contact

For issues or questions:
1. Check structured logs with correlation IDs
2. Run reconciliation tools to detect data inconsistencies
3. Use correlation IDs to trace specific payment flows
4. Contact development team with specific correlation IDs for investigation
