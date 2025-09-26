#!/usr/bin/env python3
"""
Export Users CSV Script
Standalone script to export user data to CSV format.
"""

import sys
import os
import csv
import argparse
from datetime import datetime

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db_utils import get_user_metrics
from utils.admin_db_utils import get_all_users

def export_users_csv(output_file: str = None, include_metrics: bool = True) -> str:
    """
    Export all users to CSV format.
    
    Args:
        output_file: Output file path (optional)
        include_metrics: Whether to include user metrics (posts, balances)
    
    Returns:
        Path to the generated CSV file
    """
    users = get_all_users()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if not output_file:
        output_file = f"users_export_{timestamp}.csv"
    
    print(f"Exporting {len(users)} users to {output_file}...")
    
    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        
        # Write header
        header = [
            'User ID', 'Username', 'Referrer ID', 'Affiliate Balance', 
            'Is Admin', 'Is Reply Guy'
        ]
        
        if include_metrics:
            header.extend(['X Posts', 'TG Posts'])
        
        header.append('Export Timestamp')
        writer.writerow(header)
        
        # Write user data
        for u in users:
            user_id = u[0]
            username = u[1] if u[1] else ""
            referrer = u[2] if len(u) > 2 else ""
            affiliate_balance = u[3] if len(u) > 3 else 0.0
            is_admin = u[4] if len(u) > 4 else 0
            is_reply_guy = u[5] if len(u) > 5 else 0
            
            row = [user_id, username, referrer, affiliate_balance, is_admin, is_reply_guy]
            
            if include_metrics:
                try:
                    total_x_posts, total_tg_posts, _ = get_user_metrics(user_id)
                    row.extend([total_x_posts, total_tg_posts])
                except Exception as e:
                    print(f"Warning: Could not get metrics for user {user_id}: {e}")
                    row.extend([0, 0])
            
            row.append(timestamp)
            writer.writerow(row)
    
    print(f"Export completed: {output_file}")
    return output_file

def main():
    parser = argparse.ArgumentParser(description='Export Users to CSV')
    parser.add_argument('--output', '-o', help='Output CSV file path')
    parser.add_argument('--no-metrics', action='store_true', help='Skip user metrics (faster export)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    try:
        output_file = export_users_csv(
            output_file=args.output,
            include_metrics=not args.no_metrics
        )
        
        if args.verbose:
            # Print summary statistics
            with open(output_file, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader)  # Skip header
                rows = list(reader)
                
            print(f"\nExport Summary:")
            print(f"  Total users: {len(rows)}")
            print(f"  Admins: {sum(1 for row in rows if len(row) > 4 and row[4] == '1')}")
            print(f"  Reply guys: {sum(1 for row in rows if len(row) > 5 and row[5] == '1')}")
            print(f"  Users with affiliate balance: {sum(1 for row in rows if len(row) > 3 and row[3] and float(row[3] or 0) > 0)}")
        
        return 0
        
    except Exception as e:
        print(f"Export failed: {e}")
        return 1

if __name__ == "__main__":
    exit(main())