#!/usr/bin/env python3
"""
Performance audit script for ViralCore bot.
Identifies performance bottlenecks and optimization opportunities.
"""

import os
import sys
import sqlite3
import time
from typing import List, Dict, Any

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db_utils import get_connection, DB_FILE

def analyze_database_performance():
    """Analyze database performance and suggest optimizations."""
    print("Database Performance Analysis")
    print("=" * 40)
    
    optimizations = []
    
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        
        # Check if indexes exist
        c.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = [row[0] for row in c.fetchall()]
        
        print(f"Existing indexes: {len(indexes)}")
        for idx in indexes:
            if not idx.startswith('sqlite_'):  # Skip system indexes
                print(f"  - {idx}")
        
        # Check table sizes
        tables = ['users', 'purchases', 'processed_transactions']
        for table in tables:
            try:
                c.execute(f"SELECT COUNT(*) FROM {table}")
                count = c.fetchone()[0]
                print(f"{table}: {count} records")
                
                if count > 1000:
                    optimizations.append(f"Consider partitioning {table} table (>{count} records)")
                    
            except sqlite3.OperationalError:
                print(f"{table}: Table does not exist")
        
        # Check for missing indexes on foreign keys
        c.execute("PRAGMA table_info(purchases)")
        purchases_columns = c.fetchall()
        
        if 'idx_purchases_user_id' not in indexes:
            optimizations.append("Add index on purchases.user_id for better JOIN performance")
            
        # Analyze query patterns
        print("\nQuery Performance Recommendations:")
        
        # Check for potential N+1 patterns
        print("- Use batch queries instead of loops where possible")
        print("- Consider connection pooling for high-concurrency scenarios")
        print("- Use EXPLAIN QUERY PLAN for complex queries")
        
    return optimizations

def check_async_opportunities():
    """Check for opportunities to convert sync to async operations."""
    print("\nAsync Optimization Opportunities")
    print("=" * 40)
    
    opportunities = []
    
    # Check for sync HTTP requests in async contexts
    files_to_check = [
        'utils/payment_utils.py',
        'handlers/payment_handler.py', 
        'utils/link_utils.py'
    ]
    
    for file_path in files_to_check:
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                content = f.read()
                
            if 'requests.' in content and 'async def' in content:
                opportunities.append(f"{file_path}: Mix of sync requests and async functions")
            elif 'requests.' in content:
                print(f"{file_path}: Uses sync requests (OK if not in async context)")
                
    if opportunities:
        print("Consider converting to aiohttp for:")
        for opp in opportunities:
            print(f"  - {opp}")
    else:
        print("✓ Good separation of sync/async HTTP operations")
    
    return opportunities

def memory_usage_analysis():
    """Analyze potential memory usage issues."""
    print("\nMemory Usage Analysis")
    print("=" * 40)
    
    recommendations = []
    
    # Check for potential memory leaks
    print("Memory optimization recommendations:")
    print("- Use connection context managers (already implemented ✓)")
    print("- Avoid loading large datasets into memory at once")
    print("- Use generators for large data processing")
    print("- Monitor connection pool size in production")
    
    # Check for large data operations
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        
        try:
            c.execute("SELECT COUNT(*) FROM purchases")
            purchase_count = c.fetchone()[0]
            
            if purchase_count > 10000:
                recommendations.append(f"Large purchases table ({purchase_count}). Consider pagination for bulk operations.")
                
        except sqlite3.OperationalError:
            pass
    
    return recommendations

def generate_performance_report():
    """Generate comprehensive performance report."""
    print("ViralCore Performance Audit Report")
    print("=" * 50)
    
    db_optimizations = analyze_database_performance()
    async_opportunities = check_async_opportunities()
    memory_recommendations = memory_usage_analysis()
    
    print("\n" + "=" * 50)
    print("SUMMARY & RECOMMENDATIONS")
    print("=" * 50)
    
    all_recommendations = []
    
    if db_optimizations:
        print("\nDatabase Optimizations:")
        for opt in db_optimizations:
            print(f"  • {opt}")
            all_recommendations.append(f"DB: {opt}")
    else:
        print("\n✅ Database: Well optimized")
    
    if async_opportunities:
        print("\nAsync Opportunities:")
        for opp in async_opportunities:
            print(f"  • {opp}")
            all_recommendations.append(f"Async: {opp}")
    else:
        print("\n✅ Async: Good sync/async separation")
    
    if memory_recommendations:
        print("\nMemory Optimizations:")
        for rec in memory_recommendations:
            print(f"  • {rec}")
            all_recommendations.append(f"Memory: {rec}")
    else:
        print("\n✅ Memory: No immediate concerns")
    
    print(f"\nTotal recommendations: {len(all_recommendations)}")
    
    if len(all_recommendations) == 0:
        print("\n🎉 Excellent! No critical performance issues found.")
    elif len(all_recommendations) <= 3:
        print("\n👍 Good performance profile with minor optimizations available.")
    else:
        print("\n⚠️  Several optimization opportunities identified.")
    
    return all_recommendations

if __name__ == "__main__":
    recommendations = generate_performance_report()
    
    # Write recommendations to file
    with open("performance_audit_report.md", "w") as f:
        f.write("# ViralCore Performance Audit Report\n\n")
        f.write(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        if recommendations:
            f.write("## Recommendations\n\n")
            for i, rec in enumerate(recommendations, 1):
                f.write(f"{i}. {rec}\n")
        else:
            f.write("## Status\n\n✅ No performance issues identified.\n")
    
    print(f"\nDetailed report saved to: performance_audit_report.md")