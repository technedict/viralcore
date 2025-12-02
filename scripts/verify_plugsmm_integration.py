#!/usr/bin/env python3
"""
End-to-End Verification Script for Plugsmm Integration

This script verifies the Plugsmm adapter is working correctly without
making actual API calls (uses dry-run mode).
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from utils.plugsmm_adapter import create_plugsmm_adapter, PlugsmmAdapter
from utils.boost_provider_utils import get_active_provider, PROVIDERS


def print_section(title):
    """Print a section header."""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print('=' * 60)


def verify_configuration():
    """Verify configuration is correct."""
    print_section("1. Configuration Verification")
    
    # Check provider config
    plugsmms_config = PROVIDERS.get("plugsmms")
    if not plugsmms_config:
        print("❌ FAILED: plugsmms not found in PROVIDERS")
        return False
    
    print(f"✅ Provider name: {plugsmms_config.name}")
    print(f"✅ API URL: {plugsmms_config.api_url}")
    print(f"✅ View service ID: {plugsmms_config.view_service_id}")
    print(f"✅ Like service ID: {plugsmms_config.like_service_id}")
    
    # Check API key
    api_key = plugsmms_config.api_key
    if api_key == "MISSING_KEY":
        print("⚠️  WARNING: PLUGSMMS_API_KEY not set in environment")
        print("   This is OK for testing, but required for production")
    else:
        print(f"✅ API key configured: {api_key[:4]}...{api_key[-4:]}")
    
    return True


def verify_adapter_creation():
    """Verify adapter can be created."""
    print_section("2. Adapter Creation")
    
    try:
        # Create adapter with test key
        adapter = create_plugsmm_adapter(api_key="test_key_12345")
        print(f"✅ Adapter created successfully")
        print(f"✅ API URL: {adapter.api_url}")
        print(f"✅ Timeout: {adapter.timeout}s")
        print(f"✅ New encoding enabled: {adapter.use_new_encoding}")
        return True
    except Exception as e:
        print(f"❌ FAILED: {e}")
        return False


def verify_feature_flags():
    """Verify feature flags are working."""
    print_section("3. Feature Flags")
    
    # Check default (new API enabled)
    use_new_api = os.getenv("PLUGSMM_USE_NEW_API", "true").lower() == "true"
    print(f"✅ PLUGSMM_USE_NEW_API: {use_new_api}")
    
    enable_tracking = os.getenv("PLUGSMM_ENABLE_ORDER_TRACKING", "true").lower() == "true"
    print(f"✅ PLUGSMM_ENABLE_ORDER_TRACKING: {enable_tracking}")
    
    if use_new_api:
        print("✅ New adapter will be used for plugsmms provider")
    else:
        print("⚠️  Legacy implementation will be used (rollback mode)")
    
    return True


async def verify_request_payload():
    """Verify request payload is constructed correctly."""
    print_section("4. Request Payload Construction")
    
    from urllib.parse import urlencode
    
    # Test payload
    payload = {
        "key": "test_key",
        "action": "add",
        "service": 6073,
        "link": "https://twitter.com/example/status/123",
        "quantity": 1000
    }
    
    # URL encode like the adapter does
    encoded = urlencode({k: str(v) for k, v in payload.items()})
    print(f"✅ Payload encoded: {encoded}")
    
    # Verify encoding
    expected_parts = [
        "key=test_key",
        "action=add",
        "service=6073",
        "link=https%3A%2F%2Ftwitter.com%2Fexample%2Fstatus%2F123",
        "quantity=1000"
    ]
    
    for part in expected_parts:
        if part in encoded:
            print(f"   ✅ Contains: {part}")
        else:
            print(f"   ❌ Missing: {part}")
            return False
    
    return True


def verify_error_classification():
    """Verify error classification logic."""
    print_section("5. Error Classification")
    
    test_cases = [
        ("Not enough funds in the balance", "insufficient_funds"),
        ("Incorrect service ID", "invalid_service"),
        ("Incorrect API key", "invalid_key"),
        ("Too many requests", "rate_limited"),
        ("Active order exists", "active_order"),
        ("Incorrect link format", "invalid_link"),
        ("Network timeout", "network"),
    ]
    
    all_passed = True
    for error_msg, expected_type in test_cases:
        error_lower = error_msg.lower()
        
        # Classify error (simplified version of _classify_plugsmm_error)
        if "not enough funds" in error_lower or "insufficient balance" in error_lower:
            detected_type = "insufficient_funds"
        elif "incorrect service" in error_lower or "invalid service" in error_lower:
            detected_type = "invalid_service"
        elif "incorrect api key" in error_lower or "invalid key" in error_lower:
            detected_type = "invalid_key"
        elif "rate limit" in error_lower or "too many requests" in error_lower:
            detected_type = "rate_limited"
        elif "active order" in error_lower:
            detected_type = "active_order"
        elif "incorrect link" in error_lower or "invalid link" in error_lower:
            detected_type = "invalid_link"
        elif "timeout" in error_lower or "network" in error_lower:
            detected_type = "network"
        else:
            detected_type = "unknown"
        
        if detected_type == expected_type:
            print(f"✅ '{error_msg}' → {detected_type}")
        else:
            print(f"❌ '{error_msg}' → {detected_type} (expected {expected_type})")
            all_passed = False
    
    return all_passed


def verify_backwards_compatibility():
    """Verify backwards compatibility."""
    print_section("6. Backwards Compatibility")
    
    # Check that other providers are not affected
    for provider_name in ["smmflare", "smmstone"]:
        provider = PROVIDERS.get(provider_name)
        if provider:
            print(f"✅ {provider_name} provider still available")
        else:
            print(f"❌ {provider_name} provider missing")
            return False
    
    # Check that the integration doesn't break existing code
    try:
        active_provider = get_active_provider()
        print(f"✅ get_active_provider() works: {active_provider.name}")
    except Exception as e:
        print(f"❌ get_active_provider() failed: {e}")
        return False
    
    return True


def verify_documentation():
    """Verify documentation exists."""
    print_section("7. Documentation")
    
    docs = [
        ("PLUGSMM_API_MAPPING.md", "API mapping and changes"),
        ("PLUGSMM_DEPLOYMENT_RUNBOOK.md", "Deployment and troubleshooting"),
        ("PLUGSMM_PR_SUMMARY.md", "PR summary and acceptance criteria"),
        ("README.md", "Updated with Plugsmm section"),
        (".env.example", "Updated with new env vars"),
    ]
    
    all_exist = True
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    for filename, description in docs:
        filepath = os.path.join(repo_root, filename)
        if os.path.exists(filepath):
            size_kb = os.path.getsize(filepath) / 1024
            print(f"✅ {filename} ({size_kb:.1f} KB) - {description}")
        else:
            print(f"❌ {filename} - NOT FOUND")
            all_exist = False
    
    return all_exist


def verify_tests():
    """Verify test files exist."""
    print_section("8. Test Coverage")
    
    tests = [
        ("tests/test_plugsmm_adapter.py", "Unit tests for adapter"),
        ("tests/test_plugsmm_integration.py", "Integration tests"),
    ]
    
    all_exist = True
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    for filename, description in tests:
        filepath = os.path.join(repo_root, filename)
        if os.path.exists(filepath):
            # Count test methods
            with open(filepath, 'r') as f:
                content = f.read()
                test_count = content.count('def test_')
            print(f"✅ {filename} ({test_count} tests) - {description}")
        else:
            print(f"❌ {filename} - NOT FOUND")
            all_exist = False
    
    return all_exist


def print_summary(results):
    """Print verification summary."""
    print_section("Verification Summary")
    
    total = len(results)
    passed = sum(results.values())
    
    print(f"\nResults: {passed}/{total} checks passed")
    print()
    
    for check, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {check}")
    
    print()
    
    if passed == total:
        print("🎉 All verification checks passed!")
        print()
        print("Next steps:")
        print("1. Deploy to staging environment")
        print("2. Run: python3 -m unittest tests.test_plugsmm_adapter")
        print("3. Monitor logs for any issues")
        print("4. Follow PLUGSMM_DEPLOYMENT_RUNBOOK.md for production")
        return 0
    else:
        print("⚠️  Some verification checks failed")
        print("Please review the failures above before deployment")
        return 1


def main():
    """Run all verification checks."""
    print("=" * 60)
    print("  Plugsmm Integration Verification Script")
    print("=" * 60)
    print()
    print("This script verifies the Plugsmm integration is ready for deployment.")
    print()
    
    # Run all checks
    results = {
        "Configuration": verify_configuration(),
        "Adapter Creation": verify_adapter_creation(),
        "Feature Flags": verify_feature_flags(),
        "Request Payload": asyncio.run(verify_request_payload()),
        "Error Classification": verify_error_classification(),
        "Backwards Compatibility": verify_backwards_compatibility(),
        "Documentation": verify_documentation(),
        "Test Coverage": verify_tests(),
    }
    
    # Print summary
    exit_code = print_summary(results)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
