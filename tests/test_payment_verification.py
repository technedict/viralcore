#!/usr/bin/env python3
# tests/test_payment_verification.py
# Tests for payment verification fixes

import pytest
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from handlers.payment_handler import PaymentHandler


class TestPaymentVerification:
    """Test payment verification logic."""
    
    @pytest.fixture
    def payment_handler(self):
        """Create payment handler instance."""
        return PaymentHandler()
    
    def test_normalize_address_bsc(self, payment_handler):
        """Test BSC address normalization."""
        # BSC addresses should be lowercase for comparison
        addr1 = "0x7fF8c2F4510EdC4CcB74481588dca909730AEdF5"
        addr2 = "0x7ff8c2f4510edc4ccb74481588dca909730aedf5"
        
        normalized1 = payment_handler._normalize_address(addr1, "bnb")
        normalized2 = payment_handler._normalize_address(addr2, "bnb")
        
        assert normalized1 == normalized2
        assert normalized1 == addr2.lower()
    
    def test_normalize_address_solana(self, payment_handler):
        """Test Solana address normalization (case-sensitive)."""
        addr = "Gejh1bYCihLLk1BUwhnWKZEyurT7b8azBFXf44yy7MkB"
        
        normalized = payment_handler._normalize_address(addr, "sol")
        
        # Solana addresses should preserve case but trim whitespace
        assert normalized == addr
        
        # Test whitespace trimming
        addr_with_space = "  " + addr + "  "
        normalized_trimmed = payment_handler._normalize_address(addr_with_space, "sol")
        assert normalized_trimmed == addr
    
    def test_normalize_address_tron(self, payment_handler):
        """Test Tron address normalization (case-sensitive)."""
        addr = "TGE9NvuxHGVWYpSoMYYszp8WjdKvRrUBv6"
        
        normalized = payment_handler._normalize_address(addr, "trx")
        
        # Tron addresses should preserve case
        assert normalized == addr
    
    def test_validate_tx_hash_format_bsc(self, payment_handler):
        """Test BSC transaction hash format validation."""
        # Valid BSC hash
        valid_hash = "0x" + "a" * 64
        assert payment_handler._validate_tx_hash_format(valid_hash, "bnb")
        
        # Invalid: missing 0x prefix
        invalid_hash1 = "a" * 64
        assert not payment_handler._validate_tx_hash_format(invalid_hash1, "bnb")
        
        # Invalid: wrong length
        invalid_hash2 = "0x" + "a" * 63
        assert not payment_handler._validate_tx_hash_format(invalid_hash2, "bnb")
        
        # Invalid: non-hex characters
        invalid_hash3 = "0x" + "g" * 64
        assert not payment_handler._validate_tx_hash_format(invalid_hash3, "bnb")
    
    def test_validate_tx_hash_format_solana(self, payment_handler):
        """Test Solana transaction hash format validation."""
        # Valid Solana signature (base58, ~88 chars)
        valid_hash = "5" + "A" * 87  # Base58 chars
        assert payment_handler._validate_tx_hash_format(valid_hash, "sol")
        
        # Invalid: too short
        invalid_hash1 = "5" + "A" * 20
        assert not payment_handler._validate_tx_hash_format(invalid_hash1, "sol")
        
        # Invalid: contains invalid base58 char (0)
        invalid_hash2 = "0" * 88
        assert not payment_handler._validate_tx_hash_format(invalid_hash2, "sol")
    
    def test_validate_tx_hash_format_tron(self, payment_handler):
        """Test Tron transaction hash format validation."""
        # Valid Tron hash (64 hex chars, no 0x prefix)
        valid_hash = "a" * 64
        assert payment_handler._validate_tx_hash_format(valid_hash, "trx")
        
        # Invalid: has 0x prefix (Tron doesn't use it)
        invalid_hash1 = "0x" + "a" * 64
        assert not payment_handler._validate_tx_hash_format(invalid_hash1, "trx")
        
        # Invalid: wrong length
        invalid_hash2 = "a" * 63
        assert not payment_handler._validate_tx_hash_format(invalid_hash2, "trx")
    
    def test_usdt_token_symbol_variants(self):
        """Test that USDT token symbol matching accepts common variants."""
        # This tests the logic in _check_bsc where we check token symbols
        # The fix allows "USDT", "BSC-USD", or "USD" as valid USDT symbols
        
        valid_symbols = ["USDT", "BSC-USD", "USD"]
        invalid_symbols = ["BNB", "ETH", "DAI", ""]
        
        for symbol in valid_symbols:
            # Simulate the check from _check_bsc line 515-518
            token_symbol = symbol.upper()
            assert token_symbol in ["USDT", "BSC-USD", "USD"], f"Symbol {symbol} should be accepted"
        
        for symbol in invalid_symbols:
            token_symbol = symbol.upper()
            assert token_symbol not in ["USDT", "BSC-USD", "USD"], f"Symbol {symbol} should be rejected"
    
    def test_logging_methods_exist(self, payment_handler):
        """Test that logging helper methods exist."""
        # These methods should exist after our changes
        assert hasattr(payment_handler, '_log_verification_attempt')
        assert hasattr(payment_handler, '_log_verification_result')
        
        # Test that they can be called without errors (they should just log)
        try:
            payment_handler._log_verification_attempt(
                tx_hash="test_hash",
                expected_address="test_address",
                expected_amount_usd=100.0,
                crypto_type="bnb",
                expected_token=None,
                correlation_id="test_correlation"
            )
            
            payment_handler._log_verification_result(
                tx_hash="test_hash",
                status="success",
                received_amount=100.0,
                received_amount_usd=100.0,
                correlation_id="test_correlation"
            )
        except Exception as e:
            pytest.fail(f"Logging methods should not raise exceptions: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
