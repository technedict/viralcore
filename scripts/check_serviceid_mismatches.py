#!/usr/bin/env python3
"""
Service ID Mismatch Detection Script

Scans pending jobs and recent boost logs to detect service_id mismatches
where the wrong provider's service_id was used for boost requests.
Provides CSV output and optional safe auto-fix mode.
"""

import sys
import os
import csv
import sqlite3
import json
import argparse
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple, Optional

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db_utils import get_connection, DB_FILE
from utils.boost_provider_utils import PROVIDERS
from utils.logging import get_logger, setup_logging

# Setup logging
setup_logging(console_log_level=20)  # INFO level
logger = get_logger(__name__)


class ServiceMismatch:
    """Represents a detected service ID mismatch."""
    
    def __init__(
        self,
        job_id: str,
        expected_provider: str,
        actual_provider: str,
        service_type: str,
        expected_service_id: int,
        actual_service_id: int,
        created_at: str,
        status: str,
        severity: str = "HIGH"
    ):
        self.job_id = job_id
        self.expected_provider = expected_provider
        self.actual_provider = actual_provider
        self.service_type = service_type
        self.expected_service_id = expected_service_id
        self.actual_service_id = actual_service_id
        self.created_at = created_at
        self.status = status
        self.severity = severity
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for CSV export."""
        return {
            'job_id': self.job_id,
            'expected_provider': self.expected_provider,
            'actual_provider': self.actual_provider,
            'service_type': self.service_type,
            'expected_service_id': self.expected_service_id,
            'actual_service_id': self.actual_service_id,
            'created_at': self.created_at,
            'status': self.status,
            'severity': self.severity
        }


def check_job_table_mismatches() -> List[ServiceMismatch]:
    """Check jobs table for service ID mismatches."""
    
    mismatches = []
    
    try:
        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            
            # Get all jobs with provider snapshots
            c.execute("""
                SELECT job_id, provider_snapshot, created_at, status
                FROM jobs 
                WHERE job_type = 'boost'
                ORDER BY created_at DESC
            """)
            
            rows = c.fetchall()
            
            for row in rows:
                try:
                    snapshot_data = json.loads(row['provider_snapshot'])
                    provider_id = snapshot_data.get('provider_id')
                    
                    if provider_id not in PROVIDERS:
                        logger.warning(f"Unknown provider in job {row['job_id']}: {provider_id}")
                        continue
                    
                    current_provider = PROVIDERS[provider_id]
                    
                    # Check view service ID
                    snapshot_view_id = snapshot_data.get('view_service_id')
                    if snapshot_view_id != current_provider.view_service_id:
                        mismatch = ServiceMismatch(
                            job_id=row['job_id'],
                            expected_provider=provider_id,
                            actual_provider="snapshot",
                            service_type="view",
                            expected_service_id=current_provider.view_service_id,
                            actual_service_id=snapshot_view_id,
                            created_at=row['created_at'],
                            status=row['status'],
                            severity="MEDIUM"  # Snapshot mismatches are less critical
                        )
                        mismatches.append(mismatch)
                    
                    # Check like service ID
                    snapshot_like_id = snapshot_data.get('like_service_id')
                    if snapshot_like_id != current_provider.like_service_id:
                        mismatch = ServiceMismatch(
                            job_id=row['job_id'],
                            expected_provider=provider_id,
                            actual_provider="snapshot",
                            service_type="like",
                            expected_service_id=current_provider.like_service_id,
                            actual_service_id=snapshot_like_id,
                            created_at=row['created_at'],
                            status=row['status'],
                            severity="MEDIUM"
                        )
                        mismatches.append(mismatch)
                        
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON in job {row['job_id']}: {e}")
                    continue
                except Exception as e:
                    logger.error(f"Error processing job {row['job_id']}: {e}")
                    continue
                    
    except Exception as e:
        logger.error(f"Error checking job table: {e}")
    
    return mismatches


def check_log_file_mismatches(log_file: str = "bot.log", days: int = 7) -> List[ServiceMismatch]:
    """Check log files for service ID mismatch patterns."""
    
    mismatches = []
    
    if not os.path.exists(log_file):
        logger.warning(f"Log file not found: {log_file}")
        return mismatches
    
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        with open(log_file, 'r') as f:
            for line_num, line in enumerate(f, 1):
                try:
                    # Look for boost order failures with service ID info
                    if "service_id" in line.lower() and "error" in line.lower():
                        # Try to extract timestamp
                        if line.startswith('20'):  # ISO timestamp
                            timestamp_str = line.split(' ')[0]
                            try:
                                log_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                                if log_time < cutoff_date:
                                    continue
                            except ValueError:
                                pass
                        
                        # This is a simplified pattern matcher
                        # In a real implementation, you'd parse structured logs
                        if "wrong service" in line.lower() or "mismatch" in line.lower():
                            mismatch = ServiceMismatch(
                                job_id=f"log_line_{line_num}",
                                expected_provider="unknown",
                                actual_provider="unknown", 
                                service_type="unknown",
                                expected_service_id=0,
                                actual_service_id=0,
                                created_at=timestamp_str if 'timestamp_str' in locals() else "unknown",
                                status="log_entry",
                                severity="HIGH"
                            )
                            mismatches.append(mismatch)
                            
                except Exception as e:
                    logger.debug(f"Error parsing log line {line_num}: {e}")
                    continue
                    
    except Exception as e:
        logger.error(f"Error reading log file {log_file}: {e}")
    
    return mismatches


def analyze_provider_consistency() -> List[ServiceMismatch]:
    """Analyze current provider configuration consistency."""
    
    mismatches = []
    
    # Check for duplicate service IDs across providers
    service_ids = {}
    
    for provider_name, provider in PROVIDERS.items():
        # Check view service IDs
        view_id = provider.view_service_id
        if view_id in service_ids:
            logger.warning(
                f"Duplicate view service ID {view_id} found in "
                f"{provider_name} and {service_ids[view_id]}"
            )
        else:
            service_ids[view_id] = provider_name
        
        # Check like service IDs  
        like_id = provider.like_service_id
        if like_id in service_ids:
            logger.warning(
                f"Duplicate like service ID {like_id} found in "
                f"{provider_name} and {service_ids[like_id]}"
            )
        else:
            service_ids[like_id] = provider_name
    
    return mismatches


def export_mismatches_csv(mismatches: List[ServiceMismatch], output_file: str):
    """Export mismatches to CSV file."""
    
    if not mismatches:
        logger.info("No mismatches found - no CSV file created")
        return
    
    fieldnames = [
        'job_id', 'expected_provider', 'actual_provider', 'service_type',
        'expected_service_id', 'actual_service_id', 'created_at', 'status', 'severity'
    ]
    
    with open(output_file, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for mismatch in mismatches:
            writer.writerow(mismatch.to_dict())
    
    logger.info(f"Exported {len(mismatches)} mismatches to {output_file}")


def safe_auto_fix(mismatches: List[ServiceMismatch], dry_run: bool = True) -> int:
    """
    Safely auto-fix certain types of mismatches.
    Only fixes low-risk issues and only with explicit opt-in.
    """
    
    fixed_count = 0
    
    for mismatch in mismatches:
        if mismatch.severity == "LOW" and mismatch.status == "queued":
            # Only fix queued jobs with low severity
            if not dry_run:
                try:
                    # Update job status to cancelled with reason
                    with get_connection(DB_FILE) as conn:
                        c = conn.cursor()
                        c.execute("""
                            UPDATE jobs 
                            SET status = 'cancelled', 
                                error_message = 'Auto-cancelled due to service ID mismatch'
                            WHERE job_id = ?
                        """, (mismatch.job_id,))
                        
                        if c.rowcount > 0:
                            fixed_count += 1
                            logger.info(f"Auto-fixed job {mismatch.job_id}")
                        
                except Exception as e:
                    logger.error(f"Failed to auto-fix job {mismatch.job_id}: {e}")
            else:
                logger.info(f"Would auto-fix job {mismatch.job_id} (dry run)")
                fixed_count += 1
    
    return fixed_count


def main():
    """Main function."""
    
    parser = argparse.ArgumentParser(description="Check for service ID mismatches")
    parser.add_argument('--output', '-o', default='serviceid_mismatches.csv',
                       help='Output CSV file path')
    parser.add_argument('--log-file', default='bot.log',
                       help='Log file to analyze')
    parser.add_argument('--days', type=int, default=7,
                       help='Number of days of logs to analyze')
    parser.add_argument('--auto-fix', action='store_true',
                       help='Enable safe auto-fix mode')
    parser.add_argument('--dry-run', action='store_true', default=True,
                       help='Dry run mode (default: true)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Verbose output')
    
    args = parser.parse_args()
    
    if args.verbose:
        logger.setLevel(10)  # DEBUG level
    
    logger.info("Starting service ID mismatch detection...")
    
    all_mismatches = []
    
    # Check job table
    logger.info("Checking jobs table...")
    job_mismatches = check_job_table_mismatches()
    all_mismatches.extend(job_mismatches)
    logger.info(f"Found {len(job_mismatches)} job table mismatches")
    
    # Check log files
    logger.info(f"Checking log file {args.log_file} for last {args.days} days...")
    log_mismatches = check_log_file_mismatches(args.log_file, args.days)
    all_mismatches.extend(log_mismatches)
    logger.info(f"Found {len(log_mismatches)} log file mismatches")
    
    # Analyze provider consistency
    logger.info("Analyzing provider configuration consistency...")
    config_mismatches = analyze_provider_consistency()
    all_mismatches.extend(config_mismatches)
    
    # Summary by severity
    severity_counts = {}
    for mismatch in all_mismatches:
        severity_counts[mismatch.severity] = severity_counts.get(mismatch.severity, 0) + 1
    
    logger.info("Mismatch Summary:")
    for severity, count in severity_counts.items():
        logger.info(f"  {severity}: {count}")
    
    # Export to CSV
    if all_mismatches:
        export_mismatches_csv(all_mismatches, args.output)
    
    # Auto-fix if requested
    if args.auto_fix:
        logger.info("Running auto-fix...")
        fixed_count = safe_auto_fix(all_mismatches, dry_run=args.dry_run)
        mode = "would fix" if args.dry_run else "fixed"
        logger.info(f"Auto-fix {mode} {fixed_count} issues")
    
    logger.info("Service ID mismatch detection completed")
    
    return 0 if not all_mismatches else 1


if __name__ == "__main__":
    exit(main())