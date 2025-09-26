#!/usr/bin/env python3
"""
Balance Reconciliation Script
Identifies and optionally fixes mismatched affiliate/reply balances across users.
"""

import sys
import os
import csv
import argparse
import sqlite3
from datetime import datetime
from typing import List, Dict, Any, Tuple

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db_utils import get_connection, DB_FILE, get_affiliate_balance
from ViralMonitor.utils.db import get_total_amount, init_reply_balance_db
from utils.balance_operations import init_operations_ledger

def get_all_users_with_balances() -> List[Dict[str, Any]]:
    """Get all users with their current balances."""
    users = []
    
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT u.id, u.username, u.affiliate_balance,
                   COALESCE(rb.balance, 0) as reply_balance,
                   COALESCE(rb.total_posts, 0) as total_posts
            FROM users u
            LEFT JOIN reply_balances rb ON u.id = rb.user_id
            ORDER BY u.id
        """)
        
        for row in c.fetchall():
            users.append({
                'user_id': row['id'],
                'username': row['username'] or 'N/A',
                'affiliate_balance': row['affiliate_balance'] or 0.0,
                'reply_balance': row['reply_balance'] or 0.0,
                'total_posts': row['total_posts'] or 0
            })
    
    return users

def check_balance_operations_consistency() -> List[Dict[str, Any]]:
    """Check consistency of balance operations in the ledger."""
    issues = []
    
    try:
        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            
            # Check for duplicate operation IDs
            c.execute("""
                SELECT operation_id, COUNT(*) as count
                FROM balance_operations
                GROUP BY operation_id
                HAVING COUNT(*) > 1
            """)
            
            duplicates = c.fetchall()
            for dup in duplicates:
                issues.append({
                    'type': 'duplicate_operation',
                    'operation_id': dup['operation_id'],
                    'count': dup['count'],
                    'severity': 'high'
                })
            
            # Check for operations with invalid user IDs
            c.execute("""
                SELECT DISTINCT bo.user_id, bo.operation_id
                FROM balance_operations bo
                LEFT JOIN users u ON bo.user_id = u.id
                WHERE u.id IS NULL
            """)
            
            invalid_users = c.fetchall()
            for invalid in invalid_users:
                issues.append({
                    'type': 'invalid_user_id',
                    'user_id': invalid['user_id'],
                    'operation_id': invalid['operation_id'],
                    'severity': 'high'
                })
                
    except sqlite3.OperationalError:
        # balance_operations table doesn't exist
        issues.append({
            'type': 'missing_ledger_table',
            'message': 'Balance operations ledger table does not exist',
            'severity': 'medium'
        })
    
    return issues

def detect_balance_discrepancies(users: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Detect potential balance discrepancies."""
    discrepancies = []
    
    for user in users:
        user_id = user['user_id']
        username = user['username']
        affiliate_balance = user['affiliate_balance']
        reply_balance = user['reply_balance']
        
        # Check for negative balances
        if affiliate_balance < 0:
            discrepancies.append({
                'type': 'negative_affiliate_balance',
                'user_id': user_id,
                'username': username,
                'balance': affiliate_balance,
                'severity': 'high'
            })
        
        if reply_balance < 0:
            discrepancies.append({
                'type': 'negative_reply_balance',
                'user_id': user_id,
                'username': username,
                'balance': reply_balance,
                'severity': 'high'
            })
        
        # Check for suspiciously high balances (configurable threshold)
        if affiliate_balance > 10000:  # $10,000 threshold
            discrepancies.append({
                'type': 'high_affiliate_balance',
                'user_id': user_id,
                'username': username,
                'balance': affiliate_balance,
                'severity': 'medium'
            })
        
        if reply_balance > 1000000:  # ₦1,000,000 threshold
            discrepancies.append({
                'type': 'high_reply_balance',
                'user_id': user_id,
                'username': username,
                'balance': reply_balance,
                'severity': 'medium'
            })
    
    return discrepancies

def validate_balance_consistency() -> List[Dict[str, Any]]:
    """Validate balance consistency by re-calculating from source."""
    issues = []
    
    try:
        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            
            # Check affiliate balance consistency with operations ledger
            c.execute("""
                SELECT u.id, u.username, u.affiliate_balance,
                       COALESCE(SUM(CASE WHEN bo.balance_type = 'affiliate' THEN bo.amount ELSE 0 END), 0) as ledger_total
                FROM users u
                LEFT JOIN balance_operations bo ON u.id = bo.user_id AND bo.status = 'completed'
                GROUP BY u.id, u.username, u.affiliate_balance
                HAVING ABS(u.affiliate_balance - ledger_total) > 0.01
            """)
            
            inconsistencies = c.fetchall()
            for inc in inconsistencies:
                issues.append({
                    'type': 'affiliate_balance_mismatch',
                    'user_id': inc['id'],
                    'username': inc['username'] or 'N/A',
                    'current_balance': inc['affiliate_balance'],
                    'expected_balance': inc['ledger_total'],
                    'difference': inc['affiliate_balance'] - inc['ledger_total'],
                    'severity': 'high'
                })
                
    except sqlite3.OperationalError:
        # Operations table doesn't exist, skip this check
        pass
    
    return issues

def generate_csv_report(users: List[Dict[str, Any]], discrepancies: List[Dict[str, Any]], 
                       operations_issues: List[Dict[str, Any]], output_file: str) -> None:
    """Generate CSV report of all findings."""
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if not output_file:
        output_file = f"balance_reconciliation_{timestamp}.csv"
    
    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        
        # Write header
        writer.writerow([
            'Report Type', 'User ID', 'Username', 'Issue Type', 'Severity', 
            'Affiliate Balance', 'Reply Balance', 'Details', 'Timestamp'
        ])
        
        # Write user summary
        for user in users:
            writer.writerow([
                'USER_SUMMARY',
                user['user_id'],
                user['username'],
                'normal',
                'info',
                f"${user['affiliate_balance']:.2f}",
                f"₦{user['reply_balance']:.2f}",
                f"Total posts: {user['total_posts']}",
                timestamp
            ])
        
        # Write discrepancies
        for disc in discrepancies:
            writer.writerow([
                'DISCREPANCY',
                disc.get('user_id', ''),
                disc.get('username', ''),
                disc['type'],
                disc['severity'],
                disc.get('balance', ''),
                '',
                str(disc),
                timestamp
            ])
        
        # Write operations issues
        for issue in operations_issues:
            writer.writerow([
                'OPERATIONS_ISSUE',
                issue.get('user_id', ''),
                '',
                issue['type'],
                issue['severity'],
                '',
                '',
                str(issue),
                timestamp
            ])
    
    print(f"Report generated: {output_file}")

def fix_negative_balances(dry_run: bool = True) -> int:
    """Fix negative balances by setting them to 0."""
    fixes_applied = 0
    
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        
        # Find negative affiliate balances
        c.execute("SELECT id, username, affiliate_balance FROM users WHERE affiliate_balance < 0")
        negative_affiliate = c.fetchall()
        
        for user in negative_affiliate:
            user_id = user['id']
            username = user['username'] or 'N/A'
            balance = user['affiliate_balance']
            
            print(f"{'[DRY RUN] ' if dry_run else ''}Fixing negative affiliate balance for user {user_id} ({username}): ${balance:.2f} -> $0.00")
            
            if not dry_run:
                c.execute("UPDATE users SET affiliate_balance = 0 WHERE id = ?", (user_id,))
                fixes_applied += 1
        
        # Find negative reply balances
        try:
            c.execute("SELECT user_id, balance FROM reply_balances WHERE balance < 0")
            negative_reply = c.fetchall()
            
            for user in negative_reply:
                user_id = user['user_id']
                balance = user['balance']
                
                # Get username
                c.execute("SELECT username FROM users WHERE id = ?", (user_id,))
                username_row = c.fetchone()
                username = username_row['username'] if username_row else 'N/A'
                
                print(f"{'[DRY RUN] ' if dry_run else ''}Fixing negative reply balance for user {user_id} ({username}): ₦{balance:.2f} -> ₦0.00")
                
                if not dry_run:
                    c.execute("UPDATE reply_balances SET balance = 0 WHERE user_id = ?", (user_id,))
                    fixes_applied += 1
                    
        except sqlite3.OperationalError:
            print("Reply balances table not found, skipping reply balance fixes")
        
        if not dry_run:
            conn.commit()
    
    return fixes_applied

def main():
    parser = argparse.ArgumentParser(description='Balance Reconciliation Tool')
    parser.add_argument('--output', '-o', help='Output CSV file name')
    parser.add_argument('--fix', action='store_true', help='Fix issues (not just report them)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be fixed without making changes')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    print("Balance Reconciliation Tool")
    print("=" * 40)
    
    # Initialize databases
    init_reply_balance_db()
    init_operations_ledger()
    
    # Get all users and their balances
    print("Fetching user balances...")
    users = get_all_users_with_balances()
    print(f"Found {len(users)} users")
    
    # Check for discrepancies
    print("Detecting balance discrepancies...")
    discrepancies = detect_balance_discrepancies(users)
    print(f"Found {len(discrepancies)} potential discrepancies")
    
    # Check operations consistency
    print("Checking operations ledger consistency...")
    operations_issues = check_balance_operations_consistency()
    print(f"Found {len(operations_issues)} operations issues")
    
    # Validate balance consistency
    print("Validating balance consistency...")
    consistency_issues = validate_balance_consistency()
    print(f"Found {len(consistency_issues)} consistency issues")
    
    # Combine all issues
    all_issues = discrepancies + operations_issues + consistency_issues
    
    # Print summary
    print("\nSummary:")
    print(f"  Total users: {len(users)}")
    print(f"  Total issues found: {len(all_issues)}")
    
    if args.verbose:
        print("\nDetailed Issues:")
        for issue in all_issues:
            print(f"  - {issue['type']}: {issue}")
    
    # Generate CSV report
    generate_csv_report(users, discrepancies, operations_issues + consistency_issues, args.output)
    
    # Fix issues if requested
    if args.fix or args.dry_run:
        print(f"\n{'Dry run - showing potential fixes:' if args.dry_run else 'Applying fixes:'}")
        fixes_applied = fix_negative_balances(dry_run=args.dry_run)
        
        if args.dry_run:
            print(f"Would apply {fixes_applied} fixes")
        else:
            print(f"Applied {fixes_applied} fixes")
    
    print(f"\nReconciliation complete. Report saved to CSV file.")
    
    # Return appropriate exit code
    return 1 if len(all_issues) > 0 else 0

if __name__ == "__main__":
    exit(main())