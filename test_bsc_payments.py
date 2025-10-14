#!/usr/bin/env python3
"""
BSC Payment Diagnostic Tool
Tests BSC payment functionality and identifies issues.
"""

import sys
import os
import json
import requests
from datetime import datetime, timezone

# Add current directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.config import APIConfig
from utils.payment_utils import get_deposit_address, convert_crypto_to_usd
from handlers.payment_handler import PaymentHandler

def test_bsc_configuration():
    """Test BSC configuration and API connectivity."""
    print("=== BSC Configuration Test ===")
    
    # Check API key
    bsc_api_key = APIConfig.BSC_API_KEY
    if not bsc_api_key:
        print("❌ BSC_API_KEY is not set in environment")
        return False
    else:
        print(f"✅ BSC_API_KEY is set: {bsc_api_key[:10]}...")
    
    # Check deposit address
    try:
        deposit_address = get_deposit_address("bsc")
        print(f"✅ BSC deposit address: {deposit_address}")
    except ValueError as e:
        print(f"❌ Failed to get BSC deposit address: {e}")
        return False
    
    # Test BSCScan API connectivity
    print(f"\n=== BSCScan API Connectivity Test ===")
    test_url = "https://api.etherscan.io/v2/api?chainid=56"
    test_params = {
        "module": "stats",
        "action": "bnbprice",
        "apikey": bsc_api_key
    }
    
    try:
        response = requests.get(test_url, params=test_params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get("status") == "1":
            print("✅ BSCScan API is responding correctly")
            print(f"   Current BNB price: ${data.get('result', {}).get('ethusd', 'N/A')}")
        else:
            print(f"❌ BSCScan API error: {data.get('message', 'Unknown error')}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to connect to BSCScan API: {e}")
        return False
    
    return True

def test_bsc_transaction_lookup():
    """Test BSC transaction lookup functionality."""
    print(f"\n=== BSC Transaction Lookup Test ===")
    
    # Test with a known BSC transaction hash (you can replace with a real one)
    test_tx_hash = "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
    test_wallet = get_deposit_address("bsc")
    
    payment_handler = PaymentHandler()
    
    print(f"Testing transaction lookup for:")
    print(f"  TX Hash: {test_tx_hash}")
    print(f"  Wallet: {test_wallet}")
    
    # Test address normalization
    normalized_addr = payment_handler._normalize_address(test_wallet, "bnb")
    print(f"  Normalized address: {normalized_addr}")
    
    # Test hash validation
    is_valid_hash = payment_handler._validate_tx_hash_format(test_tx_hash, "bnb")
    print(f"  Hash format valid: {is_valid_hash}")
    
    if not is_valid_hash:
        print("❌ Transaction hash format validation failed")
        return False
    
    print("✅ Transaction lookup components working")
    return True

def test_usdt_price_conversion():
    """Test USDT/BNB price conversion."""
    print(f"\n=== Price Conversion Test ===")
    
    # Test BNB to USD conversion
    test_bnb_amount = 0.1
    bnb_usd_price = convert_crypto_to_usd(test_bnb_amount, APIConfig.COINGECKO_IDS["bnb"])
    
    if bnb_usd_price is not None:
        print(f"✅ BNB price conversion working: {test_bnb_amount} BNB = ${bnb_usd_price:.2f} USD")
    else:
        print("❌ Failed to convert BNB to USD")
        return False
    
    return True

def test_bsc_api_endpoints():
    """Test different BSCScan API endpoints."""
    print(f"\n=== BSCScan API Endpoints Test ===")
    
    bsc_api_key = APIConfig.BSC_API_KEY
    if not bsc_api_key:
        print("❌ No BSC API key available for testing")
        return False
    
    test_wallet = get_deposit_address("bsc")
    base_url = "https://api.etherscan.io/v2/api?chainid=56"
    
    # Test 1: Token transactions (for USDT)
    print("Testing token transactions endpoint...")
    params1 = {
        "module": "account",
        "action": "tokentx",
        "address": test_wallet,
        "page": 1,
        "offset": 5,
        "sort": "desc",
        "apikey": bsc_api_key
    }
    
    try:
        response = requests.get(base_url, params=params1, timeout=10)
        data = response.json()
        if data.get("status") == "1":
            print(f"✅ Token transactions: Found {len(data.get('result', []))} transactions")
        else:
            print(f"⚠️  Token transactions: {data.get('message', 'No data')}")
    except Exception as e:
        print(f"❌ Token transactions failed: {e}")
    
    # Test 2: Normal transactions (for BNB)
    print("Testing normal transactions endpoint...")
    params2 = {
        "module": "account",
        "action": "txlist",
        "address": test_wallet,
        "page": 1,
        "offset": 5,
        "sort": "desc",
        "apikey": bsc_api_key
    }
    
    try:
        response = requests.get(base_url, params=params2, timeout=10)
        data = response.json()
        if data.get("status") == "1":
            print(f"✅ Normal transactions: Found {len(data.get('result', []))} transactions")
        else:
            print(f"⚠️  Normal transactions: {data.get('message', 'No data')}")
    except Exception as e:
        print(f"❌ Normal transactions failed: {e}")
    
    return True

def diagnose_common_issues():
    """Diagnose common BSC payment issues."""
    print(f"\n=== Common Issues Diagnosis ===")
    
    issues_found = []
    
    # Check 1: Environment variables
    if not os.getenv("BSC_API_KEY"):
        issues_found.append("BSC_API_KEY environment variable not set")
    
    if not os.getenv("BSC_DEPOSIT_ADDRESS"):
        issues_found.append("BSC_DEPOSIT_ADDRESS environment variable not set")
    
    # Check 2: API rate limits
    try:
        bsc_api_key = APIConfig.BSC_API_KEY
        if bsc_api_key:
            # Make a simple API call to check rate limits
            response = requests.get(
                "https://api.etherscan.io/v2/api?chainid=56",
                params={"module": "stats", "action": "bnbprice", "apikey": bsc_api_key},
                timeout=5
            )
            if response.status_code == 429:
                issues_found.append("BSCScan API rate limit exceeded")
    except:
        pass
    
    # Check 3: Network connectivity
    try:
        response = requests.get("https://api.bscscan.com", timeout=5)
        if response.status_code != 200:
            issues_found.append("BSCScan API endpoint not accessible")
    except:
        issues_found.append("Network connectivity issue to BSCScan")
    
    if issues_found:
        print("❌ Issues found:")
        for issue in issues_found:
            print(f"   - {issue}")
    else:
        print("✅ No common issues detected")
    
    return len(issues_found) == 0

def main():
    """Run all BSC payment tests."""
    print("BSC Payment System Diagnostics")
    print("=" * 50)
    
    all_tests_passed = True
    
    # Run all tests
    tests = [
        ("Configuration", test_bsc_configuration),
        ("Transaction Lookup", test_bsc_transaction_lookup),
        ("Price Conversion", test_usdt_price_conversion),
        ("API Endpoints", test_bsc_api_endpoints),
        ("Common Issues", diagnose_common_issues)
    ]
    
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        try:
            result = test_func()
            if not result:
                all_tests_passed = False
        except Exception as e:
            print(f"❌ Test {test_name} failed with exception: {e}")
            all_tests_passed = False
    
    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    
    if all_tests_passed:
        print("✅ All tests passed - BSC payments should be working")
    else:
        print("❌ Some tests failed - BSC payments may have issues")
        print("\nRecommended fixes:")
        print("1. Set BSC_API_KEY environment variable with a valid BSCScan API key")
        print("2. Set BSC_DEPOSIT_ADDRESS environment variable with your BSC wallet address")
        print("3. Check network connectivity to BSCScan API")
        print("4. Verify BSCScan API key has not exceeded rate limits")
        print("5. Check logs for specific transaction verification errors")

if __name__ == "__main__":
    main()