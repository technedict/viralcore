#!/usr/bin/env python3
"""
Unit tests for Plugsmm adapter.
"""

import asyncio
import unittest
from unittest.mock import Mock, patch, AsyncMock
import json

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.plugsmm_adapter import (
    PlugsmmAdapter,
    PlugsmmResponse,
    PlugsmmAction,
    create_plugsmm_adapter
)


class TestPlugsmmAdapter(unittest.TestCase):
    """Test Plugsmm adapter functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.adapter = PlugsmmAdapter(
            api_url="https://test-api.example.com/v2",
            api_key="test_key_12345",
            timeout=10,
            use_new_encoding=True
        )
    
    def test_adapter_initialization(self):
        """Test adapter is initialized correctly."""
        self.assertEqual(self.adapter.api_url, "https://test-api.example.com/v2")
        self.assertEqual(self.adapter.api_key, "test_key_12345")
        self.assertEqual(self.adapter.timeout, 10)
        self.assertTrue(self.adapter.use_new_encoding)
    
    @patch('aiohttp.ClientSession.post')
    def test_add_order_success(self, mock_post):
        """Test successful order creation."""
        # Mock response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{"order": 123, "status": "success"}')
        mock_post.return_value.__aenter__.return_value = mock_response
        
        # Run test
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            self.adapter.add_order(
                service_id=1000,
                link="https://example.com/post",
                quantity=100,
                correlation_id="test-123"
            )
        )
        
        # Verify
        self.assertTrue(result.success)
        self.assertIsNone(result.error)
        self.assertEqual(result.data["order"], 123)
    
    @patch('aiohttp.ClientSession.post')
    def test_add_order_insufficient_funds(self, mock_post):
        """Test order creation with insufficient funds."""
        # Mock error response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{"error": "Not enough funds in the balance"}')
        mock_post.return_value.__aenter__.return_value = mock_response
        
        # Run test
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            self.adapter.add_order(
                service_id=1000,
                link="https://example.com/post",
                quantity=100
            )
        )
        
        # Verify
        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)
        self.assertIn("Not enough funds", result.error)
    
    @patch('aiohttp.ClientSession.post')
    def test_add_order_invalid_service(self, mock_post):
        """Test order creation with invalid service ID."""
        # Mock error response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{"error": "Incorrect service ID"}')
        mock_post.return_value.__aenter__.return_value = mock_response
        
        # Run test
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            self.adapter.add_order(
                service_id=9999,
                link="https://example.com/post",
                quantity=100
            )
        )
        
        # Verify
        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)
        self.assertIn("Incorrect service", result.error)
    
    @patch('aiohttp.ClientSession.post')
    def test_add_order_with_optional_params(self, mock_post):
        """Test order creation with optional parameters."""
        # Mock response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{"order": 456}')
        mock_post.return_value.__aenter__.return_value = mock_response
        
        # Run test
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            self.adapter.add_order(
                service_id=1000,
                link="https://example.com/post",
                quantity=100,
                runs=5,
                interval=10,
                comments="Great post\nNice work"
            )
        )
        
        # Verify
        self.assertTrue(result.success)
        self.assertEqual(result.data["order"], 456)
    
    @patch('aiohttp.ClientSession.post')
    def test_get_status(self, mock_post):
        """Test getting order status."""
        # Mock response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{"charge": "0.50", "status": "Completed", "remains": 0}')
        mock_post.return_value.__aenter__.return_value = mock_response
        
        # Run test
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            self.adapter.get_status(order_id=123)
        )
        
        # Verify
        self.assertTrue(result.success)
        self.assertEqual(result.data["status"], "Completed")
    
    @patch('aiohttp.ClientSession.post')
    def test_get_multi_status(self, mock_post):
        """Test getting multiple order statuses."""
        # Mock response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='[{"order": 123, "status": "Completed"}, {"order": 456, "status": "In progress"}]')
        mock_post.return_value.__aenter__.return_value = mock_response
        
        # Run test
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            self.adapter.get_multi_status(order_ids=[123, 456])
        )
        
        # Verify
        self.assertTrue(result.success)
        self.assertEqual(len(result.data), 2)
    
    @patch('aiohttp.ClientSession.post')
    def test_get_balance(self, mock_post):
        """Test getting account balance."""
        # Mock response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{"balance": "100.50", "currency": "USD"}')
        mock_post.return_value.__aenter__.return_value = mock_response
        
        # Run test
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            self.adapter.get_balance()
        )
        
        # Verify
        self.assertTrue(result.success)
        self.assertEqual(result.data["balance"], "100.50")
    
    @patch('aiohttp.ClientSession.post')
    def test_http_error(self, mock_post):
        """Test handling of HTTP errors."""
        # Mock 500 error
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value='Internal Server Error')
        mock_post.return_value.__aenter__.return_value = mock_response
        
        # Run test
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            self.adapter.add_order(
                service_id=1000,
                link="https://example.com/post",
                quantity=100
            )
        )
        
        # Verify
        self.assertFalse(result.success)
        self.assertIn("HTTP 500", result.error)
    
    @patch('aiohttp.ClientSession.post')
    def test_invalid_json_response(self, mock_post):
        """Test handling of invalid JSON responses."""
        # Mock invalid JSON
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='Not valid JSON {')
        mock_post.return_value.__aenter__.return_value = mock_response
        
        # Run test
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            self.adapter.add_order(
                service_id=1000,
                link="https://example.com/post",
                quantity=100
            )
        )
        
        # Verify
        self.assertFalse(result.success)
        self.assertIn("Invalid JSON", result.error)
    
    @patch('aiohttp.ClientSession.post')
    def test_network_timeout(self, mock_post):
        """Test handling of network timeouts."""
        # Mock timeout
        mock_post.side_effect = asyncio.TimeoutError()
        
        # Run test
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            self.adapter.add_order(
                service_id=1000,
                link="https://example.com/post",
                quantity=100
            )
        )
        
        # Verify
        self.assertFalse(result.success)
        self.assertIn("timeout", result.error.lower())
    
    @patch('aiohttp.ClientSession.post')
    def test_cancel_orders(self, mock_post):
        """Test canceling multiple orders."""
        # Mock response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='[{"order": 123, "cancel": "1"}, {"order": 456, "cancel": "1"}]')
        mock_post.return_value.__aenter__.return_value = mock_response
        
        # Run test
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            self.adapter.cancel_orders(order_ids=[123, 456])
        )
        
        # Verify
        self.assertTrue(result.success)
    
    @patch('aiohttp.ClientSession.post')
    def test_refill_order(self, mock_post):
        """Test refilling an order."""
        # Mock response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{"refill": 789}')
        mock_post.return_value.__aenter__.return_value = mock_response
        
        # Run test
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            self.adapter.refill_order(order_id=123)
        )
        
        # Verify
        self.assertTrue(result.success)
        self.assertEqual(result.data["refill"], 789)
    
    @patch.dict(os.environ, {"PLUGSMMS_API_KEY": "env_test_key"})
    def test_factory_with_env_key(self):
        """Test factory function uses environment variable."""
        adapter = create_plugsmm_adapter()
        
        self.assertEqual(adapter.api_key, "env_test_key")
        self.assertEqual(adapter.api_url, "https://plugsmmservice.com/api/v2")
    
    @patch.dict(os.environ, {"PLUGSMM_USE_NEW_API": "false"})
    def test_factory_with_disabled_feature_flag(self):
        """Test factory function respects feature flag."""
        adapter = create_plugsmm_adapter(api_key="test_key")
        
        self.assertFalse(adapter.use_new_encoding)
    
    @patch.dict(os.environ, {"PLUGSMM_USE_NEW_API": "true"})
    def test_factory_with_enabled_feature_flag(self):
        """Test factory function with enabled feature flag."""
        adapter = create_plugsmm_adapter(api_key="test_key")
        
        self.assertTrue(adapter.use_new_encoding)


if __name__ == '__main__':
    unittest.main()
