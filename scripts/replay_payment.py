#!/usr/bin/env python3
"""
Payment verification replay script for debugging NOTOK failures.
Replays payment verification with detailed output.
"""

import sys
import os
import argparse
import json
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from handlers.payment_handler import PaymentHandler
from utils.logging import setup_logging, get_logger
import logging

# Setup logging for detailed output
setup_logging(
    console_log_level=logging.DEBUG,
    use_structured_format=False
)
logger = get_logger(__name__)


def replay_verification(
    tx_hash: str,
    expected_address: str,
    expected_amount_usd: float,
    crypto_type: str,
    expected_token: str = None,
    token_decimals: int = 18
):
    """
    Replay a payment verification with detailed logging.
    
    Args:
        tx_hash: Transaction hash to verify
        expected_address: Expected recipient address
        expected_amount_usd: Expected amount in USD
        crypto_type: Crypto type (bnb, sol, trx, aptos)
        expected_token: Expected token symbol (for token transfers)
        token_decimals: Token decimals (default: 18)
    """
    print("=" * 80)
    print("PAYMENT VERIFICATION REPLAY")
    print("=" * 80)
    print(f"Transaction Hash: {tx_hash}")
    print(f"Expected Address: {expected_address}")
    print(f"Expected Amount USD: ${expected_amount_usd}")
    print(f"Crypto Type: {crypto_type}")
    print(f"Expected Token: {expected_token or 'Native'}")
    print(f"Token Decimals: {token_decimals}")
    print(f"Timestamp: {datetime.utcnow().isoformat()}")
    print("=" * 80)
    print()
    
    # Create payment handler
    handler = PaymentHandler()
    
    # Validate transaction hash format
    print("Step 1: Validating transaction hash format...")
    is_valid_format = handler._validate_tx_hash_format(tx_hash, crypto_type)
    print(f"  Format valid: {is_valid_format}")
    if not is_valid_format:
        print("  ❌ INVALID FORMAT - Verification will fail")
        return False
    print("  ✅ Format is valid")
    print()
    
    # Normalize addresses
    print("Step 2: Normalizing addresses...")
    normalized_expected = handler._normalize_address(expected_address, crypto_type)
    print(f"  Original: {expected_address}")
    print(f"  Normalized: {normalized_expected}")
    print()
    
    # Perform verification
    print("Step 3: Performing on-chain verification...")
    print("  (This may take a few seconds...)")
    print()
    
    result = handler._check_transaction_on_chain(
        tx_hash=tx_hash,
        expected_address=expected_address,
        expected_amount_usd=expected_amount_usd,
        crypto_type=crypto_type,
        expected_token_symbol=expected_token,
        token_decimals=token_decimals
    )
    
    # Print result
    print("=" * 80)
    print("VERIFICATION RESULT")
    print("=" * 80)
    print(f"Status: {result.get('status', 'unknown')}")
    print(f"Message: {result.get('message', 'No message')}")
    print()
    
    if result.get("transaction"):
        tx = result["transaction"]
        print("Transaction Details:")
        print(f"  From: {tx.get('from', 'N/A')}")
        print(f"  To: {tx.get('to', 'N/A')}")
        print(f"  Value (crypto): {tx.get('value', 'N/A')}")
        print(f"  Value (USD): ${tx.get('value_usd', 'N/A')}")
        print(f"  Confirmations: {tx.get('confirmations', 'N/A')}")
        print(f"  Timestamp: {tx.get('timestamp', 'N/A')}")
        print()
    
    # Print detailed JSON for debugging
    print("Full Result (JSON):")
    print(json.dumps(result, indent=2))
    print()
    
    # Verdict
    print("=" * 80)
    if result.get("status") == "success":
        print("✅ VERIFICATION PASSED")
    else:
        print("❌ VERIFICATION FAILED")
        print()
        print("Common Causes:")
        print("  1. Address mismatch (check normalization)")
        print("  2. Amount mismatch (check tolerance: ±$0.50)")
        print("  3. Transaction too old (check age limit)")
        print("  4. Token symbol mismatch (check accepted variants)")
        print("  5. Network/API error (check logs above)")
    print("=" * 80)
    
    return result.get("status") == "success"


def main():
    parser = argparse.ArgumentParser(
        description="Replay payment verification for debugging NOTOK failures"
    )
    parser.add_argument("tx_hash", help="Transaction hash")
    parser.add_argument("address", help="Expected recipient address")
    parser.add_argument("amount", type=float, help="Expected amount in USD")
    parser.add_argument(
        "crypto_type",
        choices=["bnb", "sol", "trx", "aptos"],
        help="Cryptocurrency type"
    )
    parser.add_argument(
        "--token",
        help="Expected token symbol (e.g., USDT)",
        default=None
    )
    parser.add_argument(
        "--decimals",
        type=int,
        help="Token decimals (default: 18)",
        default=18
    )
    
    args = parser.parse_args()
    
    success = replay_verification(
        tx_hash=args.tx_hash,
        expected_address=args.address,
        expected_amount_usd=args.amount,
        crypto_type=args.crypto_type,
        expected_token=args.token,
        token_decimals=args.decimals
    )
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
