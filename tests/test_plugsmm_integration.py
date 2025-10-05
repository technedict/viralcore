#!/usr/bin/env python3
"""
Integration tests for Plugsmm adapter with mock provider.
Tests real-world scenarios including error conditions.
"""

import asyncio
import unittest
from unittest.mock import Mock, patch, AsyncMock
import json

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.plugsmm_adapter import create_plugsmm_adapter, PlugsmmAdapter

# Import ProviderErrorType for classification tests
try:
    from utils.boost_utils_enhanced import ProviderErrorType
except ImportError:
    # If import fails, define minimal version for tests
    from enum import Enum
    class ProviderErrorType(Enum):
        TRANSIENT = "transient"
        PERMANENT = "permanent"
        RATE_LIMITED = "rate_limited"
        INSUFFICIENT_FUNDS = "insufficient_funds"


class MockPlugsmmProvider:
    """Mock Plugsmm provider for integration testing."""
    
    def __init__(self):
        self.balance = 100.0
        self.orders = {}
        self.next_order_id = 1000
        self.valid_api_key = "test_api_key_12345"
        self.service_ids = {1000: "Views", 2000: "Likes"}
        self.rate_limit_count = 0
        self.rate_limit_threshold = 10
    
    async def handle_request(self, payload: dict) -> dict:
        """Simulate provider API responses."""
        
        # Check API key
        if payload.get("key") != self.valid_api_key:
            return {"error": "Incorrect API key"}
        
        action = payload.get("action")
        
        if action == "add":
            return await self._handle_add_order(payload)
        elif action == "status":
            return await self._handle_status(payload)
        elif action == "balance":
            return await self._handle_balance(payload)
        elif action == "services":
            return await self._handle_services(payload)
        elif action == "cancel":
            return await self._handle_cancel(payload)
        else:
            return {"error": f"Unknown action: {action}"}
    
    async def _handle_add_order(self, payload: dict) -> dict:
        """Handle add order request."""
        
        # Rate limiting
        self.rate_limit_count += 1
        if self.rate_limit_count > self.rate_limit_threshold:
            return {"error": "Too many requests. Please try again later."}
        
        # Validate service
        service_id = int(payload.get("service", 0))
        if service_id not in self.service_ids:
            return {"error": "Incorrect service ID"}
        
        # Validate link
        link = payload.get("link", "")
        if not link or not link.startswith("http"):
            return {"error": "Incorrect link format"}
        
        # Check quantity
        quantity = int(payload.get("quantity", 0))
        if quantity <= 0:
            return {"error": "Quantity must be positive"}
        
        # Calculate cost (simplified)
        cost = quantity * 0.001  # $0.001 per unit
        
        # Check balance
        if cost > self.balance:
            return {"error": "Not enough funds in the balance"}
        
        # Create order
        order_id = self.next_order_id
        self.next_order_id += 1
        
        self.orders[order_id] = {
            "order_id": order_id,
            "service_id": service_id,
            "link": link,
            "quantity": quantity,
            "cost": cost,
            "status": "Pending",
            "remains": quantity,
            "start_count": 0
        }
        
        # Deduct from balance
        self.balance -= cost
        
        return {
            "order": order_id
        }
    
    async def _handle_status(self, payload: dict) -> dict:
        """Handle status request."""
        
        if "order" in payload:
            # Single order status
            order_id = int(payload["order"])
            
            if order_id not in self.orders:
                return {"error": "Order not found"}
            
            order = self.orders[order_id]
            return {
                "charge": f"{order['cost']:.2f}",
                "status": order["status"],
                "remains": order["remains"],
                "start_count": order["start_count"],
                "currency": "USD"
            }
        elif "orders" in payload:
            # Multiple orders status
            order_ids = [int(x.strip()) for x in payload["orders"].split(",")]
            results = []
            
            for order_id in order_ids:
                if order_id in self.orders:
                    order = self.orders[order_id]
                    results.append({
                        "order": order_id,
                        "charge": f"{order['cost']:.2f}",
                        "status": order["status"],
                        "remains": order["remains"]
                    })
            
            return results
        else:
            return {"error": "Missing order parameter"}
    
    async def _handle_balance(self, payload: dict) -> dict:
        """Handle balance request."""
        return {
            "balance": f"{self.balance:.2f}",
            "currency": "USD"
        }
    
    async def _handle_services(self, payload: dict) -> dict:
        """Handle services list request."""
        services = []
        for sid, name in self.service_ids.items():
            services.append({
                "service": sid,
                "name": f"Test {name}",
                "type": "Default",
                "rate": "0.001",
                "min": "10",
                "max": "10000"
            })
        return services
    
    async def _handle_cancel(self, payload: dict) -> dict:
        """Handle cancel request."""
        order_ids = [int(x.strip()) for x in payload["orders"].split(",")]
        results = []
        
        for order_id in order_ids:
            if order_id in self.orders:
                self.orders[order_id]["status"] = "Canceled"
                results.append({"order": order_id, "cancel": 1})
            else:
                results.append({"order": order_id, "cancel": 0})
        
        return results
    
    def reset_rate_limit(self):
        """Reset rate limit counter."""
        self.rate_limit_count = 0


class TestPlugsmmIntegration(unittest.TestCase):
    """Integration tests with mock provider."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_provider = MockPlugsmmProvider()
        self.adapter = PlugsmmAdapter(
            api_url="https://test-api.example.com/v2",
            api_key="test_api_key_12345",
            timeout=10,
            use_new_encoding=True
        )
    
    async def _mock_post(self, *args, **kwargs):
        """Mock HTTP POST to provider."""
        # Extract data from kwargs
        data = kwargs.get('data')
        
        # Parse the request data
        if isinstance(data, str):
            # URL-encoded format
            from urllib.parse import parse_qs
            parsed = parse_qs(data)
            payload = {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
        else:
            payload = data if data else {}
        
        # Get response from mock provider
        response_data = await self.mock_provider.handle_request(payload)
        
        # Create mock response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=json.dumps(response_data))
        
        return mock_response
    
    @patch('aiohttp.ClientSession.post')
    def test_successful_boost_flow(self, mock_post):
        """Test complete successful boost flow."""
        
        # Setup mock
        async def mock_post_wrapper(*args, **kwargs):
            return await self._mock_post(*args, **kwargs)
        
        mock_post.return_value.__aenter__ = mock_post_wrapper
        
        # Run test
        loop = asyncio.get_event_loop()
        
        # Step 1: Check balance
        balance_result = loop.run_until_complete(
            self.adapter.get_balance(correlation_id="test-001")
        )
        
        self.assertTrue(balance_result.success)
        self.assertEqual(balance_result.data["balance"], "100.00")
        
        # Step 2: Create order
        order_result = loop.run_until_complete(
            self.adapter.add_order(
                service_id=1000,
                link="https://example.com/post/123",
                quantity=1000,
                correlation_id="test-001"
            )
        )
        
        self.assertTrue(order_result.success)
        self.assertIsNotNone(order_result.data.get("order"))
        order_id = order_result.data["order"]
        
        # Step 3: Check order status
        status_result = loop.run_until_complete(
            self.adapter.get_status(order_id, correlation_id="test-001")
        )
        
        self.assertTrue(status_result.success)
        self.assertEqual(status_result.data["status"], "Pending")
        
        # Step 4: Check updated balance
        balance_result2 = loop.run_until_complete(
            self.adapter.get_balance(correlation_id="test-001")
        )
        
        self.assertTrue(balance_result2.success)
        # Balance should be reduced by $1.00 (1000 * $0.001)
        self.assertEqual(balance_result2.data["balance"], "99.00")
    
    @patch('aiohttp.ClientSession.post')
    def test_insufficient_funds_scenario(self, mock_post):
        """Test insufficient funds error handling."""
        
        # Setup mock
        async def mock_post_wrapper(*args, **kwargs):
            return await self._mock_post(*args, **kwargs)
        
        mock_post.return_value.__aenter__ = mock_post_wrapper
        
        # Deplete balance
        self.mock_provider.balance = 0.01
        
        # Run test
        loop = asyncio.get_event_loop()
        
        # Try to create large order
        result = loop.run_until_complete(
            self.adapter.add_order(
                service_id=1000,
                link="https://example.com/post/456",
                quantity=10000,  # Would cost $10
                correlation_id="test-002"
            )
        )
        
        self.assertFalse(result.success)
        self.assertIn("Not enough funds", result.error)
    
    @patch('aiohttp.ClientSession.post')
    def test_invalid_service_id_scenario(self, mock_post):
        """Test invalid service ID error."""
        
        # Setup mock
        async def mock_post_wrapper(*args, **kwargs):
            return await self._mock_post(*args, **kwargs)
        
        mock_post.return_value.__aenter__ = mock_post_wrapper
        
        # Run test
        loop = asyncio.get_event_loop()
        
        result = loop.run_until_complete(
            self.adapter.add_order(
                service_id=9999,  # Invalid
                link="https://example.com/post/789",
                quantity=100,
                correlation_id="test-003"
            )
        )
        
        self.assertFalse(result.success)
        self.assertIn("Incorrect service", result.error)
    
    @patch('aiohttp.ClientSession.post')
    def test_invalid_api_key_scenario(self, mock_post):
        """Test invalid API key error."""
        
        # Create adapter with wrong key
        bad_adapter = PlugsmmAdapter(
            api_url="https://test-api.example.com/v2",
            api_key="wrong_key",
            timeout=10,
            use_new_encoding=True
        )
        
        # Setup mock
        async def mock_post_wrapper(*args, **kwargs):
            return await self._mock_post(*args, **kwargs)
        
        mock_post.return_value.__aenter__ = mock_post_wrapper
        
        # Run test
        loop = asyncio.get_event_loop()
        
        result = loop.run_until_complete(
            bad_adapter.add_order(
                service_id=1000,
                link="https://example.com/post/321",
                quantity=100,
                correlation_id="test-004"
            )
        )
        
        self.assertFalse(result.success)
        self.assertIn("Incorrect API key", result.error)
    
    @patch('aiohttp.ClientSession.post')
    def test_rate_limiting_scenario(self, mock_post):
        """Test rate limiting behavior."""
        
        # Setup mock
        async def mock_post_wrapper(*args, **kwargs):
            return await self._mock_post(*args, **kwargs)
        
        mock_post.return_value.__aenter__ = mock_post_wrapper
        
        # Run test
        loop = asyncio.get_event_loop()
        
        # Make requests until rate limited
        results = []
        for i in range(15):
            result = loop.run_until_complete(
                self.adapter.add_order(
                    service_id=1000,
                    link=f"https://example.com/post/{i}",
                    quantity=10,
                    correlation_id=f"test-005-{i}"
                )
            )
            results.append(result)
        
        # First 10 should succeed, rest should be rate limited
        success_count = sum(1 for r in results if r.success)
        rate_limited_count = sum(1 for r in results if not r.success and "Too many requests" in (r.error or ""))
        
        self.assertEqual(success_count, 10)
        self.assertGreater(rate_limited_count, 0)
    
    @patch('aiohttp.ClientSession.post')
    def test_multi_order_status(self, mock_post):
        """Test checking status of multiple orders."""
        
        # Setup mock
        async def mock_post_wrapper(*args, **kwargs):
            return await self._mock_post(*args, **kwargs)
        
        mock_post.return_value.__aenter__ = mock_post_wrapper
        
        # Run test
        loop = asyncio.get_event_loop()
        
        # Create multiple orders
        order_ids = []
        for i in range(3):
            result = loop.run_until_complete(
                self.adapter.add_order(
                    service_id=1000,
                    link=f"https://example.com/post/{i}",
                    quantity=100,
                    correlation_id=f"test-006-{i}"
                )
            )
            if result.success:
                order_ids.append(result.data["order"])
        
        # Check status of all orders
        status_result = loop.run_until_complete(
            self.adapter.get_multi_status(order_ids, correlation_id="test-006")
        )
        
        self.assertTrue(status_result.success)
        self.assertEqual(len(status_result.data), 3)
    
    @patch('aiohttp.ClientSession.post')
    def test_cancel_orders(self, mock_post):
        """Test canceling orders."""
        
        # Setup mock
        async def mock_post_wrapper(*args, **kwargs):
            return await self._mock_post(*args, **kwargs)
        
        mock_post.return_value.__aenter__ = mock_post_wrapper
        
        # Run test
        loop = asyncio.get_event_loop()
        
        # Create orders
        order_ids = []
        for i in range(2):
            result = loop.run_until_complete(
                self.adapter.add_order(
                    service_id=1000,
                    link=f"https://example.com/post/{i}",
                    quantity=100,
                    correlation_id=f"test-007-{i}"
                )
            )
            if result.success:
                order_ids.append(result.data["order"])
        
        # Cancel orders
        cancel_result = loop.run_until_complete(
            self.adapter.cancel_orders(order_ids, correlation_id="test-007")
        )
        
        self.assertTrue(cancel_result.success)
        self.assertEqual(len(cancel_result.data), 2)
        
        # Verify status is Canceled
        for order_id in order_ids:
            status_result = loop.run_until_complete(
                self.adapter.get_status(order_id, correlation_id="test-007")
            )
            self.assertEqual(status_result.data["status"], "Canceled")


class TestErrorClassification(unittest.TestCase):
    """Test error classification without full boost service."""
    
    def test_error_message_patterns(self):
        """Test that error messages are properly detected."""
        
        # Test patterns we expect to see
        test_cases = [
            ("Not enough funds in the balance", "insufficient_funds"),
            ("Incorrect service ID", "invalid_service"),
            ("Incorrect API key", "invalid_key"),
            ("Too many requests", "rate_limited"),
            ("Active order exists", "active_order"),
            ("Incorrect link format", "invalid_link"),
            ("Network error", "network"),
        ]
        
        for error_msg, expected_type in test_cases:
            error_lower = error_msg.lower()
            
            # Verify our detection logic
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
            elif "network error" in error_lower:
                detected_type = "network"
            else:
                detected_type = "unknown"
            
            self.assertEqual(detected_type, expected_type, f"Failed to detect: {error_msg}")


if __name__ == '__main__':
    unittest.main()
