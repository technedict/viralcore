#!/usr/bin/env python3
# utils/api_client.py
# Structured API client with error handling and diagnostics

import json
import logging
import time
import uuid
from typing import Dict, Any, Optional, Union
from datetime import datetime
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

class APIError(Exception):
    """Base exception for API-related errors."""
    
    def __init__(self, message: str, code: str = None, context: Dict = None, trace_id: str = None):
        super().__init__(message)
        self.message = message
        self.code = code or "UNKNOWN_ERROR"
        self.context = context or {}
        self.trace_id = trace_id or str(uuid.uuid4())
        self.timestamp = datetime.utcnow().isoformat()

class APIClient:
    """Structured HTTP client with comprehensive error handling and logging."""
    
    def __init__(self, base_url: str = None, timeout: int = 30, max_retries: int = 3):
        self.base_url = base_url
        self.timeout = timeout
        self.session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST", "PUT", "DELETE", "OPTIONS", "TRACE"]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Set common headers
        self.session.headers.update({
            'User-Agent': 'ViralCore-Bot/1.0',
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        })
    
    def _generate_trace_id(self) -> str:
        """Generate a unique trace ID for request correlation."""
        return f"vc_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    
    def _sanitize_payload(self, payload: Dict) -> Dict:
        """Sanitize payload for logging (remove sensitive data)."""
        if not payload:
            return {}
        
        sensitive_keys = {
            'password', 'token', 'secret', 'key', 'auth', 'authorization',
            'api_key', 'access_token', 'refresh_token', 'private_key',
            'account_number', 'bank_details', 'transaction_ref'
        }
        
        sanitized = {}
        for key, value in payload.items():
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                sanitized[key] = "[REDACTED]"
            elif isinstance(value, dict):
                sanitized[key] = self._sanitize_payload(value)
            else:
                sanitized[key] = value
        
        return sanitized
    
    def _log_request(self, method: str, url: str, payload: Dict, trace_id: str):
        """Log outgoing request with structured format."""
        logger.info(
            "API Request",
            extra={
                'trace_id': trace_id,
                'method': method,
                'url': url,
                'payload': self._sanitize_payload(payload),
                'timestamp': datetime.utcnow().isoformat(),
                'event_type': 'api_request'
            }
        )
    
    def _log_response(self, method: str, url: str, status_code: int, response_text: str, 
                     trace_id: str, duration: float, error: str = None):
        """Log API response with structured format."""
        # Truncate response body for logging
        max_response_length = 1000
        truncated_response = (
            response_text[:max_response_length] + "... [TRUNCATED]"
            if len(response_text) > max_response_length
            else response_text
        )
        
        log_level = logging.ERROR if error or status_code >= 400 else logging.INFO
        
        logger.log(
            log_level,
            f"API Response [{status_code}]",
            extra={
                'trace_id': trace_id,
                'method': method,
                'url': url,
                'status_code': status_code,
                'response_body': truncated_response,
                'duration_ms': round(duration * 1000, 2),
                'error': error,
                'timestamp': datetime.utcnow().isoformat(),
                'event_type': 'api_response'
            }
        )
    
    def _make_request(self, method: str, url: str, **kwargs) -> Dict[str, Any]:
        """
        Make HTTP request with comprehensive error handling and logging.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL
            **kwargs: Additional arguments for requests
        
        Returns:
            Dictionary with success, data, error, and metadata
        """
        trace_id = self._generate_trace_id()
        full_url = f"{self.base_url.rstrip('/')}/{url.lstrip('/')}" if self.base_url else url
        
        # Prepare payload for logging
        payload = kwargs.get('json', kwargs.get('data', {}))
        
        # Log request
        self._log_request(method, full_url, payload, trace_id)
        
        start_time = time.time()
        
        try:
            # Set timeout if not provided
            if 'timeout' not in kwargs:
                kwargs['timeout'] = self.timeout
            
            # Make the request
            response = self.session.request(method, full_url, **kwargs)
            duration = time.time() - start_time
            
            # Log response
            self._log_response(
                method, full_url, response.status_code, 
                response.text, trace_id, duration
            )
            
            # Parse response
            try:
                response_data = response.json() if response.text else {}
            except ValueError:
                response_data = {'raw_response': response.text}
            
            # Check for HTTP errors
            if response.status_code >= 400:
                error_message = f"HTTP {response.status_code}: {response.reason}"
                if response_data.get('message'):
                    error_message += f" - {response_data['message']}"
                
                raise APIError(
                    message=error_message,
                    code=f"HTTP_{response.status_code}",
                    context={
                        'url': full_url,
                        'method': method,
                        'status_code': response.status_code,
                        'response_data': response_data
                    },
                    trace_id=trace_id
                )
            
            return {
                'success': True,
                'data': response_data,
                'status_code': response.status_code,
                'trace_id': trace_id,
                'duration_ms': round(duration * 1000, 2)
            }
            
        except requests.exceptions.Timeout as e:
            duration = time.time() - start_time
            error_msg = f"Request timeout after {self.timeout}s"
            
            self._log_response(method, full_url, 0, "", trace_id, duration, error_msg)
            
            raise APIError(
                message=error_msg,
                code="TIMEOUT",
                context={'url': full_url, 'method': method, 'timeout': self.timeout},
                trace_id=trace_id
            ) from e
            
        except requests.exceptions.ConnectionError as e:
            duration = time.time() - start_time
            error_msg = f"Connection error: {str(e)}"
            
            self._log_response(method, full_url, 0, "", trace_id, duration, error_msg)
            
            raise APIError(
                message=error_msg,
                code="CONNECTION_ERROR",
                context={'url': full_url, 'method': method},
                trace_id=trace_id
            ) from e
            
        except requests.exceptions.RequestException as e:
            duration = time.time() - start_time
            error_msg = f"Request failed: {str(e)}"
            
            self._log_response(method, full_url, 0, "", trace_id, duration, error_msg)
            
            raise APIError(
                message=error_msg,
                code="REQUEST_ERROR",
                context={'url': full_url, 'method': method},
                trace_id=trace_id
            ) from e
    
    def get(self, url: str, params: Dict = None, **kwargs) -> Dict[str, Any]:
        """Make GET request."""
        return self._make_request('GET', url, params=params, **kwargs)
    
    def post(self, url: str, data: Dict = None, **kwargs) -> Dict[str, Any]:
        """Make POST request."""
        return self._make_request('POST', url, json=data, **kwargs)
    
    def put(self, url: str, data: Dict = None, **kwargs) -> Dict[str, Any]:
        """Make PUT request."""
        return self._make_request('PUT', url, json=data, **kwargs)
    
    def delete(self, url: str, **kwargs) -> Dict[str, Any]:
        """Make DELETE request."""
        return self._make_request('DELETE', url, **kwargs)

class FlutterwaveClient(APIClient):
    """Specialized client for Flutterwave API."""
    
    def __init__(self, api_key: str):
        super().__init__(base_url="https://api.flutterwave.com/v3")
        self.api_key = api_key
        self.session.headers.update({
            'Authorization': f'Bearer {api_key}'
        })
    
    def initiate_transfer(self, amount: float, beneficiary_name: str, 
                         account_number: str, account_bank: str, 
                         reference: str = None, **kwargs) -> Dict[str, Any]:
        """
        Initiate a transfer with enhanced error handling.
        
        Returns:
            Structured response with success status, data, and error info
        """
        if not reference:
            reference = f"vc_transfer_{uuid.uuid4().hex[:8]}"
        
        payload = {
            "account_bank": account_bank,
            "account_number": account_number,
            "amount": amount,
            "narration": kwargs.get("narration", "ViralCore Withdrawal"),
            "currency": kwargs.get("currency", "NGN"),
            "reference": reference,
            "beneficiary_name": beneficiary_name,
            "debit_currency": kwargs.get("debit_currency"),
            "callback_url": kwargs.get("callback_url")
        }
        
        # Remove None values
        payload = {k: v for k, v in payload.items() if v is not None}
        
        try:
            result = self.post("transfers", payload)
            
            # Parse Flutterwave-specific response
            if result['success'] and result['data'].get('status') == 'success':
                return {
                    'success': True,
                    'status': 'success',
                    'data': result['data'],
                    'trace_id': result['trace_id'],
                    'reference': reference
                }
            else:
                return {
                    'success': False,
                    'status': 'failed',
                    'error': result['data'].get('message', 'Transfer failed'),
                    'data': result['data'],
                    'trace_id': result['trace_id']
                }
                
        except APIError as e:
            return {
                'success': False,
                'status': 'error',
                'error': e.message,
                'code': e.code,
                'trace_id': e.trace_id,
                'context': e.context
            }

def create_user_friendly_error_message(error: Union[APIError, Exception], 
                                     operation: str = "operation") -> str:
    """
    Convert technical errors into user-friendly messages.
    
    Args:
        error: The error object
        operation: Description of the operation that failed
    
    Returns:
        User-friendly error message
    """
    if isinstance(error, APIError):
        if error.code == "TIMEOUT":
            return f"The {operation} is taking longer than usual. Please try again in a few minutes."
        elif error.code == "CONNECTION_ERROR":
            return f"Unable to connect to the service. Please check your internet connection and try again."
        elif error.code.startswith("HTTP_4"):
            return f"There was an issue with your {operation} request. Please verify your details and try again."
        elif error.code.startswith("HTTP_5"):
            return f"The service is temporarily unavailable. Please try your {operation} again later."
        else:
            return f"An unexpected error occurred during {operation}. Please contact support if this continues."
    else:
        return f"An unexpected error occurred during {operation}. Please try again or contact support."

def create_admin_error_message(error: Union[APIError, Exception], 
                              operation: str = "operation") -> str:
    """
    Create detailed error message for admin/logs.
    
    Args:
        error: The error object
        operation: Description of the operation that failed
    
    Returns:
        Detailed error message for admin
    """
    if isinstance(error, APIError):
        return (
            f"API Error in {operation}:\n"
            f"Code: {error.code}\n"
            f"Message: {error.message}\n"
            f"Trace ID: {error.trace_id}\n"
            f"Timestamp: {error.timestamp}\n"
            f"Context: {json.dumps(error.context, indent=2)}"
        )
    else:
        return f"System Error in {operation}: {str(error)}"

# Global clients
_flutterwave_client = None

def get_flutterwave_client() -> FlutterwaveClient:
    """Get or create Flutterwave client instance."""
    global _flutterwave_client
    
    if _flutterwave_client is None:
        from utils.config import APIConfig
        _flutterwave_client = FlutterwaveClient(APIConfig.FLUTTERWAVE_API_KEY)
    
    return _flutterwave_client