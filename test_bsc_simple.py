#!/usr/bin/env python3
"""
Simple BSC payment test script
"""

import sys
import os
import requests

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.config import APIConfig
from utils.payment_utils import get_deposit_address

def test_bscscan_api():
    """Test BSCScan API connectivity and functionality."""
    print("Testing BSCScan API...")
    
    api_key = APIConfig.BSC_API_KEY
    deposit_address = get_deposit_address("bsc")
    
    print(f"API Key: {api_key[:10]}...")
    print(f"Deposit Address: {deposit_address}")
    
    # Test 1: Get account balance
    print("\n1. Testing account balance...")
    balance_url = "https://api.etherscan.io/v2/api?chainid=56"
    balance_params = {
        "module": "account",
        "action": "balance",
        "address": deposit_address,
        "tag": "latest",
        "apikey": api_key
    }
    
    try:
        response = requests.get(balance_url, params=balance_params, timeout=10)
        data = response.json()
        if data.get("status") == "1":
            balance_wei = int(data.get("result", 0))
            balance_bnb = balance_wei / 10**18
            print(f"✅ Account balance: {balance_bnb:.6f} BNB")
        else:
            print(f"❌ Balance check failed: {data.get('message')}")
    except Exception as e:
        print(f"❌ Balance check error: {e}")
    
    # Test 2: Get recent transactions
    print("\n2. Testing recent transactions...")
    tx_url = "https://api.etherscan.io/v2/api?chainid=56"
    tx_params = {
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
    
    try:
        response = requests.get(tx_url, params=tx_params, timeout=10)
        data = response.json()
        if data.get("status") == "1":
            transactions = data.get("result", [])
            print(f"✅ Found {len(transactions)} recent transactions")
            for i, tx in enumerate(transactions[:3]):
                print(f"   TX {i+1}: {tx.get('hash')[:20]}... ({tx.get('value')} wei)")
        else:
            print(f"❌ Transaction check failed: {data}")
    except Exception as e:
        print(f"❌ Transaction check error: {e}")
    
    # Test 3: Get token transactions (USDT)
    print("\n3. Testing token transactions (USDT)...")
    token_params = {
        "module": "account",
        "action": "tokentx",
        "address": deposit_address,
        "page": 1,
        "offset": 5,
        "sort": "desc",
        "apikey": api_key
    }
    
    try:
        response = requests.get(tx_url, params=token_params, timeout=10)
        data = response.json()
        if data.get("status") == "1":
            token_txs = data.get("result", [])
            print(f"✅ Found {len(token_txs)} recent token transactions")
            for i, tx in enumerate(token_txs[:3]):
                symbol = tx.get("tokenSymbol", "Unknown")
                value = tx.get("value", "0")
                print(f"   Token TX {i+1}: {symbol} - {value}")
        else:
            print(f"❌ Token transaction check failed: {data.get('message')}")
    except Exception as e:
        print(f"❌ Token transaction check error: {e}")

def test_payment_handler():
    """Test payment handler BSC functionality."""
    print("\n" + "="*50)
    print("Testing Payment Handler BSC Functions...")
    
    try:
        from handlers.payment_handler import PaymentHandler
        handler = PaymentHandler()
        
        # Test address normalization
        test_addr = "0x7fF8c2F4510EdC4CcB74481588dca909730AEdF5"
        normalized = handler._normalize_address(test_addr, "bnb")
        print(f"✅ Address normalization: {test_addr} -> {normalized}")
        
        # Test hash validation
        test_hash = "0x" + "a" * 64
        is_valid = handler._validate_tx_hash_format(test_hash, "bnb")
        print(f"✅ Hash validation: {test_hash[:20]}... -> {is_valid}")
        
    except Exception as e:
        print(f"❌ Payment handler test error: {e}")

if __name__ == "__main__":
    print("BSC Payment System Test")
    print("=" * 50)
    
    test_bscscan_api()
    test_payment_handler()
    
    print("\n" + "="*50)
    print("Test completed. Check above for any errors.")