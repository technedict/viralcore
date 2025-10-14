#!/usr/bin/env python3
"""
Comprehensive payment system test including referrals
"""

import sys
import os
import asyncio
import sqlite3
from unittest.mock import Mock, patch

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.db_utils import (
    create_user, get_user, update_affiliate_balance, 
    get_referrer, save_purchase, get_connection, DB_FILE
)
from utils.payment_utils import convert_usd_to_crypto, get_deposit_address
from handlers.payment_handler import PaymentHandler

def setup_test_users():
    """Create test users for payment testing."""
    print("Setting up test users...")
    
    # Create referrer
    referrer_id = 111111
    referrer_username = "test_referrer"
    create_user(referrer_id, referrer_username)
    
    # Create referee  
    referee_id = 222222
    referee_username = "test_referee"
    create_user(referee_id, referee_username, referrer_id)
    
    print(f"✅ Created referrer: ID={referrer_id}, username={referrer_username}")
    print(f"✅ Created referee: ID={referee_id}, username={referee_username}, referrer={referrer_id}")
    
    return referrer_id, referee_id

def test_referral_lookup():
    """Test referral lookup functionality."""
    print("\n=== Testing Referral Lookup ===")
    
    referrer_id, referee_id = setup_test_users()
    
    # Test get_referrer function
    referrer_data = get_referrer(referee_id)
    if referrer_data:
        print(f"✅ Referrer found for user {referee_id}: {referrer_data}")
        if referrer_data['id'] == referrer_id:
            print(f"✅ Referrer ID matches expected: {referrer_id}")
        else:
            print(f"❌ Referrer ID mismatch: expected {referrer_id}, got {referrer_data['id']}")
    else:
        print(f"❌ No referrer found for user {referee_id}")
    
    return referrer_id, referee_id

def test_affiliate_bonus():
    """Test affiliate bonus calculation and assignment."""
    print("\n=== Testing Affiliate Bonus ===")
    
    referrer_id, referee_id = setup_test_users()
    
    # Get initial balance
    referrer_before = get_user(referrer_id)
    initial_balance = referrer_before['affiliate_balance']
    print(f"Initial referrer balance: ${initial_balance:.2f}")
    
    # Simulate a payment amount
    payment_amount_usd = 50.0
    bonus_percentage = 0.10  # 10%
    expected_bonus = payment_amount_usd * bonus_percentage
    
    print(f"Payment amount: ${payment_amount_usd:.2f}")
    print(f"Expected bonus (10%): ${expected_bonus:.2f}")
    
    # Apply bonus
    update_affiliate_balance(referrer_id, expected_bonus)
    
    # Check new balance
    referrer_after = get_user(referrer_id)
    new_balance = referrer_after['affiliate_balance']
    actual_bonus = new_balance - initial_balance
    
    print(f"New referrer balance: ${new_balance:.2f}")
    print(f"Actual bonus applied: ${actual_bonus:.2f}")
    
    if abs(actual_bonus - expected_bonus) < 0.01:  # Allow for small floating point differences
        print(f"✅ Affiliate bonus applied correctly")
    else:
        print(f"❌ Affiliate bonus mismatch: expected ${expected_bonus:.2f}, got ${actual_bonus:.2f}")

def test_payment_verification():
    """Test payment verification process."""
    print("\n=== Testing Payment Verification ===")
    
    try:
        # Test crypto conversion
        usd_amount = 25.0
        crypto_info = convert_usd_to_crypto(usd_amount, "bnb")
        print(f"✅ USD to BNB conversion: ${usd_amount} = {crypto_info}")
        
        # Test deposit address
        bnb_address = get_deposit_address("bnb")
        usdt_address = get_deposit_address("usdt_bsc")
        print(f"✅ BNB deposit address: {bnb_address}")
        print(f"✅ USDT-BSC deposit address: {usdt_address}")
        
    except Exception as e:
        print(f"❌ Payment verification test error: {e}")

async def test_payment_handler_integration():
    """Test the full payment handler integration."""
    print("\n=== Testing Payment Handler Integration ===")
    
    referrer_id, referee_id = setup_test_users()
    
    try:
        # Create mock update and context objects
        mock_update = Mock()
        mock_update.effective_user.id = referee_id
        mock_update.effective_user.username = "test_referee"
        mock_update.effective_chat.id = referee_id
        
        mock_context = Mock()
        mock_context.bot.send_message = Mock()
        
        # Create payment handler
        handler = PaymentHandler()
        
        # Test parameters
        payment_amount = 100.0
        test_tx_hash = "0x" + "a" * 64
        
        print(f"Testing payment verification for ${payment_amount} from user {referee_id}")
        
        # Test the payment verification method
        with patch('handlers.payment_handler.PaymentHandler._verify_bsc_transaction') as mock_verify:
            mock_verify.return_value = (True, payment_amount, "bnb")
            
            # Get initial balances
            referrer_before = get_user(referrer_id)
            initial_referrer_balance = referrer_before['affiliate_balance']
            
            print(f"Initial referrer balance: ${initial_referrer_balance:.2f}")
            
            # Mock the payment verification process
            await handler._verify_and_process_payment(
                update=mock_update,
                context=mock_context,
                payment_type="crypto",
                received_amount_usd=payment_amount,
                invoice_id="test_invoice_123",
                transaction_hash=test_tx_hash,
                current_plan_type="premium",
                ordered_quantity=100
            )
            
            # Check if referrer received bonus
            referrer_after = get_user(referrer_id)
            final_referrer_balance = referrer_after['affiliate_balance']
            bonus_received = final_referrer_balance - initial_referrer_balance
            expected_bonus = payment_amount * 0.10
            
            print(f"Final referrer balance: ${final_referrer_balance:.2f}")
            print(f"Bonus received: ${bonus_received:.2f}")
            print(f"Expected bonus: ${expected_bonus:.2f}")
            
            if abs(bonus_received - expected_bonus) < 0.01:
                print(f"✅ Payment handler integration successful")
            else:
                print(f"❌ Payment handler integration failed: bonus mismatch")
                
    except Exception as e:
        print(f"❌ Payment handler integration error: {e}")

def test_purchase_recording():
    """Test that purchases are properly recorded."""
    print("\n=== Testing Purchase Recording ===")
    
    referrer_id, referee_id = setup_test_users()
    
    # Test purchase data
    purchase_data = {
        'user_id': referee_id,
        'plan_type': 'premium',
        'quantity': 100,
        'amount_paid_usd': 50.0,
        'payment_method': 'crypto_bnb',
        'transaction_hash': '0x' + 'b' * 64,
        'invoice_id': 'test_invoice_456'
    }
    
    try:
        # Save purchase
        save_purchase(**purchase_data)
        print(f"✅ Purchase saved for user {referee_id}")
        
        # Verify purchase was saved
        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("""
                SELECT * FROM purchases 
                WHERE user_id = ? AND invoice_id = ?
            """, (referee_id, purchase_data['invoice_id']))
            
            purchase_record = c.fetchone()
            if purchase_record:
                print(f"✅ Purchase record found: {dict(purchase_record)}")
            else:
                print(f"❌ Purchase record not found")
                
    except Exception as e:
        print(f"❌ Purchase recording error: {e}")

def test_database_consistency():
    """Test database consistency for referrals and payments."""
    print("\n=== Testing Database Consistency ===")
    
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        
        # Check for users with referrers
        c.execute("SELECT COUNT(*) FROM users WHERE referrer IS NOT NULL")
        users_with_referrers = c.fetchone()[0]
        print(f"Users with referrers: {users_with_referrers}")
        
        # Check for purchases with referrer bonuses
        c.execute("""
            SELECT COUNT(*) FROM purchases p
            JOIN users u ON p.user_id = u.id
            WHERE u.referrer IS NOT NULL
        """)
        purchases_with_referrers = c.fetchone()[0]
        print(f"Purchases from referred users: {purchases_with_referrers}")
        
        # Check affiliate balance totals
        c.execute("SELECT SUM(affiliate_balance) FROM users WHERE affiliate_balance > 0")
        total_affiliate_balance = c.fetchone()[0] or 0
        print(f"Total affiliate balance in system: ${total_affiliate_balance:.2f}")

def cleanup_test_data():
    """Clean up test data."""
    print("\n=== Cleaning up test data ===")
    
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        
        # Delete test purchases
        c.execute("DELETE FROM purchases WHERE invoice_id LIKE 'test_invoice_%'")
        purchases_deleted = c.rowcount
        
        # Delete test users
        c.execute("DELETE FROM users WHERE id IN (111111, 222222)")
        users_deleted = c.rowcount
        
        conn.commit()
        
        print(f"Deleted {purchases_deleted} test purchases")
        print(f"Deleted {users_deleted} test users")

async def main():
    """Run all payment system tests."""
    print("🧪 PAYMENT SYSTEM COMPREHENSIVE TEST")
    print("=" * 60)
    
    try:
        # Run tests
        test_referral_lookup()
        test_affiliate_bonus()
        test_payment_verification()
        test_purchase_recording()
        await test_payment_handler_integration()
        test_database_consistency()
        
        print("\n" + "=" * 60)
        print("✅ All payment system tests completed!")
        print("\nIf you see any ❌ errors above, those indicate issues that need fixing.")
        
    except Exception as e:
        print(f"\n❌ Test suite error: {e}")
        
    finally:
        # Always clean up
        cleanup_test_data()

if __name__ == "__main__":
    asyncio.run(main())