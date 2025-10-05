# Withdrawal Approval State Fix - Runbook

## Issue Summary
**Bug:** After admin approves a withdrawal, the `admin_approval_state` field was not being updated from 'pending' to 'approved', causing data inconsistency in the audit trail.

**Impact:** While withdrawals were correctly removed from the pending list (status was updated), the approval state field remained inconsistent. This could affect:
- Audit trail accuracy
- Any code that relies on `admin_approval_state` for filtering or reporting
- Historical data integrity

## Root Cause

The bug was in `/home/runner/work/viralcore/viralcore/utils/withdrawal_service.py`:

1. **Line 758** in `_approve_withdrawal_manual_mode()`: Updated `withdrawal.status` but not `withdrawal.admin_approval_state`
2. **Line 868** in `_approve_withdrawal_automatic_mode()`: Updated `withdrawal.status` but not `withdrawal.admin_approval_state`

The deprecated `approve_manual_withdrawal()` method (line 429) correctly set both fields, but the newer unified approval methods did not.

## Fix Applied

Added the missing line to both approval methods:
```python
withdrawal.admin_approval_state = AdminApprovalState.APPROVED
```

### Files Changed
1. `utils/withdrawal_service.py` - Added admin_approval_state updates in both approval methods
2. `utils/withdrawal_service.py` - Enhanced audit logging to include approval state transitions
3. `tests/test_withdrawal_approval_state_fix.py` - New comprehensive test suite

## Testing

### Automated Tests
Run the test suite to verify the fix:
```bash
cd /home/runner/work/viralcore/viralcore
python3 -m pytest tests/test_withdrawal_approval_state_fix.py -p no:asyncio -v
```

All 5 tests should pass:
- ✅ `test_manual_mode_sets_admin_approval_state` - Verifies manual mode sets approval state
- ✅ `test_automatic_mode_sets_admin_approval_state` - Verifies automatic mode sets approval state  
- ✅ `test_approved_withdrawal_not_in_pending_list` - Verifies withdrawal removed from pending
- ✅ `test_rejection_sets_admin_approval_state` - Verifies rejection also works correctly
- ✅ `test_idempotent_approval_maintains_state` - Verifies re-approval is idempotent

### Manual Testing Steps

#### Reproduce the Original Bug (Before Fix)
1. Create a test database and user
2. Create a withdrawal request
3. Approve the withdrawal as admin
4. Query the database to check `admin_approval_state` - it would show 'pending' (BUG)

#### Verify the Fix (After Fix)
1. Create a test database and user
2. Create a withdrawal request:
   ```sql
   INSERT INTO withdrawals (user_id, amount_usd, amount_ngn, ..., status, admin_approval_state)
   VALUES (123, 50.0, 75000.0, ..., 'pending', 'pending');
   ```
3. Approve the withdrawal via admin handler
4. Query the database:
   ```sql
   SELECT id, status, admin_approval_state, admin_id, approved_at 
   FROM withdrawals WHERE id = ?;
   ```
   Expected result:
   - `status` = 'completed' (or 'processing' then 'completed' for automatic mode)
   - `admin_approval_state` = 'approved' ✅
   - `admin_id` = admin's user ID
   - `approved_at` = timestamp

#### End-to-End User Flow Test
1. User creates a withdrawal request
2. Admin approves the withdrawal
3. Verify withdrawal no longer appears in pending list
4. Verify user can create a new withdrawal (not blocked)
5. Check audit log for proper state transitions

## Validation Checklist

- [x] After admin approval, withdrawal status is updated correctly
- [x] After admin approval, admin_approval_state is set to 'approved'
- [x] Withdrawal no longer appears in pending list after approval
- [x] Admin ID and approval timestamp are recorded
- [x] Audit log includes state transitions
- [x] Manual mode approval works correctly
- [x] Automatic mode approval works correctly
- [x] Rejection flow continues to work (sets state to 'rejected')
- [x] Idempotent approval (re-approving doesn't cause errors)
- [x] No regressions in existing tests

## Rollback Procedure

If issues are detected after deployment:

### 1. Immediate Rollback
```bash
# Stop the bot
sudo systemctl stop viralcore-bot  # or pkill -f main_viral_core_bot.py

# Revert to previous commit
git checkout main  # or previous stable branch
git log --oneline -10  # find the commit before the fix
git checkout <previous-commit-hash>

# Restart the bot
sudo systemctl start viralcore-bot
```

### 2. Database Rollback (if needed)
The fix only adds a field update; no schema changes were made. Existing data is not affected.

If you need to fix inconsistent historical data:
```sql
-- Update historical records where status is completed but admin_approval_state is still pending
UPDATE withdrawals 
SET admin_approval_state = 'approved'
WHERE status IN ('completed', 'processing') 
  AND admin_approval_state = 'pending' 
  AND admin_id IS NOT NULL;

-- Update historical records where status is rejected but admin_approval_state is still pending  
UPDATE withdrawals
SET admin_approval_state = 'rejected'
WHERE status = 'rejected'
  AND admin_approval_state = 'pending'
  AND admin_id IS NOT NULL;
```

### 3. Monitoring After Rollback
```bash
# Check logs for any errors
tail -f /path/to/bot.log

# Verify withdrawal approvals are working
# Test with a small withdrawal amount
```

## Data Reconciliation

To fix any historical inconsistencies in production data:

```sql
-- Count inconsistent records
SELECT 
    COUNT(*) as inconsistent_count,
    status,
    admin_approval_state
FROM withdrawals
WHERE (status IN ('completed', 'processing') AND admin_approval_state != 'approved')
   OR (status = 'rejected' AND admin_approval_state != 'rejected')
GROUP BY status, admin_approval_state;

-- Fix inconsistent approved withdrawals
UPDATE withdrawals
SET admin_approval_state = 'approved'
WHERE status IN ('completed', 'processing')
  AND admin_approval_state != 'approved'
  AND admin_id IS NOT NULL;

-- Fix inconsistent rejected withdrawals
UPDATE withdrawals
SET admin_approval_state = 'rejected'
WHERE status = 'rejected'
  AND admin_approval_state != 'rejected'
  AND admin_id IS NOT NULL;

-- Verify the fix
SELECT 
    COUNT(*) as total,
    SUM(CASE WHEN status IN ('completed', 'processing') AND admin_approval_state = 'approved' THEN 1 ELSE 0 END) as approved_consistent,
    SUM(CASE WHEN status = 'rejected' AND admin_approval_state = 'rejected' THEN 1 ELSE 0 END) as rejected_consistent
FROM withdrawals
WHERE admin_id IS NOT NULL;
```

## Performance Impact

**Minimal to None:**
- Added one field assignment in memory (no additional DB queries)
- Audit logging already existed, just enhanced with additional fields
- No schema changes
- No new indexes required

## Security & Safety

**Backwards Compatible:**
- No API contract changes
- No schema changes
- Existing withdrawal flows unchanged
- Only internal field consistency improved

**Audit Trail Enhanced:**
- Approval state transitions now properly logged
- Admin ID, timestamp, and correlation ID captured
- Better forensic capability for debugging

## Monitoring Recommendations

Add these monitoring checks post-deployment:

1. **Alert on inconsistent states:**
   ```sql
   SELECT COUNT(*) FROM withdrawals
   WHERE (status IN ('completed', 'processing') AND admin_approval_state != 'approved')
      OR (status = 'rejected' AND admin_approval_state != 'rejected');
   ```
   Alert if count > 0

2. **Track approval latency:**
   Monitor time between withdrawal creation and approval

3. **Audit log completeness:**
   Verify all approvals have corresponding audit entries with state transitions

## Support Contacts

For deployment issues:
1. Check logs with correlation IDs
2. Run validation queries above
3. Contact development team with specific error details and withdrawal IDs

## Success Criteria

Deployment is successful when:
- ✅ Bot starts without errors
- ✅ Withdrawal approval sets both status AND admin_approval_state
- ✅ Withdrawals removed from pending list after approval
- ✅ Audit logs show complete state transitions
- ✅ No increase in approval errors
- ✅ All automated tests pass
- ✅ Manual test approval completes successfully

## Related Documentation

- `WITHDRAWAL_FIXES.md` - Previous withdrawal system improvements
- `tests/test_withdrawal_approval_state_fix.py` - Test documentation
- `utils/withdrawal_service.py` - Implementation details
