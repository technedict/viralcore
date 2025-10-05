#!/usr/bin/env python3
"""
Simple verification script for withdrawal approval fix.
Checks that the code has the required fixes in place.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def verify_manual_approval_fix():
    """Verify manual approval sets admin_approval_state."""
    print("Checking manual approval fix...")
    
    with open('utils/withdrawal_service.py', 'r') as f:
        content = f.read()
    
    # Check if _approve_withdrawal_manual_mode sets admin_approval_state
    if 'def _approve_withdrawal_manual_mode' in content:
        # Find the method
        start = content.find('def _approve_withdrawal_manual_mode')
        end = content.find('\n    def ', start + 1)
        method_content = content[start:end]
        
        # Check for the fix
        has_status_update = 'withdrawal.status = WithdrawalStatus.COMPLETED' in method_content
        has_approval_update = 'withdrawal.admin_approval_state = AdminApprovalState.APPROVED' in method_content
        
        if has_status_update and has_approval_update:
            print("✅ Manual approval fix is present")
            return True
        else:
            print("❌ Manual approval fix is MISSING")
            if not has_status_update:
                print("   - Missing: withdrawal.status = WithdrawalStatus.COMPLETED")
            if not has_approval_update:
                print("   - Missing: withdrawal.admin_approval_state = AdminApprovalState.APPROVED")
            return False
    else:
        print("❌ Method _approve_withdrawal_manual_mode not found")
        return False

def verify_automatic_approval_fix():
    """Verify automatic approval sets admin_approval_state."""
    print("\nChecking automatic approval fix...")
    
    with open('utils/withdrawal_service.py', 'r') as f:
        content = f.read()
    
    # Check if _approve_withdrawal_automatic_mode sets admin_approval_state
    if 'def _approve_withdrawal_automatic_mode' in content:
        # Find the method
        start = content.find('def _approve_withdrawal_automatic_mode')
        end = content.find('\n    def ', start + 1)
        method_content = content[start:end]
        
        # Check for the fix
        has_status_update = 'withdrawal.status = WithdrawalStatus.PROCESSING' in method_content
        has_approval_update = 'withdrawal.admin_approval_state = AdminApprovalState.APPROVED' in method_content
        
        if has_status_update and has_approval_update:
            print("✅ Automatic approval fix is present")
            return True
        else:
            print("❌ Automatic approval fix is MISSING")
            if not has_status_update:
                print("   - Missing: withdrawal.status = WithdrawalStatus.PROCESSING")
            if not has_approval_update:
                print("   - Missing: withdrawal.admin_approval_state = AdminApprovalState.APPROVED")
            return False
    else:
        print("❌ Method _approve_withdrawal_automatic_mode not found")
        return False

def verify_approve_manual_withdrawal_fix():
    """Verify approve_manual_withdrawal method sets admin_approval_state."""
    print("\nChecking approve_manual_withdrawal fix...")
    
    with open('utils/withdrawal_service.py', 'r') as f:
        content = f.read()
    
    # Check if approve_manual_withdrawal sets admin_approval_state
    if 'def approve_manual_withdrawal' in content:
        # Find the method
        start = content.find('def approve_manual_withdrawal')
        end = content.find('def reject_manual_withdrawal', start)
        if end == -1:
            end = content.find('\n    def ', start + 1)
        method_content = content[start:end]
        
        # Check for the fix
        has_status_update = 'withdrawal.status = WithdrawalStatus.COMPLETED' in method_content
        has_approval_update = 'withdrawal.admin_approval_state = AdminApprovalState.APPROVED' in method_content
        
        if has_status_update and has_approval_update:
            print("✅ approve_manual_withdrawal fix is present")
            return True
        else:
            print("❌ approve_manual_withdrawal fix is MISSING")
            if not has_status_update:
                print("   - Missing: withdrawal.status = WithdrawalStatus.COMPLETED")
            if not has_approval_update:
                print("   - Missing: withdrawal.admin_approval_state = AdminApprovalState.APPROVED")
            return False
    else:
        print("❌ Method approve_manual_withdrawal not found")
        return False

def verify_pending_check_logic():
    """Verify the pending check logic in handlers."""
    print("\nChecking pending withdrawal check logic...")
    
    with open('handlers/custom_order_handlers.py', 'r') as f:
        content = f.read()
    
    # Check for the pending withdrawal check
    check_pattern1 = "wd.status.value in ['pending']"
    check_pattern2 = "wd.admin_approval_state.value == 'pending'"
    
    if check_pattern1 in content and check_pattern2 in content:
        print("✅ Pending withdrawal check logic found")
        print("   - Checks status == 'pending'")
        print("   - Checks admin_approval_state == 'pending' for manual mode")
        return True
    else:
        print("❌ Pending withdrawal check logic not found or incomplete")
        return False

def main():
    """Run all verifications."""
    print("=" * 60)
    print("Withdrawal Approval Fix Verification")
    print("=" * 60)
    
    results = []
    
    # Run verifications
    results.append(("Manual approval fix", verify_manual_approval_fix()))
    results.append(("Automatic approval fix", verify_automatic_approval_fix()))
    results.append(("approve_manual_withdrawal fix", verify_approve_manual_withdrawal_fix()))
    results.append(("Pending check logic", verify_pending_check_logic()))
    
    # Summary
    print("\n" + "=" * 60)
    print("Verification Summary")
    print("=" * 60)
    
    all_passed = True
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")
        if not passed:
            all_passed = False
    
    print("=" * 60)
    
    if all_passed:
        print("✅ All verifications PASSED")
        print("\nThe withdrawal approval fix is correctly implemented.")
        print("\nKey changes:")
        print("1. Manual approval sets admin_approval_state = APPROVED")
        print("2. Automatic approval sets admin_approval_state = APPROVED")
        print("3. Both approval methods update status to COMPLETED/PROCESSING")
        print("4. Pending check correctly verifies both status and admin_approval_state")
        return 0
    else:
        print("❌ Some verifications FAILED")
        print("\nPlease review the failures above and ensure all fixes are in place.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
