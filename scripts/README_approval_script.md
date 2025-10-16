# Withdrawal Approval Script

## Usage

The `approve_all_pending_withdrawals.py` script allows you to bulk approve all pending withdrawals in the viralcore database.

### Commands

```bash
# Check what withdrawals would be approved (safe preview)
python scripts/approve_all_pending_withdrawals.py --dry-run

# Actually approve all pending withdrawals
python scripts/approve_all_pending_withdrawals.py
```

### What it does

1. **Finds** all withdrawals with `status='pending'`
2. **Displays** withdrawal details including:
   - Withdrawal ID, User ID, Username, X Username  
   - Amount, Payment Mode, Created Date
3. **Saves** all found withdrawals to a CSV file with timestamp
4. **Updates** approved withdrawals to:
   - `status='completed'`
   - `admin_approval_state='approved'`
   - Sets `approved_at`, `processed_at`, and `updated_at` timestamps
   - Sets `admin_id=1` (system admin)
5. **Logs** audit events for each approval
6. **Reports** success/failure counts

### Safety Features

- **Dry-run mode**: Preview changes without making them
- **Username display**: Shows both username and X username for easy identification
- **CSV export**: Automatically saves all pending withdrawals to timestamped CSV file
- **Confirmation prompt**: Requires explicit confirmation before proceeding
- **Atomic transactions**: Each withdrawal is processed in its own transaction
- **Audit logging**: All changes are logged in the `withdrawal_audit_log` table
- **Error handling**: Continues processing even if individual withdrawals fail

### Example Output

```
🔍 Finding pending withdrawals...
📋 Found 2 pending withdrawal(s):

  ID: 24    | User: 888396377  | Username: Dexmile (@dexmile_x)      | Amount: $500.00   | Mode: manual    | Created: 2025-10-16 11:04:13
  ID: 25    | User: 953253201  | Username: jane_chy                  | Amount: $750.00   | Mode: automatic | Created: 2025-10-16 11:07:04

📊 Total amount: $1250.00
💾 Saved withdrawal details to: output/pending_withdrawals_20251016_110733.csv

Are you sure you want to approve 2 withdrawal(s)? (yes/no): yes

🚀 Processing withdrawals...
✅ Approved withdrawal 24
✅ Approved withdrawal 25

📊 Results:
  ✅ Successfully approved: 2
  ❌ Failed: 0

🎉 All withdrawals processed successfully!
```

### Notes

- Run from the `viralcore` directory
- Requires access to the viralcore database
- Only affects withdrawals with `status='pending'`
- Safe to run multiple times (idempotent)