# ViralCore Admin Panel - New Features

## Overview

This document describes two major new features added to the ViralCore bot admin panel:

1. **Withdrawal Payment Modes** - Support for both automatic and manual withdrawal processing
2. **Boosting Service Provider Management** - Dynamic editing of likes/views service IDs

## Feature 1: Withdrawal Payment Modes

### What's New

Previously, all withdrawals were processed automatically through Flutterwave. Now admins can choose between:

- **Automatic Mode** (default, backwards compatible)
- **Manual Mode** (requires admin approval)

### How It Works

#### Automatic Withdrawals (Default)
```
User Request → Balance Check → Flutterwave API → Balance Deduction → Complete
```
- Same as before - immediate processing
- Balance deducted only after successful Flutterwave transfer
- No admin intervention required

#### Manual Withdrawals (New)
```
User Request → Balance Check → Admin Notification → Admin Decision → Balance Deduction/Rejection
```
- Balance is **NOT** deducted until admin approval
- Admin receives notification with approval buttons
- Admin can approve (deducts balance) or reject (no balance change)
- All actions are logged for audit

### Database Schema

**New `withdrawals` table:**
```sql
withdrawals (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    amount_usd REAL,
    amount_ngn REAL,
    payment_mode TEXT DEFAULT 'automatic',  -- NEW
    admin_approval_state TEXT,              -- NEW (pending/approved/rejected) 
    admin_id INTEGER,                       -- NEW
    account_name TEXT,
    account_number TEXT,
    bank_name TEXT,
    bank_details_raw TEXT,
    is_affiliate_withdrawal INTEGER,
    status TEXT DEFAULT 'pending',
    approved_at TEXT,                       -- NEW
    processed_at TEXT,                      -- NEW  
    failure_reason TEXT,                    -- NEW
    flutterwave_reference TEXT,
    flutterwave_trace_id TEXT,
    operation_id TEXT,                      -- NEW (for idempotency)
    created_at TEXT,
    updated_at TEXT
)
```

**New `withdrawal_audit_log` table:**
```sql
withdrawal_audit_log (
    id INTEGER PRIMARY KEY,
    withdrawal_id INTEGER,
    admin_id INTEGER,
    action TEXT,                    -- 'created', 'approved', 'rejected'
    old_status TEXT,
    new_status TEXT,
    old_approval_state TEXT,
    new_approval_state TEXT,
    reason TEXT,
    metadata TEXT,                  -- JSON for additional data
    created_at TEXT
)
```

### Admin Interface

**New Admin Panel Menu: "Withdrawal Management"**

1. **📋 Pending Manual Withdrawals**
   - Shows all manual withdrawals awaiting approval
   - Display user info, amount, bank details
   - ✅ Approve or ❌ Reject buttons
   - Shows remaining pending count

2. **📊 Withdrawal Statistics**
   - Total withdrawals by type (automatic/manual)  
   - Completed vs failed counts
   - Total amounts processed
   - Current pending count

3. **🔍 Search Withdrawals** (extensible for future)

### API Changes

**Withdrawal Creation (Backwards Compatible):**
```python
# Existing code continues to work (automatic mode)
withdrawal = withdrawal_service.create_withdrawal(
    user_id=123,
    amount_usd=50.0,
    amount_ngn=75000.0,
    account_name="John Doe",
    account_number="1234567890", 
    bank_name="First Bank",
    bank_details_raw="John Doe, 1234567890, First Bank"
)

# New: Optional payment mode parameter
withdrawal = withdrawal_service.create_withdrawal(
    # ... same parameters ...
    payment_mode=PaymentMode.MANUAL  # NEW
)
```

**Admin Actions:**
```python
# Approve manual withdrawal
success = withdrawal_service.approve_manual_withdrawal(
    withdrawal_id=123,
    admin_id=456,
    reason="Verified bank details"
)

# Reject manual withdrawal  
success = withdrawal_service.reject_manual_withdrawal(
    withdrawal_id=123,
    admin_id=456,
    reason="Invalid bank account"
)
```

### Safety Features

- **Idempotent Operations**: Multiple approval attempts are safe
- **Database Locking**: Prevents race conditions with `SELECT ... FOR UPDATE`
- **Atomic Balance Updates**: Uses existing `atomic_withdraw_operation`
- **Comprehensive Audit Logging**: Every action is tracked
- **Transaction Safety**: All operations wrapped in database transactions

## Feature 2: Boosting Service Provider Management

### What's New

Previously, service IDs for likes/views were hardcoded in `boost_provider_utils.py`. Now they're stored in the database and can be edited by admins through the UI.

### How It Works

#### Before (Hardcoded)
```python
PROVIDERS = {
    "smmflare": ProviderConfig(like_service_id=8646, view_service_id=8381),
    "plugsmms": ProviderConfig(like_service_id=11023, view_service_id=7750),
    "smmstone": ProviderConfig(like_service_id=6662, view_service_id=5480)
}
```

#### After (Database-Driven)
```sql
-- Service types (likes, views, comments)
boosting_services (id, name, service_type, is_active)

-- Provider mappings (flexible per service)
boosting_service_providers (
    service_id,          -- FK to boosting_services
    provider_name,       -- 'smmflare', 'plugsmms', etc.
    provider_service_id, -- The actual ID to send to provider API
    created_by,
    updated_by
)
```

### Database Schema

**New `boosting_services` table:**
```sql
boosting_services (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE,               -- 'Default Likes Service'
    service_type TEXT,              -- 'likes', 'views', 'comments' 
    is_active INTEGER DEFAULT 0,    -- Only one active per type
    created_at TEXT,
    updated_at TEXT
)
```

**New `boosting_service_providers` table:**
```sql
boosting_service_providers (
    id INTEGER PRIMARY KEY,
    service_id INTEGER,             -- FK to boosting_services
    provider_name TEXT,             -- 'smmflare', 'plugsmms', 'smmstone'
    provider_service_id INTEGER,    -- The actual service ID
    created_by INTEGER,             -- Admin who created mapping
    updated_by INTEGER,             -- Admin who last updated
    created_at TEXT,
    updated_at TEXT,
    UNIQUE(service_id, provider_name)
)
```

**New `boosting_service_audit_log` table:**
```sql
boosting_service_audit_log (
    id INTEGER PRIMARY KEY,
    service_provider_id INTEGER,    -- FK to boosting_service_providers
    admin_id INTEGER,
    action TEXT,                    -- 'updated'
    old_provider_service_id INTEGER,
    new_provider_service_id INTEGER, 
    reason TEXT,
    created_at TEXT
)
```

### Migration & Seeding

When the migration runs, it automatically:

1. Creates the new tables
2. Seeds with current provider configurations:
   - Creates "Default Likes Service" and "Default Views Service"
   - Populates mappings from existing `boost_provider_utils.py` configuration
   - Preserves all current service IDs

### Admin Interface

**New Admin Panel Menu: "Service Management"**

1. **📝 Edit Service IDs**
   - Shows current provider/service combinations
   - Click to edit any specific mapping
   - Example: "Edit smmflare likes (8646)"

2. **📊 Current Mappings**
   - Table view of all active service mappings
   - Shows provider name and current service ID
   - Organized by service type (likes/views)

3. **📋 Audit Log**
   - History of all service ID changes
   - Shows who changed what, when, and why
   - Displays old → new values

### Edit Flow

1. Admin clicks "Edit smmflare likes (8646)"
2. System shows current configuration and prompts for new ID
3. Admin enters new service ID (e.g., "9999")
4. System validates the ID format
5. Confirmation screen shows: "smmflare likes: 8646 → 9999"  
6. Admin clicks "Confirm Changes"
7. Update is applied and audit logged

### Validation

**Service ID Validation Rules:**
```python
def validate_provider_service_id(provider_name: str, service_id: int) -> bool:
    # Basic validation
    if not isinstance(service_id, int) or service_id <= 0:
        return False
    
    # Provider-specific rules
    provider_rules = {
        'smmflare': lambda x: 1000 <= x <= 99999,
        'plugsmms': lambda x: 1000 <= x <= 99999, 
        'smmstone': lambda x: 1000 <= x <= 99999,
    }
    
    if provider_name in provider_rules:
        return provider_rules[provider_name](service_id)
    
    # Default for unknown providers
    return 1 <= service_id <= 999999
```

### API Usage

**Get Current Service ID:**
```python
service_manager = get_boosting_service_manager()

# Get service ID for active likes service + smmflare provider
likes_service_id = service_manager.get_provider_service_id(
    ServiceType.LIKES, 
    "smmflare"
)
# Returns: 8646 (or updated value)
```

**Update Service Mapping:**
```python
success = service_manager.update_provider_service_mapping(
    service_id=1,
    provider_name="smmflare", 
    new_provider_service_id=9999,
    admin_id=456,
    reason="Provider updated their service IDs"
)
```

**Get All Current Mappings:**
```python
mappings = service_manager.get_current_provider_mappings_summary()
# Returns:
# {
#   "likes": {"smmflare": 8646, "plugsmms": 11023, "smmstone": 6662},
#   "views": {"smmflare": 8381, "plugsmms": 7750, "smmstone": 5480}
# }
```

## Backwards Compatibility

### ✅ What Stays The Same

**Withdrawal System:**
- All existing withdrawal code continues to work unchanged
- Default behavior is automatic processing (same as before)
- User experience is identical for automatic withdrawals
- Balance operations use same atomic functions

**Boosting System:**
- Existing boost requests continue to work
- Current provider configurations are migrated to database
- Service selection logic remains the same
- No changes to provider API calls

### 🆕 What's New

**Withdrawal System:**
- Optional manual mode for special cases
- Admin approval workflow for manual withdrawals  
- Comprehensive audit logging
- Enhanced balance operation safety

**Boosting System:**
- Dynamic service ID management
- Admin UI for changing provider configurations
- Audit trail for all service changes
- Validation for service ID formats

## Testing

### Included Tests

1. **Unit Tests** (`tests/test_withdrawal_service.py`)
   - Withdrawal creation (automatic/manual)
   - Admin approval/rejection workflows
   - Idempotency testing
   - Audit logging verification

2. **Unit Tests** (`tests/test_boosting_service_manager.py`)
   - Service creation and provider mapping
   - Service ID retrieval and updates
   - Validation logic
   - Audit logging

3. **Integration Tests** (`test_integration.py`)
   - Database migration verification  
   - Schema consistency checks
   - Basic functionality validation

### Manual Testing Checklist

**Withdrawal Features:**
- [ ] Create automatic withdrawal (existing flow)
- [ ] Test manual withdrawal creation and admin notification
- [ ] Approve manual withdrawal and verify balance deduction
- [ ] Reject manual withdrawal and verify no balance change
- [ ] Test concurrent admin actions (idempotency)

**Service Management Features:**
- [ ] View current service mappings
- [ ] Edit a service ID and verify update takes effect
- [ ] Test validation with invalid service IDs
- [ ] Verify audit logging of changes

## Deployment

See `DEPLOYMENT_GUIDE.md` for complete deployment instructions.

**Quick Start:**
```bash
# 1. Backup database
cp viralcore.db viralcore.db.backup

# 2. Run migrations  
python3 scripts/migrate_database.py --backup --apply

# 3. Verify migrations
python3 scripts/migrate_database.py --check

# 4. Test integration
python3 test_integration.py

# 5. Deploy and restart bot
```

## Benefits

### For Admins
- **Flexible Withdrawal Control**: Choose when to require manual approval
- **Better Audit Trail**: Complete history of all withdrawal and service actions
- **Dynamic Configuration**: Change provider service IDs without code deployments
- **Enhanced Security**: Manual approval for suspicious withdrawal requests

### For Users  
- **Same Experience**: Automatic withdrawals work exactly as before
- **Transparency**: Clear status updates for manual withdrawals
- **Reliability**: Improved error handling and recovery

### For Developers
- **Maintainable Code**: Service configurations in database vs hardcoded
- **Extensible Design**: Easy to add new providers or service types
- **Robust Architecture**: Proper transaction handling and race condition prevention
- **Comprehensive Logging**: Full audit trail for debugging and compliance

---

For technical details, see the source code in:
- `utils/withdrawal_service.py` - Withdrawal business logic
- `utils/boosting_service_manager.py` - Service provider management
- `handlers/admin_withdrawal_handlers.py` - Admin withdrawal UI
- `handlers/admin_service_handlers.py` - Admin service management UI