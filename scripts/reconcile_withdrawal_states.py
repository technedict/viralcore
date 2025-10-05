#!/usr/bin/env python3
"""
Data reconciliation script to fix historical withdrawal records
with inconsistent admin_approval_state.

This script identifies and optionally fixes withdrawals where:
- status is 'completed' or 'processing' but admin_approval_state is still 'pending'
- status is 'rejected' but admin_approval_state is still 'pending'

Usage:
    python3 reconcile_withdrawal_states.py --dry-run     # Show what would be fixed
    python3 reconcile_withdrawal_states.py --fix         # Actually fix the data
"""

import sys
import os
import argparse
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db_utils import get_connection, DB_FILE
from utils.withdrawal_service import AdminApprovalState, WithdrawalStatus


def find_inconsistent_withdrawals():
    """Find withdrawals with inconsistent status and admin_approval_state."""
    
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        
        # Find approved withdrawals with pending approval state
        c.execute('''
            SELECT id, user_id, status, admin_approval_state, admin_id, created_at, updated_at
            FROM withdrawals
            WHERE (status IN ('completed', 'processing') AND admin_approval_state != 'approved')
               OR (status = 'rejected' AND admin_approval_state != 'rejected')
            ORDER BY created_at DESC
        ''')
        
        inconsistent = []
        for row in c.fetchall():
            inconsistent.append({
                'id': row[0],
                'user_id': row[1],
                'status': row[2],
                'admin_approval_state': row[3],
                'admin_id': row[4],
                'created_at': row[5],
                'updated_at': row[6]
            })
        
        return inconsistent


def fix_inconsistent_withdrawals(dry_run=True):
    """Fix inconsistent withdrawal records."""
    
    inconsistent = find_inconsistent_withdrawals()
    
    if not inconsistent:
        print("✅ No inconsistent withdrawal records found!")
        return
    
    print(f"\n{'='*80}")
    print(f"Found {len(inconsistent)} inconsistent withdrawal record(s)")
    print(f"{'='*80}\n")
    
    # Group by type of inconsistency
    approved_inconsistent = [w for w in inconsistent if w['status'] in ('completed', 'processing')]
    rejected_inconsistent = [w for w in inconsistent if w['status'] == 'rejected']
    
    if approved_inconsistent:
        print(f"Approved withdrawals with pending approval state: {len(approved_inconsistent)}")
        for w in approved_inconsistent[:5]:  # Show first 5
            print(f"  - Withdrawal ID {w['id']}: status={w['status']}, approval_state={w['admin_approval_state']}")
        if len(approved_inconsistent) > 5:
            print(f"  ... and {len(approved_inconsistent) - 5} more")
    
    if rejected_inconsistent:
        print(f"\nRejected withdrawals with pending approval state: {len(rejected_inconsistent)}")
        for w in rejected_inconsistent[:5]:  # Show first 5
            print(f"  - Withdrawal ID {w['id']}: status={w['status']}, approval_state={w['admin_approval_state']}")
        if len(rejected_inconsistent) > 5:
            print(f"  ... and {len(rejected_inconsistent) - 5} more")
    
    if dry_run:
        print(f"\n{'='*80}")
        print("DRY RUN MODE - No changes will be made")
        print("Run with --fix to apply changes")
        print(f"{'='*80}\n")
        return
    
    # Apply fixes
    print(f"\n{'='*80}")
    print("Applying fixes...")
    print(f"{'='*80}\n")
    
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        
        # Fix approved withdrawals
        if approved_inconsistent:
            c.execute('''
                UPDATE withdrawals
                SET admin_approval_state = 'approved',
                    updated_at = ?
                WHERE status IN ('completed', 'processing')
                  AND admin_approval_state != 'approved'
                  AND admin_id IS NOT NULL
            ''', (datetime.utcnow().isoformat(),))
            
            print(f"✅ Fixed {c.rowcount} approved withdrawal(s)")
        
        # Fix rejected withdrawals  
        if rejected_inconsistent:
            c.execute('''
                UPDATE withdrawals
                SET admin_approval_state = 'rejected',
                    updated_at = ?
                WHERE status = 'rejected'
                  AND admin_approval_state != 'rejected'
                  AND admin_id IS NOT NULL
            ''', (datetime.utcnow().isoformat(),))
            
            print(f"✅ Fixed {c.rowcount} rejected withdrawal(s)")
        
        conn.commit()
    
    # Verify
    print("\nVerifying fixes...")
    still_inconsistent = find_inconsistent_withdrawals()
    
    if not still_inconsistent:
        print("✅ All inconsistencies resolved!")
    else:
        print(f"⚠️  Warning: {len(still_inconsistent)} withdrawal(s) still inconsistent")
        print("These may require manual review")


def show_stats():
    """Show overall withdrawal statistics."""
    
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        
        print(f"\n{'='*80}")
        print("Withdrawal Statistics")
        print(f"{'='*80}\n")
        
        # Total withdrawals
        c.execute('SELECT COUNT(*) FROM withdrawals')
        total = c.fetchone()[0]
        print(f"Total withdrawals: {total}")
        
        # By status
        c.execute('''
            SELECT status, COUNT(*) 
            FROM withdrawals 
            GROUP BY status
            ORDER BY COUNT(*) DESC
        ''')
        print("\nBy status:")
        for row in c.fetchall():
            print(f"  {row[0]:15} : {row[1]}")
        
        # By approval state
        c.execute('''
            SELECT admin_approval_state, COUNT(*) 
            FROM withdrawals 
            WHERE admin_approval_state IS NOT NULL
            GROUP BY admin_approval_state
            ORDER BY COUNT(*) DESC
        ''')
        print("\nBy approval state:")
        for row in c.fetchall():
            print(f"  {row[0]:15} : {row[1]}")
        
        # Consistency check
        c.execute('''
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status IN ('completed', 'processing') AND admin_approval_state = 'approved' THEN 1 ELSE 0 END) as approved_consistent,
                SUM(CASE WHEN status = 'rejected' AND admin_approval_state = 'rejected' THEN 1 ELSE 0 END) as rejected_consistent
            FROM withdrawals
            WHERE admin_id IS NOT NULL
        ''')
        
        row = c.fetchone()
        total_processed = row[0]
        approved_consistent = row[1]
        rejected_consistent = row[2]
        
        print(f"\nConsistency:")
        print(f"  Total processed: {total_processed}")
        print(f"  Approved & consistent: {approved_consistent}")
        print(f"  Rejected & consistent: {rejected_consistent}")
        
        if total_processed > 0:
            consistency_rate = ((approved_consistent + rejected_consistent) / total_processed) * 100
            print(f"  Consistency rate: {consistency_rate:.1f}%")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Reconcile withdrawal approval states')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be fixed without making changes')
    parser.add_argument('--fix', action='store_true', help='Actually fix inconsistent records')
    parser.add_argument('--stats', action='store_true', help='Show withdrawal statistics')
    
    args = parser.parse_args()
    
    try:
        if args.stats:
            show_stats()
        elif args.fix:
            fix_inconsistent_withdrawals(dry_run=False)
        else:
            # Default to dry run
            fix_inconsistent_withdrawals(dry_run=True)
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
