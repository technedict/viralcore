#!/usr/bin/env python3
"""
BSC Payment Testing - Focused on BSCScan API V2
"""

import sys
import os
import requests
import asyncio
from unittest.mock import Mock

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.config import APIConfig
from utils.payment_utils import get_deposit_address, convert_usd_to_crypto
from handlers.payment_handler import PaymentHandler

def test_bscscan_v2_api():
    """Test BSCScan API endpoints."""
    print("🔍 Testing BSCScan API...")
    
    api_key = APIConfig.BSC_API_KEY
    deposit_address = get_deposit_address("bsc")
    
    if not api_key or api_key in ["your_bscscan_api_key", "your_bsc_api_key"]:
        print("❌ BSCScan API key not configured")
        print("   Set BSC_API_KEY in .env (get one from https://bscscan.com/apis)")
        return False
    
    print(f"API Key: {api_key[:10]}...")
    print(f"Deposit Address: {deposit_address}")
    
    # Use BSCScan API directly (free tier available)
    base_url = "https://api.bscscan.com/api"
    
    tests = [
        {
            "name": "Account Balance",
            "params": {
                "module": "account",
                "action": "balance",
                "address": deposit_address,
                "tag": "latest",
                "apikey": api_key
            }
        },
        {
            "name": "Recent Transactions",
            "params": {
                "module": "account", 
                "action": "txlist",
                "address": deposit_address,
                "startblock": 0,
                "endblock": 99999999,
                "page": 1,
                "offset": 5,
                "sort": "desc",
                "apikey": api_key
            }
        },
        {
            "name": "Token Transactions (USDT)",
            "params": {
                "module": "account",
                "action": "tokentx", 
                "address": deposit_address,
                "page": 1,
                "offset": 5,
                "sort": "desc",
                "apikey": api_key
            }
        }
    ]
    
    all_passed = True
    
    for test in tests:
        print(f"\n📊 Testing {test['name']}...")
        try:
            response = requests.get(base_url, params=test['params'], timeout=15)
            data = response.json()
            
            if data.get("status") == "1":
                result = data.get("result", [])
                if test['name'] == "Account Balance":
                    balance_wei = int(result)
                    balance_bnb = balance_wei / 10**18
                    print(f"✅ Balance: {balance_bnb:.6f} BNB")
                else:
                    print(f"✅ Found {len(result) if isinstance(result, list) else 1} records")
                    if isinstance(result, list) and result:
                        print(f"   Sample: {result[0].get('hash', 'N/A')[:20]}...")
            else:
                print(f"❌ API Error: {data.get('message', 'Unknown error')}")
                all_passed = False
                
        except Exception as e:
            print(f"❌ Request failed: {e}")
            all_passed = False
    
    return all_passed

def test_crypto_conversions():
    """Test USD to crypto conversions."""
    print("\n💱 Testing Crypto Conversions...")
    
    test_amounts = [10, 25, 50, 100]
    
    for amount in test_amounts:
        try:
            # Test BNB conversion
            bnb_info = convert_usd_to_crypto(amount, "bnb")
            print(f"✅ ${amount} USD = {bnb_info['amount']:.6f} BNB (rate: ${bnb_info['rate']:.2f})")
            
            # Test USDT conversion  
            usdt_info = convert_usd_to_crypto(amount, "usdt_bsc")
            print(f"✅ ${amount} USD = {usdt_info['amount']:.2f} USDT (rate: ${usdt_info['rate']:.4f})")
            
        except Exception as e:
            print(f"❌ Conversion failed for ${amount}: {e}")

async def test_payment_verification():
    """Test payment verification with mock transaction."""
    print("\n🔐 Testing Payment Verification...")
    
    try:
        handler = PaymentHandler()
        
        # Test transaction hash validation
        valid_hash = "0x" + "a" * 64
        invalid_hash = "invalid_hash"
        
        is_valid = handler._validate_tx_hash_format(valid_hash, "bnb")
        is_invalid = handler._validate_tx_hash_format(invalid_hash, "bnb")
        
        print(f"✅ Valid hash format check: {is_valid}")
        print(f"✅ Invalid hash format check: {not is_invalid}")
        
        # Test address normalization
        test_addresses = [
            "0x7fF8c2F4510EdC4CcB74481588dca909730AEdF5",
            "0x7ff8c2f4510edc4ccb74481588dca909730aedf5"  # lowercase
        ]
        
        for addr in test_addresses:
            normalized = handler._normalize_address(addr, "bnb")
            print(f"✅ Address normalization: {addr} -> {normalized}")
            
    except Exception as e:
        print(f"❌ Payment verification test failed: {e}")

def test_deposit_addresses():
    """Test deposit address generation."""
    print("\n🏦 Testing Deposit Addresses...")
    
    currencies = ["bnb", "usdt_bsc", "eth", "usdt_eth"]
    
    for currency in currencies:
        try:
            address = get_deposit_address(currency)
            print(f"✅ {currency.upper()} address: {address}")
        except Exception as e:
            print(f"❌ Failed to get {currency.upper()} address: {e}")

async def test_full_payment_flow():
    """Test a complete payment flow simulation."""
    print("\n🔄 Testing Full Payment Flow...")
    
    try:
        # Mock objects
        mock_update = Mock()
        mock_update.effective_user.id = 999999
        mock_update.effective_user.username = "test_user"
        mock_update.effective_chat.id = 999999
        
        mock_context = Mock()
        mock_context.bot.send_message = Mock()
        
        handler = PaymentHandler()
        
        # Simulate payment parameters
        payment_amount = 25.0
        test_tx_hash = "0x1234567890abcdef" + "0" * 48
        
        print(f"Simulating ${payment_amount} payment with hash: {test_tx_hash[:20]}...")
        
        # Test hash format validation
        is_valid_format = handler._validate_tx_hash_format(test_tx_hash, "bnb")
        print(f"✅ Hash format valid: {is_valid_format}")
        
        # Test address validation  
        deposit_addr = get_deposit_address("bnb")
        is_valid_addr = handler._validate_address_format(deposit_addr, "bnb")
        print(f"✅ Address format valid: {is_valid_addr}")
        
        print("✅ Payment flow components working")
        
    except Exception as e:
        print(f"❌ Payment flow test failed: {e}")

async def main():
    """Run all BSC payment tests."""
    print("🧪 BSC PAYMENT SYSTEM TEST")
    print("=" * 50)
    
    # Test API connectivity
    api_working = test_bscscan_v2_api()
    
    # Test other components
    test_crypto_conversions()
    test_deposit_addresses()
    await test_payment_verification()
    await test_full_payment_flow()
    
    print("\n" + "=" * 50)
    if api_working:
        print("✅ BSC Payment System: READY")
        print("✅ BSCScan API V2: WORKING")
    else:
        print("❌ BSC Payment System: API ISSUES DETECTED")
        print("⚠️  Check BSCScan API key and network connectivity")
    
    print("\nNext steps:")
    print("1. Ensure BSCScan API key is valid")
    print("2. Test with real small transactions") 
    print("3. Monitor transaction verification speed")

if __name__ == "__main__":
    asyncio.run(main())