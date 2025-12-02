#!/usr/bin/env python3
"""
Script to approve all pending withdrawals in the viralcore database.

This script will:
1. Find all withdrawals with status='pending'
2. Update them to status='completed' and admin_approval_state='approved'
3. Set appropriate timestamps
4. Log the operations for audit purposes

Usage:
    python scripts/approve_all_pending_withdrawals.py [--dry-run]
    
Options:
    --dry-run: Show what would be updated without making changes
"""

import sys
import os
import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path

# Add the parent directory to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.db_utils import get_connection, DB_FILE
from utils.withdrawal_service import WithdrawalStatus, AdminApprovalState

def get_pending_withdrawals():
    """Get all pending withdrawals from the database with usernames."""
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('''
            SELECT w.id, w.user_id, u.username, u.x_username, w.amount_usd, 
                   w.payment_mode, w.status, w.admin_approval_state, w.created_at
            FROM withdrawals w
            LEFT JOIN users u ON w.user_id = u.id
            WHERE w.status = 'pending'
            ORDER BY w.created_at ASC
        ''')
        
        withdrawals = []
        for row in c.fetchall():
            withdrawals.append(dict(row))
        
        return withdrawals

def save_withdrawals_to_csv(withdrawals, filename=None):
    """Save withdrawals to CSV file."""
    if not filename:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"pending_withdrawals_{timestamp}.csv"
    
    # Create output directory if it doesn't exist
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    filepath = output_dir / filename
    
    with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['id', 'user_id', 'username', 'x_username', 'amount_usd', 
                     'payment_mode', 'status', 'admin_approval_state', 'created_at']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        writer.writeheader()
        for withdrawal in withdrawals:
            writer.writerow(withdrawal)
    
    return str(filepath)

def format_username_display(username, x_username):
    """Format username for display."""
    if username and x_username:
        return f"{username} (@{x_username})"
    elif username:
        return username
    elif x_username:
        return f"@{x_username}"
    else:
        return "N/A"

def approve_withdrawal(withdrawal_id: int, dry_run: bool = False):
    """Approve a single withdrawal."""
    current_time = datetime.now(timezone.utc).isoformat()
    
    if dry_run:
        print(f"[DRY RUN] Would approve withdrawal {withdrawal_id}")
        return True
    
    with get_connection(DB_FILE) as conn:
        try:
            conn.execute('BEGIN IMMEDIATE')
            c = conn.cursor()
            
            # Update withdrawal to completed/approved status
            c.execute('''
                UPDATE withdrawals 
                SET status = ?, 
                    admin_approval_state = ?, 
                    approved_at = ?, 
                    processed_at = ?,
                    updated_at = ?,
                    admin_id = 1
                WHERE id = ? AND status = 'pending'
            ''', (
                WithdrawalStatus.COMPLETED.value,
                AdminApprovalState.APPROVED.value,
                current_time,
                current_time,
                current_time,
                withdrawal_id
            ))
            
            if c.rowcount == 0:
                print(f"Warning: No rows updated for withdrawal {withdrawal_id} (may have been already processed)")
                conn.rollback()
                return False
            
            # Log audit event
            c.execute('''
                INSERT INTO withdrawal_audit_log (
                    withdrawal_id, admin_id, action, old_status, new_status,
                    old_approval_state, new_approval_state, reason, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                withdrawal_id,
                1,  # System admin ID
                "bulk_approved",
                "pending",
                WithdrawalStatus.COMPLETED.value,
                "pending", 
                AdminApprovalState.APPROVED.value,
                "Bulk approval via script",
                '{"script": "approve_all_pending_withdrawals.py", "bulk_operation": true}'
            ))
            
            conn.commit()
            print(f"✅ Approved withdrawal {withdrawal_id}")
            return True
            
        except Exception as e:
            conn.rollback()
            print(f"❌ Failed to approve withdrawal {withdrawal_id}: {str(e)}")
            return False

def main():
    parser = argparse.ArgumentParser(description="Approve all pending withdrawals")
    parser.add_argument("--dry-run", action="store_true", 
                       help="Show what would be updated without making changes")
    args = parser.parse_args()
    
    # Check if database exists
    if not os.path.exists(DB_FILE):
        print(f"❌ Database file not found: {DB_FILE}")
        print("Make sure you're running this script from the viralcore directory")
        sys.exit(1)
    
    # Get all pending withdrawals
    print("🔍 Finding pending withdrawals...")
    try:
        pending_withdrawals = get_pending_withdrawals()
    except Exception as e:
        print(f"❌ Error accessing database: {str(e)}")
        sys.exit(1)
    
    if not pending_withdrawals:
        print("✅ No pending withdrawals found!")
        sys.exit(0)
    
    print(f"📋 Found {len(pending_withdrawals)} pending withdrawal(s):")
    print()
    
    # Display pending withdrawals with usernames
    total_amount = 0
    for w in pending_withdrawals:
        username_display = format_username_display(w.get('username'), w.get('x_username'))
        print(f"  ID: {w['id']:<5} | User: {w['user_id']:<10} | Username: {username_display:<25} | Amount: ${w['amount_usd']:<8.2f} | Mode: {w['payment_mode']:<9} | Created: {w['created_at']}")
        total_amount += w['amount_usd']
    
    print()
    print(f"📊 Total amount: ${total_amount:.2f}")
    
    # Save to CSV
    csv_file = save_withdrawals_to_csv(pending_withdrawals)
    print(f"💾 Saved withdrawal details to: {csv_file}")
    print()
    
    if args.dry_run:
        print("🔍 DRY RUN MODE - No changes will be made")
        print("Run without --dry-run to actually approve these withdrawals")
        return
    
    # Confirm before proceeding
    try:
        confirm = input(f"Are you sure you want to approve {len(pending_withdrawals)} withdrawal(s)? (yes/no): ").strip().lower()
        if confirm not in ['yes', 'y']:
            print("❌ Operation cancelled")
            sys.exit(0)
    except KeyboardInterrupt:
        print("\n❌ Operation cancelled")
        sys.exit(0)
    
    # Process withdrawals
    print("\n🚀 Processing withdrawals...")
    successful = 0
    failed = 0
    
    for withdrawal in pending_withdrawals:
        if approve_withdrawal(withdrawal['id'], dry_run=args.dry_run):
            successful += 1
        else:
            failed += 1
    
    print(f"\n📊 Results:")
    print(f"  ✅ Successfully approved: {successful}")
    print(f"  ❌ Failed: {failed}")
    
    if failed == 0:
        print("\n🎉 All withdrawals processed successfully!")
    else:
        print(f"\n⚠️  {failed} withdrawal(s) failed to process. Check the errors above.")
        sys.exit(1)

if __name__ == "__main__":
    main()