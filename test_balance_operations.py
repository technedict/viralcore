#!/usr/bin/env python3
"""
Simple test script for balance operations
"""

import sys
import os
import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.db_utils import init_main_db, create_user, get_affiliate_balance
from ViralMonitor.utils.db import init_reply_balance_db, get_total_amount
from utils.balance_operations import (
    init_operations_ledger, 
    atomic_balance_update,
    atomic_withdraw_operation,
    validate_withdrawal_request
)

def setup_test_environment():
    """Setup test environment with test users."""
    print("Setting up test environment...")
    
    # Initialize databases
    init_main_db()
    init_reply_balance_db()
    init_operations_ledger()
    
    # Create test users
    test_users = [12345, 67890, 99999]
    for user_id in test_users:
        create_user(user_id, f"testuser{user_id}")
        
        # Add some initial balance
        atomic_balance_update(
            user_id=user_id,
            balance_type="affiliate",
            amount=100.0,
            operation_type="test_setup",
            reason="Initial test balance"
        )
        
        atomic_balance_update(
            user_id=user_id,
            balance_type="reply",
            amount=1000.0,
            operation_type="test_setup",
            reason="Initial test reply balance"
        )
    
    print("Test environment setup complete.")
    return test_users

def test_basic_operations():
    """Test basic balance operations."""
    print("\n=== Testing Basic Operations ===")
    
    user_id = 12345
    
    # Test affiliate balance operations
    print(f"Initial affiliate balance: ${get_affiliate_balance(user_id):.2f}")
    
    # Add bonus
    success = atomic_balance_update(
        user_id=user_id,
        balance_type="affiliate",
        amount=50.0,
        operation_type="test_bonus",
        reason="Test bonus"
    )
    print(f"Added $50 bonus: {'Success' if success else 'Failed'}")
    print(f"New affiliate balance: ${get_affiliate_balance(user_id):.2f}")
    
    # Test withdrawal
    success = atomic_withdraw_operation(
        user_id=user_id,
        balance_type="affiliate",
        amount=25.0,
        reason="Test withdrawal"
    )
    print(f"Withdrew $25: {'Success' if success else 'Failed'}")
    print(f"Final affiliate balance: ${get_affiliate_balance(user_id):.2f}")
    
    # Test reply balance operations
    print(f"\nInitial reply balance: ₦{get_total_amount(user_id):.2f}")
    
    success = atomic_withdraw_operation(
        user_id=user_id,
        balance_type="reply",
        amount=200.0,
        reason="Test reply withdrawal"
    )
    print(f"Withdrew ₦200: {'Success' if success else 'Failed'}")
    print(f"Final reply balance: ₦{get_total_amount(user_id):.2f}")

def test_validation():
    """Test withdrawal validation."""
    print("\n=== Testing Validation ===")
    
    user_id = 67890
    current_balance = get_affiliate_balance(user_id)
    
    # Test valid withdrawal
    is_valid, error = validate_withdrawal_request(user_id, "affiliate", 50.0)
    print(f"Valid withdrawal ($50): {'Valid' if is_valid else f'Invalid - {error}'}")
    
    # Test invalid withdrawal (insufficient funds)
    is_valid, error = validate_withdrawal_request(user_id, "affiliate", current_balance + 100)
    print(f"Invalid withdrawal (${current_balance + 100}): {'Valid' if is_valid else f'Invalid - {error}'}")
    
    # Test zero/negative withdrawal
    is_valid, error = validate_withdrawal_request(user_id, "affiliate", 0)
    print(f"Zero withdrawal: {'Valid' if is_valid else f'Invalid - {error}'}")

def concurrent_withdrawal_test(user_id, withdrawal_amount, operation_id_prefix):
    """Helper function for concurrent withdrawal test."""
    operation_id = f"{operation_id_prefix}_{threading.get_ident()}"
    
    success = atomic_withdraw_operation(
        user_id=user_id,
        balance_type="affiliate",
        amount=withdrawal_amount,
        reason=f"Concurrent test withdrawal - {operation_id}",
        operation_id=operation_id
    )
    
    return {
        'thread_id': threading.get_ident(),
        'operation_id': operation_id,
        'success': success,
        'timestamp': time.time()
    }

def test_concurrency():
    """Test concurrent operations to ensure no race conditions."""
    print("\n=== Testing Concurrency ===")
    
    user_id = 99999
    initial_balance = get_affiliate_balance(user_id)
    print(f"Initial balance for concurrency test: ${initial_balance:.2f}")
    
    # Try to withdraw the same amount from multiple threads simultaneously
    withdrawal_amount = 20.0
    num_threads = 5
    
    print(f"Starting {num_threads} concurrent withdrawals of ${withdrawal_amount} each...")
    
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = []
        for i in range(num_threads):
            future = executor.submit(
                concurrent_withdrawal_test, 
                user_id, 
                withdrawal_amount, 
                f"concurrent_test_{i}"
            )
            futures.append(future)
        
        # Wait for all to complete
        results = [future.result() for future in futures]
    
    # Check results
    successful_withdrawals = sum(1 for r in results if r['success'])
    final_balance = get_affiliate_balance(user_id)
    expected_balance = initial_balance - (successful_withdrawals * withdrawal_amount)
    
    print(f"Concurrent withdrawal results:")
    print(f"  Successful withdrawals: {successful_withdrawals}/{num_threads}")
    print(f"  Final balance: ${final_balance:.2f}")
    print(f"  Expected balance: ${expected_balance:.2f}")
    print(f"  Balance consistency: {'✓ PASS' if abs(final_balance - expected_balance) < 0.01 else '✗ FAIL'}")
    
    # Show individual results
    for result in results:
        print(f"  Thread {result['thread_id']}: {'Success' if result['success'] else 'Failed'}")

def test_idempotency():
    """Test idempotency of operations."""
    print("\n=== Testing Idempotency ===")
    
    user_id = 12345
    initial_balance = get_affiliate_balance(user_id)
    operation_id = "idempotency_test_12345"
    withdrawal_amount = 10.0
    
    print(f"Initial balance: ${initial_balance:.2f}")
    
    # Perform the same operation twice with the same operation_id
    success1 = atomic_withdraw_operation(
        user_id=user_id,
        balance_type="affiliate",
        amount=withdrawal_amount,
        reason="Idempotency test",
        operation_id=operation_id
    )
    
    balance_after_first = get_affiliate_balance(user_id)
    
    success2 = atomic_withdraw_operation(
        user_id=user_id,
        balance_type="affiliate",
        amount=withdrawal_amount,
        reason="Idempotency test (duplicate)",
        operation_id=operation_id
    )
    
    final_balance = get_affiliate_balance(user_id)
    
    print(f"First operation: {'Success' if success1 else 'Failed'}")
    print(f"Balance after first: ${balance_after_first:.2f}")
    print(f"Second operation (same ID): {'Success' if success2 else 'Failed'}")
    print(f"Final balance: ${final_balance:.2f}")
    
    # Check if only one withdrawal was processed
    expected_balance = initial_balance - withdrawal_amount
    balance_correct = abs(final_balance - expected_balance) < 0.01
    
    print(f"Idempotency test: {'✓ PASS' if balance_correct else '✗ FAIL'}")
    if not balance_correct:
        print(f"  Expected: ${expected_balance:.2f}, Got: ${final_balance:.2f}")

def main():
    """Run all tests."""
    print("Balance Operations Test Suite")
    print("=" * 40)
    
    try:
        # Setup test environment
        test_users = setup_test_environment()
        
        # Run tests
        test_basic_operations()
        test_validation() 
        test_concurrency()
        test_idempotency()
        
        print("\n" + "=" * 40)
        print("All tests completed!")
        
    except Exception as e:
        print(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())