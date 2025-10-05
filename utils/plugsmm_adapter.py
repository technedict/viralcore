#!/usr/bin/env python3
"""
Plugsmmservice API Adapter
Implements the new Plugsmmservice API v2 with backwards compatibility.
"""

import asyncio
import aiohttp
import json
import os
from typing import Dict, Optional, Any, List
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlencode

from utils.logging import get_logger, log_provider_error

logger = get_logger(__name__)


class PlugsmmAction(Enum):
    """Supported API actions."""
    ADD = "add"
    STATUS = "status"
    SERVICES = "services"
    REFILL = "refill"
    REFILL_STATUS = "refill_status"
    CANCEL = "cancel"
    BALANCE = "balance"


@dataclass
class PlugsmmResponse:
    """Standardized response from Plugsmm API."""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None


class PlugsmmAdapter:
    """
    Adapter for Plugsmmservice API v2.
    
    This adapter encapsulates all provider interaction and provides
    a clean internal API for the rest of the application.
    """
    
    def __init__(
        self,
        api_url: str,
        api_key: str,
        timeout: int = 30,
        use_new_encoding: bool = True
    ):
        """
        Initialize the adapter.
        
        Args:
            api_url: Provider API endpoint
            api_key: Provider API key
            timeout: Request timeout in seconds
            use_new_encoding: Use PHP-compatible URL encoding (default: True)
        """
        self.api_url = api_url
        self.api_key = api_key
        self.timeout = timeout
        self.use_new_encoding = use_new_encoding
        
    async def add_order(
        self,
        service_id: int,
        link: str,
        quantity: int,
        correlation_id: Optional[str] = None,
        **kwargs
    ) -> PlugsmmResponse:
        """
        Create a new order.
        
        Args:
            service_id: Service ID from provider
            link: URL to boost
            quantity: Number of items (likes, views, etc.)
            correlation_id: For request tracking
            **kwargs: Optional parameters (runs, interval, comments, etc.)
            
        Returns:
            PlugsmmResponse with order details or error
        """
        payload = {
            "key": self.api_key,
            "action": PlugsmmAction.ADD.value,
            "service": service_id,
            "link": link,
            "quantity": quantity
        }
        
        # Add optional parameters if provided
        optional_params = [
            'runs', 'interval', 'comments', 'usernames', 'hashtags',
            'username', 'min', 'max', 'posts', 'old_posts', 'delay',
            'expiry', 'answer_number', 'groups'
        ]
        
        for param in optional_params:
            if param in kwargs and kwargs[param] is not None:
                payload[param] = kwargs[param]
        
        return await self._make_request(payload, correlation_id)
    
    async def get_status(
        self,
        order_id: int,
        correlation_id: Optional[str] = None
    ) -> PlugsmmResponse:
        """
        Get status of a single order.
        
        Args:
            order_id: Provider order ID
            correlation_id: For request tracking
            
        Returns:
            PlugsmmResponse with order status
        """
        payload = {
            "key": self.api_key,
            "action": PlugsmmAction.STATUS.value,
            "order": order_id
        }
        
        return await self._make_request(payload, correlation_id)
    
    async def get_multi_status(
        self,
        order_ids: List[int],
        correlation_id: Optional[str] = None
    ) -> PlugsmmResponse:
        """
        Get status of multiple orders.
        
        Args:
            order_ids: List of provider order IDs
            correlation_id: For request tracking
            
        Returns:
            PlugsmmResponse with order statuses
        """
        payload = {
            "key": self.api_key,
            "action": PlugsmmAction.STATUS.value,
            "orders": ",".join(str(oid) for oid in order_ids)
        }
        
        return await self._make_request(payload, correlation_id)
    
    async def get_services(
        self,
        correlation_id: Optional[str] = None
    ) -> PlugsmmResponse:
        """
        Get list of available services.
        
        Args:
            correlation_id: For request tracking
            
        Returns:
            PlugsmmResponse with services list
        """
        payload = {
            "key": self.api_key,
            "action": PlugsmmAction.SERVICES.value
        }
        
        return await self._make_request(payload, correlation_id)
    
    async def refill_order(
        self,
        order_id: int,
        correlation_id: Optional[str] = None
    ) -> PlugsmmResponse:
        """
        Refill a single order.
        
        Args:
            order_id: Provider order ID
            correlation_id: For request tracking
            
        Returns:
            PlugsmmResponse with refill details
        """
        payload = {
            "key": self.api_key,
            "action": PlugsmmAction.REFILL.value,
            "order": order_id
        }
        
        return await self._make_request(payload, correlation_id)
    
    async def refill_orders(
        self,
        order_ids: List[int],
        correlation_id: Optional[str] = None
    ) -> PlugsmmResponse:
        """
        Refill multiple orders.
        
        Args:
            order_ids: List of provider order IDs
            correlation_id: For request tracking
            
        Returns:
            PlugsmmResponse with refill details
        """
        payload = {
            "key": self.api_key,
            "action": PlugsmmAction.REFILL.value,
            "orders": ",".join(str(oid) for oid in order_ids)
        }
        
        return await self._make_request(payload, correlation_id)
    
    async def get_refill_status(
        self,
        refill_id: int,
        correlation_id: Optional[str] = None
    ) -> PlugsmmResponse:
        """
        Get refill status.
        
        Args:
            refill_id: Provider refill ID
            correlation_id: For request tracking
            
        Returns:
            PlugsmmResponse with refill status
        """
        payload = {
            "key": self.api_key,
            "action": PlugsmmAction.REFILL_STATUS.value,
            "refill": refill_id
        }
        
        return await self._make_request(payload, correlation_id)
    
    async def get_multi_refill_status(
        self,
        refill_ids: List[int],
        correlation_id: Optional[str] = None
    ) -> PlugsmmResponse:
        """
        Get multiple refill statuses.
        
        Args:
            refill_ids: List of provider refill IDs
            correlation_id: For request tracking
            
        Returns:
            PlugsmmResponse with refill statuses
        """
        payload = {
            "key": self.api_key,
            "action": PlugsmmAction.REFILL_STATUS.value,
            "refills": ",".join(str(rid) for rid in refill_ids)
        }
        
        return await self._make_request(payload, correlation_id)
    
    async def cancel_orders(
        self,
        order_ids: List[int],
        correlation_id: Optional[str] = None
    ) -> PlugsmmResponse:
        """
        Cancel multiple orders.
        
        Args:
            order_ids: List of provider order IDs
            correlation_id: For request tracking
            
        Returns:
            PlugsmmResponse with cancellation details
        """
        payload = {
            "key": self.api_key,
            "action": PlugsmmAction.CANCEL.value,
            "orders": ",".join(str(oid) for oid in order_ids)
        }
        
        return await self._make_request(payload, correlation_id)
    
    async def get_balance(
        self,
        correlation_id: Optional[str] = None
    ) -> PlugsmmResponse:
        """
        Get account balance.
        
        Args:
            correlation_id: For request tracking
            
        Returns:
            PlugsmmResponse with balance information
        """
        payload = {
            "key": self.api_key,
            "action": PlugsmmAction.BALANCE.value
        }
        
        return await self._make_request(payload, correlation_id)
    
    async def _make_request(
        self,
        payload: Dict[str, Any],
        correlation_id: Optional[str] = None
    ) -> PlugsmmResponse:
        """
        Make HTTP request to provider API.
        
        Args:
            payload: Request payload
            correlation_id: For request tracking and logging
            
        Returns:
            PlugsmmResponse
        """
        start_time = asyncio.get_event_loop().time()
        
        try:
            # Prepare request body
            if self.use_new_encoding:
                # PHP-compatible URL encoding
                # Convert all values to strings and encode
                encoded_payload = urlencode({k: str(v) for k, v in payload.items()})
                headers = {'Content-Type': 'application/x-www-form-urlencoded'}
                request_data = encoded_payload
            else:
                # Legacy: Let aiohttp handle encoding
                headers = {}
                request_data = payload
            
            # Log request (sanitize API key)
            safe_payload = {**payload}
            if 'key' in safe_payload:
                safe_payload['key'] = f"{safe_payload['key'][:4]}...{safe_payload['key'][-4:]}"
            
            logger.info(
                f"Plugsmm API request: {safe_payload.get('action')}",
                extra={
                    'correlation_id': correlation_id,
                    'payload': safe_payload,
                    'url': self.api_url
                }
            )
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.api_url,
                    data=request_data if self.use_new_encoding else payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    
                    elapsed_time = asyncio.get_event_loop().time() - start_time
                    
                    # Get response text first for better error handling
                    response_text = await response.text()
                    
                    logger.info(
                        f"Plugsmm API response: status={response.status}, elapsed={elapsed_time:.2f}s",
                        extra={
                            'correlation_id': correlation_id,
                            'status_code': response.status,
                            'elapsed_time': elapsed_time,
                            'response_preview': response_text[:200] if response_text else None
                        }
                    )
                    
                    # Check HTTP status
                    if response.status != 200:
                        error_msg = f"HTTP {response.status}: {response_text[:200]}"
                        log_provider_error(logger, "plugsmms", error_msg, correlation_id)
                        
                        return PlugsmmResponse(
                            success=False,
                            error=error_msg,
                            raw_response={"http_status": response.status, "body": response_text}
                        )
                    
                    # Parse JSON response
                    try:
                        data = json.loads(response_text)
                    except json.JSONDecodeError as e:
                        error_msg = f"Invalid JSON response: {e}"
                        log_provider_error(logger, "plugsmms", error_msg, correlation_id)
                        
                        return PlugsmmResponse(
                            success=False,
                            error=error_msg,
                            raw_response={"body": response_text}
                        )
                    
                    # Check for error in response
                    if "error" in data:
                        error_msg = str(data["error"])
                        log_provider_error(logger, "plugsmms", data, correlation_id)
                        
                        return PlugsmmResponse(
                            success=False,
                            error=error_msg,
                            raw_response=data
                        )
                    
                    # Success
                    logger.info(
                        "Plugsmm API success",
                        extra={
                            'correlation_id': correlation_id,
                            'response_data': data
                        }
                    )
                    
                    return PlugsmmResponse(
                        success=True,
                        data=data,
                        raw_response=data
                    )
                    
        except aiohttp.ClientError as e:
            elapsed_time = asyncio.get_event_loop().time() - start_time
            error_msg = f"Network error: {e}"
            log_provider_error(logger, "plugsmms", error_msg, correlation_id)
            
            logger.error(
                f"Plugsmm API network error after {elapsed_time:.2f}s: {e}",
                extra={'correlation_id': correlation_id}
            )
            
            return PlugsmmResponse(
                success=False,
                error=error_msg
            )
            
        except asyncio.TimeoutError:
            elapsed_time = asyncio.get_event_loop().time() - start_time
            error_msg = f"Request timeout after {elapsed_time:.2f}s"
            log_provider_error(logger, "plugsmms", error_msg, correlation_id)
            
            logger.error(
                f"Plugsmm API timeout: {error_msg}",
                extra={'correlation_id': correlation_id}
            )
            
            return PlugsmmResponse(
                success=False,
                error=error_msg
            )
            
        except Exception as e:
            elapsed_time = asyncio.get_event_loop().time() - start_time
            error_msg = f"Unexpected error: {e}"
            log_provider_error(logger, "plugsmms", error_msg, correlation_id)
            
            logger.error(
                f"Plugsmm API unexpected error after {elapsed_time:.2f}s: {e}",
                extra={'correlation_id': correlation_id},
                exc_info=True
            )
            
            return PlugsmmResponse(
                success=False,
                error=error_msg
            )


def create_plugsmm_adapter(
    api_url: str = "https://plugsmmservice.com/api/v2",
    api_key: Optional[str] = None,
    use_new_encoding: bool = True
) -> PlugsmmAdapter:
    """
    Factory function to create a Plugsmm adapter.
    
    Args:
        api_url: Provider API URL
        api_key: Provider API key (defaults to env var)
        use_new_encoding: Use PHP-compatible encoding
        
    Returns:
        PlugsmmAdapter instance
    """
    if api_key is None:
        api_key = os.getenv("PLUGSMMS_API_KEY", "MISSING_KEY")
    
    # Check for feature toggle
    use_new_api = os.getenv("PLUGSMM_USE_NEW_API", "true").lower() == "true"
    
    if not use_new_api:
        logger.warning("PLUGSMM_USE_NEW_API is disabled - using legacy adapter")
        use_new_encoding = False
    
    return PlugsmmAdapter(
        api_url=api_url,
        api_key=api_key,
        use_new_encoding=use_new_encoding
    )
