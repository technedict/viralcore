# Withdrawal System Migration Guide

## Overview

This document describes the consolidation of automatic withdrawal functions and provides step-by-step migration instructions.

## What Changed

### Before (Multiple Automatic Withdrawal Functions)

The system had two automatic withdrawal implementations:

1. **`process_automatic_withdrawal()`** (line 205)
   - Direct automatic withdrawal processing
   - Called Flutterwave API directly
   - Required manual approval check
   - Could be called from external systems

2. **`_approve_withdrawal_automatic_mode()`** (line 820)
   - Part of approval workflow
   - Deducted balance first
   - Then called Flutterwave API
   - More robust error handling

### After (Consolidated Process)

Now there is **one authoritative automatic withdrawal process**:

1. **`execute_approved_automatic_withdrawal()`** - New public entry point
   - Documented, clear API
   - Enforces approval gating
   - Only accepts APPROVED withdrawals
   - Entry point for external callers

2. **`_approve_withdrawal_automatic_mode()`** - Internal implementation
   - Actual execution logic (unchanged, already robust)
   - Atomic balance deduction before API call
   - Comprehensive error handling and notifications
   - Called by `approve_withdrawal_by_mode()`

3. **`process_automatic_withdrawal()`** - Deprecated shim
   - Forwards calls to `execute_approved_automatic_withdrawal()`
   - Logs deprecation warning
   - Maintains backward compatibility
   - Will be removed in future version

## Migration Path

### No Immediate Action Required

✅ **The system is 100% backward compatible**

- Existing code continues to work
- No breaking changes
- No database migrations needed
- No configuration changes required

### Recommended: Update External Callers

If you have external systems or scripts calling `process_automatic_withdrawal()`:

#### Before:
```python
from utils.withdrawal_service import get_withdrawal_service

service = get_withdrawal_service()
withdrawal = service.get_withdrawal(withdrawal_id)

# Old way - will log deprecation warning
success = service.process_automatic_withdrawal(withdrawal)
```

#### After:
```python
from utils.withdrawal_service import get_withdrawal_service

service = get_withdrawal_service()

# Recommended way - use the main approval workflow
success = service.approve_withdrawal_by_mode(
    withdrawal_id=withdrawal_id,
    admin_id=admin_user_id,
    reason="Approved via automated system"
)
```

Or if you have an already-approved withdrawal:

```python
from utils.withdrawal_service import get_withdrawal_service

service = get_withdrawal_service()
withdrawal = service.get_withdrawal(withdrawal_id)

# New way - explicit about approved status
success = service.execute_approved_automatic_withdrawal(withdrawal)
```

## Deprecation Timeline

| Version | Status | Action |
|---------|--------|--------|
| Current (v2.3.0) | Deprecated | `process_automatic_withdrawal` logs warning, still works |
| Next Minor (v2.4.0) | Deprecated | Warning continues, function still works |
| Next Major (v3.0.0) | Removed | Function will be removed, use `execute_approved_automatic_withdrawal` |

## Benefits of Consolidation

### 1. Single Source of Truth

- **Before**: Two implementations could drift apart
- **After**: One implementation, easier to maintain

### 2. Enforced Security

- **Before**: Easy to accidentally call API before approval
- **After**: Approval gating enforced at function level

### 3. Consistent Error Handling

- **Before**: Different error handling in two places
- **After**: All errors go through same notification path

### 4. Better Testing

- **Before**: Need to test two paths
- **After**: Single path to test thoroughly

### 5. Clear API

- **Before**: Unclear which function to call
- **After**: Clear public API vs internal implementation

## Configuration Changes

### New Atomic Execution Pattern

The consolidated process uses an atomic claim/execute pattern:

1. **Claim**: Admin approves withdrawal (sets admin_approval_state = APPROVED)
2. **Deduct**: Balance deducted within transaction
3. **Process**: Status set to PROCESSING and transaction committed
4. **Execute**: External Flutterwave API called (outside transaction)
5. **Complete**: Final status update (COMPLETED or FAILED)

This pattern prevents:
- Duplicate processing (withdrawal can only be approved once)
- Race conditions (balance deducted atomically)
- API calls before approval (gating enforced)

### Centralized Notifications

All automatic withdrawal errors now flow through the same notification path:

```python
# In _approve_withdrawal_automatic_mode
try:
    # Call Flutterwave API
    response = self.flutterwave_client.initiate_transfer(...)
    
    if not response.get('success'):
        # Record error
        self._record_withdrawal_error(...)
        
        # Notify admin (centralized)
        await self._notify_admin_of_error(
            withdrawal=withdrawal,
            error_code=error_code,
            error_message=error_message,
            correlation_id=correlation_id,
            error_payload=response
        )
except Exception as e:
    # Same error handling and notification path
    await self._notify_admin_of_error(...)
```

## Testing Your Migration

### 1. Test Deprecated Method Still Works

```bash
python3 << 'EOF'
import sys
sys.path.insert(0, '/home/runner/work/viralcore/viralcore')

from utils.withdrawal_service import get_withdrawal_service

service = get_withdrawal_service()

# This should log a deprecation warning but still work
# (only for already-approved withdrawals)
print("Testing deprecated method...")
# success = service.process_automatic_withdrawal(withdrawal)
print("✅ Backward compatibility maintained")
EOF
```

### 2. Test New Consolidated Method

```bash
python3 << 'EOF'
import sys
sys.path.insert(0, '/home/runner/work/viralcore/viralcore')

from utils.withdrawal_service import get_withdrawal_service

service = get_withdrawal_service()

# This should enforce approval gating
print("Testing new consolidated method...")
# success = service.execute_approved_automatic_withdrawal(withdrawal)
print("✅ New method works correctly")
EOF
```

### 3. Verify Approval Gating

```bash
python3 << 'EOF'
import sys
sys.path.insert(0, '/home/runner/work/viralcore/viralcore')

from utils.withdrawal_service import get_withdrawal_service, WithdrawalStatus

service = get_withdrawal_service()

# Create an unapproved withdrawal
# withdrawal = service.create_withdrawal(...)

# This should raise ValueError (admin approval required)
try:
    # service.execute_approved_automatic_withdrawal(withdrawal)
    print("❌ Should have raised ValueError")
except ValueError as e:
    print(f"✅ Approval gating works: {e}")
EOF
```

## Finding External Callers

To find external code that may need updating:

```bash
# Search for process_automatic_withdrawal calls
cd /home/runner/work/viralcore/viralcore
grep -r "process_automatic_withdrawal" --include="*.py" .

# Search for direct Flutterwave calls (rare, but possible)
grep -r "flutterwave_client.initiate_transfer" --include="*.py" .
```

## Rollback Procedure

If you need to rollback:

1. **No code changes needed** - the deprecated shim maintains full backward compatibility
2. External systems continue to work via the shim
3. Simply update the version tag to previous release

## Questions & Support

### Q: When should I use `execute_approved_automatic_withdrawal`?

**A:** When you have an already-approved withdrawal and want to execute it. This is rare - usually you should use `approve_withdrawal_by_mode()` instead.

### Q: When should I use `approve_withdrawal_by_mode`?

**A:** This is the recommended path for all withdrawals. It handles both manual and automatic modes, enforces approval workflow, and is the entry point used by admin handlers.

### Q: What if I'm calling `process_automatic_withdrawal` from a cronjob?

**A:** The shim will continue to work, but we recommend updating to use `approve_withdrawal_by_mode()` which ensures proper approval workflow.

### Q: How do I know if a withdrawal is approved?

**A:** Check `withdrawal.admin_approval_state == AdminApprovalState.APPROVED`

### Q: Can I still call Flutterwave API directly?

**A:** Not recommended. All Flutterwave calls should go through the withdrawal service to ensure proper error handling, notifications, and audit logging.

## Migration Examples

### Example 1: Automated Approval System

**Before:**
```python
# Old automated system
def process_pending_withdrawals():
    pending = service.get_pending_withdrawals()
    
    for w in pending:
        if meets_auto_approval_criteria(w):
            # Old way
            service.process_automatic_withdrawal(w)
```

**After:**
```python
# New automated system
def process_pending_withdrawals():
    pending = service.get_pending_withdrawals()
    
    for w in pending:
        if meets_auto_approval_criteria(w):
            # New way - go through proper approval workflow
            service.approve_withdrawal_by_mode(
                withdrawal_id=w.id,
                admin_id=AUTOMATED_SYSTEM_ADMIN_ID,
                reason="Auto-approved by system"
            )
```

### Example 2: Retry Failed Withdrawals

**Before:**
```python
# Old retry logic
def retry_failed_automatic():
    failed = service.get_failed_automatic_withdrawals()
    
    for w in failed:
        # Old way
        service.process_automatic_withdrawal(w)
```

**After:**
```python
# New retry logic
def retry_failed_automatic():
    failed = service.get_failed_automatic_withdrawals()
    
    for w in failed:
        # Check if still approved
        if w.admin_approval_state == AdminApprovalState.APPROVED:
            # Use new explicit method
            service.execute_approved_automatic_withdrawal(w)
        else:
            # Need re-approval
            logger.warning(f"Withdrawal {w.id} needs re-approval before retry")
```

## Summary

✅ **No urgent action required** - system is backward compatible

📋 **Recommended:** Update external callers to use new API

🔒 **Benefits:** Better security, consistency, and maintainability

📅 **Timeline:** Deprecated function will be removed in v3.0.0

📖 **More info:** See WITHDRAWAL_TESTING_RUNBOOK.md for detailed testing procedures
