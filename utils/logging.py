#!/usr/bin/env python3
"""
Enhanced logging configuration module for ViralCore bot.
Provides structured logging with correlation IDs, proper level filtering,
and secret sanitization.
"""

import logging
import logging.handlers
import json
import os
import re
import uuid
from typing import Dict, Any, Optional
from datetime import datetime
from contextlib import contextmanager


class CorrelationFilter(logging.Filter):
    """Adds correlation ID to log records."""
    
    def __init__(self):
        super().__init__()
        self._correlation_id = None
    
    def filter(self, record):
        if not hasattr(record, 'correlation_id'):
            record.correlation_id = self._correlation_id or 'none'
        return True
    
    def set_correlation_id(self, correlation_id: str):
        """Set correlation ID for current context."""
        self._correlation_id = correlation_id


class SecretSanitizer:
    """Sanitizes sensitive information from log messages and data."""
    
    # Enhanced patterns for sensitive data
    SENSITIVE_PATTERNS = [
        # API Keys and tokens - enhanced patterns
        (re.compile(r'(api[_-]?key["\']?\s*[:=]\s*["\']?)([^"\']+)', re.IGNORECASE), r'\1***REDACTED***'),
        (re.compile(r'(token["\']?\s*[:=]\s*["\']?)([^"\']+)', re.IGNORECASE), r'\1***REDACTED***'),
        (re.compile(r'(password["\']?\s*[:=]\s*["\']?)([^"\']+)', re.IGNORECASE), r'\1***REDACTED***'),
        (re.compile(r'(secret["\']?\s*[:=]\s*["\']?)([^"\']+)', re.IGNORECASE), r'\1***REDACTED***'),
        (re.compile(r'("key":\s*")([^"]+)', re.IGNORECASE), r'\1***REDACTED***'),
        (re.compile(r'(authorization["\']?\s*[:=]\s*["\']?bearer\s+)([^"\']+)', re.IGNORECASE), r'\1***REDACTED***'),
        
        # Specific service patterns
        (re.compile(r'(\d{10}:\w{35})', re.IGNORECASE), '***TELEGRAM_BOT_TOKEN***'),  # Telegram bot tokens
        (re.compile(r'(FLWSECK-[a-zA-Z0-9\-]+)', re.IGNORECASE), '***FLUTTERWAVE_KEY***'),  # Flutterwave keys
        (re.compile(r'(eyJ[a-zA-Z0-9_\-\.]{100,})', re.IGNORECASE), '***JWT_TOKEN***'),  # JWT tokens (longer ones)
        
        # Bank account patterns
        (re.compile(r'\b\d{10,}\b'), '***ACCOUNT***'),
        # Credit card patterns (basic)
        (re.compile(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b'), '***CARD***'),
        
        # Generic hex keys (40+ characters to avoid false positives)
        (re.compile(r'\b[a-fA-F0-9]{40,64}\b'), '***HEX_KEY***'),
    ]
    
    @classmethod
    def sanitize(cls, data: Any) -> Any:
        """
        Sanitize sensitive information from various data types.
        
        Args:
            data: Data to sanitize (str, dict, list, etc.)
            
        Returns:
            Sanitized data with sensitive information redacted
        """
        if isinstance(data, str):
            return cls._sanitize_string(data)
        elif isinstance(data, dict):
            return {k: cls.sanitize(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [cls.sanitize(item) for item in data]
        elif isinstance(data, tuple):
            return tuple(cls.sanitize(item) for item in data)
        else:
            return data
    
    @classmethod
    def _sanitize_string(cls, text: str) -> str:
        """Sanitize sensitive patterns in string."""
        if not isinstance(text, str):
            return text
            
        result = text
        for pattern, replacement in cls.SENSITIVE_PATTERNS:
            result = pattern.sub(replacement, result)
        return result


class StructuredFormatter(logging.Formatter):
    """JSON formatter with structured logging support."""
    
    def format(self, record):
        # Base log data
        log_data = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'module': record.name,
            'message': record.getMessage(),
            'correlation_id': getattr(record, 'correlation_id', 'none'),
        }
        
        # Add optional fields if present
        if hasattr(record, 'user_id'):
            log_data['user_id'] = record.user_id
        if hasattr(record, 'job_id'):
            log_data['job_id'] = record.job_id
        if hasattr(record, 'provider_name'):
            log_data['provider_name'] = record.provider_name
        if hasattr(record, 'response_truncated'):
            log_data['response_truncated'] = record.response_truncated
            
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
            
        # Sanitize sensitive data
        log_data = SecretSanitizer.sanitize(log_data)
        
        return json.dumps(log_data)


class SimpleFormatter(logging.Formatter):
    """Simple formatter with secret sanitization."""
    
    def format(self, record):
        # Apply standard formatting
        formatted = super().format(record)
        # Sanitize sensitive data
        return SecretSanitizer._sanitize_string(formatted)


def setup_logging(
    bot_log_level: int = logging.WARNING,
    console_log_level: int = logging.INFO,
    debug_file_log_level: int = logging.DEBUG,
    log_file_path: str = "bot.log",
    debug_file_path: str = "debug.log",
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
    use_structured_format: bool = True
) -> Dict[str, logging.Handler]:
    """
    Setup comprehensive logging configuration.
    
    Args:
        bot_log_level: Level for bot.log file (WARNING and above)
        console_log_level: Level for console output
        debug_file_log_level: Level for debug file
        log_file_path: Path to main log file
        debug_file_path: Path to debug log file
        max_bytes: Maximum log file size before rotation
        backup_count: Number of backup files to keep
        use_structured_format: Use JSON structured format
        
    Returns:
        Dictionary of created handlers
    """
    
    # Create correlation filter
    correlation_filter = CorrelationFilter()
    
    # Setup formatters
    if use_structured_format:
        structured_formatter = StructuredFormatter()
        simple_formatter = SimpleFormatter(
            '%(asctime)s - %(name)s - %(levelname)s - [%(correlation_id)s] - %(message)s'
        )
    else:
        simple_formatter = SimpleFormatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        structured_formatter = simple_formatter
    
    handlers = {}
    
    # Bot log file handler (WARNING and ERROR only)
    bot_file_handler = logging.handlers.RotatingFileHandler(
        log_file_path, maxBytes=max_bytes, backupCount=backup_count
    )
    bot_file_handler.setLevel(bot_log_level)
    bot_file_handler.setFormatter(structured_formatter)
    bot_file_handler.addFilter(correlation_filter)
    handlers['bot_file'] = bot_file_handler
    
    # Debug file handler (INFO and DEBUG)
    debug_file_handler = logging.handlers.RotatingFileHandler(
        debug_file_path, maxBytes=max_bytes, backupCount=backup_count
    )
    debug_file_handler.setLevel(debug_file_log_level)
    debug_file_handler.setFormatter(structured_formatter)
    debug_file_handler.addFilter(correlation_filter)
    # Filter to exclude WARNING and above (they go to bot.log)
    debug_file_handler.addFilter(lambda record: record.levelno < logging.WARNING)
    handlers['debug_file'] = debug_file_handler
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_log_level)
    console_handler.setFormatter(simple_formatter)
    console_handler.addFilter(correlation_filter)
    handlers['console'] = console_handler
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Allow all levels, handlers will filter
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Add our handlers
    for handler in handlers.values():
        root_logger.addHandler(handler)
    
    # Set external library levels to WARNING
    for lib in ['httpx', 'httpcore', 'aiohttp', 'telegram', 'urllib3']:
        logging.getLogger(lib).setLevel(logging.WARNING)
    
    # Store correlation filter globally for access
    _correlation_filter = correlation_filter
    
    return handlers


def get_logger(name: str) -> logging.Logger:
    """Get a logger with proper configuration."""
    return logging.getLogger(name)


def log_provider_error(
    logger: logging.Logger,
    provider_name: str,
    error_response: Any,
    correlation_id: str,
    job_id: Optional[str] = None,
    user_id: Optional[int] = None
):
    """
    Log provider error with structured format and sanitization.
    
    Args:
        logger: Logger instance
        provider_name: Name of the external provider
        error_response: Raw error response from provider
        correlation_id: Request correlation ID
        job_id: Associated job ID if applicable
        user_id: Associated user ID if applicable
    """
    
    # Truncate response if too long
    response_str = str(error_response)
    truncated = False
    if len(response_str) > 1000:
        response_str = response_str[:1000] + "..."
        truncated = True
    
    logger.error(
        f"Provider API error: {provider_name}",
        extra={
            'correlation_id': correlation_id,
            'provider_name': provider_name,
            'job_id': job_id,
            'user_id': user_id,
            'response_truncated': truncated,
            'raw_response': response_str
        }
    )


@contextmanager
def correlation_context(correlation_id: Optional[str] = None):
    """
    Context manager for setting correlation ID.
    
    Args:
        correlation_id: Correlation ID to use, generates one if None
    """
    if correlation_id is None:
        correlation_id = str(uuid.uuid4())[:8]
    
    # Get the correlation filter from root logger
    root_logger = logging.getLogger()
    correlation_filter = None
    for handler in root_logger.handlers:
        for filter_obj in handler.filters:
            if isinstance(filter_obj, CorrelationFilter):
                correlation_filter = filter_obj
                break
        if correlation_filter:
            break
    
    if correlation_filter:
        old_id = correlation_filter._correlation_id
        correlation_filter.set_correlation_id(correlation_id)
        try:
            yield correlation_id
        finally:
            correlation_filter.set_correlation_id(old_id)
    else:
        yield correlation_id


# Global correlation filter reference
_correlation_filter: Optional[CorrelationFilter] = None


def set_correlation_id(correlation_id: str):
    """Set correlation ID globally."""
    global _correlation_filter
    if _correlation_filter:
        _correlation_filter.set_correlation_id(correlation_id)


def generate_correlation_id() -> str:
    """Generate a new correlation ID."""
    return str(uuid.uuid4())[:8]