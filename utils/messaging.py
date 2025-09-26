#!/usr/bin/env python3
"""
Messaging utilities for safe MarkdownV2 handling and template rendering.
Fixes issues with over-escaping templates and provides safe send functionality.
"""

import logging
import re
from typing import Dict, Any, Optional

try:
    from telegram import Bot
    from telegram.error import BadRequest
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    Bot = None
    BadRequest = None

from utils.logging import get_logger, correlation_context

logger = get_logger(__name__)


def escape_markdown_v2(text: str) -> str:
    """
    Escape MarkdownV2 special characters in user-supplied text only.
    
    According to Telegram MarkdownV2 specification, these characters need escaping:
    '_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!'
    
    Args:
        text: Text to escape
        
    Returns:
        Text with MarkdownV2 special characters escaped
    """
    if not isinstance(text, str):
        text = str(text)
    
    # Characters that must be escaped in MarkdownV2 (official Telegram spec)
    # Note: Order matters, escape backslashes first, and '$' and '@' are NOT special in MarkdownV2
    escape_chars = ['\\', '_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    
    result = text
    for char in escape_chars:
        result = result.replace(char, f'\\{char}')
    
    return result


def render_markdown_v2(template: str, **variables) -> str:
    """
    Safely render a MarkdownV2 template with escaped variables.
    
    Template should contain placeholder variables like {username}, {amount}, etc.
    Only the variable values will be escaped, not the template structure.
    
    Args:
        template: MarkdownV2 template string with {variable} placeholders
        **variables: Variable values to substitute (will be escaped)
        
    Returns:
        Rendered template with safely escaped variables
        
    Example:
        template = "Hello *{username}*! Your balance is ${amount}"
        result = render_markdown_v2(template, username="john_doe", amount="100.50")
        # Result: "Hello *john\\_doe*! Your balance is $100\\.50"
    """
    # Escape all variable values
    escaped_vars = {}
    for key, value in variables.items():
        escaped_vars[key] = escape_markdown_v2(str(value))
    
    try:
        return template.format(**escaped_vars)
    except KeyError as e:
        logger.error(f"Missing template variable: {e}")
        # Return template with missing variables highlighted
        return template + f" [ERROR: Missing variable {e}]"
    except Exception as e:
        logger.error(f"Template rendering error: {e}")
        return template + f" [ERROR: {e}]"


async def safe_send(
    bot,  # Bot type annotation removed to support optional telegram import
    chat_id: int,
    text: str,
    parse_mode: str = 'MarkdownV2',
    correlation_id: Optional[str] = None,
    **kwargs
) -> Optional[Any]:
    """
    Safely send a message with fallback on parse errors.
    
    If MarkdownV2 parsing fails, tries HTML, then plain text, then sends as document.
    
    Args:
        bot: Telegram Bot instance
        chat_id: Target chat ID
        text: Message text
        parse_mode: Initial parse mode to try ('MarkdownV2', 'HTML', None)
        correlation_id: Optional correlation ID for logging
        **kwargs: Additional arguments for send_message
        
    Returns:
        Message object if successful, None if all attempts failed
    """
    
    if not TELEGRAM_AVAILABLE:
        logger.error("Telegram library not available, cannot send message")
        return None
    
    with correlation_context(correlation_id) as corr_id:
        # Try primary parse mode
        try:
            logger.debug(f"Sending message with {parse_mode} parse mode")
            return await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
                **kwargs
            )
        except BadRequest as e:
            if "parse" in str(e).lower() or "invalid" in str(e).lower():
                logger.warning(f"Parse error with {parse_mode}: {e}")
                
                # Try HTML fallback
                if parse_mode != 'HTML':
                    try:
                        logger.debug("Falling back to HTML parse mode")
                        # Convert basic MarkdownV2 to HTML
                        html_text = _markdown_to_html_fallback(text)
                        return await bot.send_message(
                            chat_id=chat_id,
                            text=html_text,
                            parse_mode='HTML',
                            **kwargs
                        )
                    except BadRequest as e2:
                        logger.warning(f"HTML fallback failed: {e2}")
                
                # Try plain text fallback
                try:
                    logger.debug("Falling back to plain text")
                    # Strip markdown formatting for plain text
                    plain_text = _strip_markdown(text)
                    return await bot.send_message(
                        chat_id=chat_id,
                        text=plain_text,
                        parse_mode=None,
                        **kwargs
                    )
                except BadRequest as e3:
                    logger.warning(f"Plain text fallback failed: {e3}")
                
                # Final fallback: send as document
                try:
                    logger.info("All parse modes failed, sending as document")
                    from io import BytesIO
                    
                    doc = BytesIO(text.encode('utf-8'))
                    doc.name = f"message_{corr_id}.txt"
                    
                    return await bot.send_document(
                        chat_id=chat_id,
                        document=doc,
                        caption="Message content (formatting failed)",
                        **{k: v for k, v in kwargs.items() if k not in ['reply_markup']}
                    )
                except Exception as e4:
                    logger.error(f"Document fallback failed: {e4}")
                    
            else:
                # Non-parse error, re-raise
                logger.error(f"Non-parse error sending message: {e}")
                raise
                
        except Exception as e:
            logger.error(f"Unexpected error sending message: {e}")
            raise
    
    return None


def _markdown_to_html_fallback(text: str) -> str:
    """
    Convert basic MarkdownV2 formatting to HTML.
    
    This is a simple fallback conversion, not comprehensive.
    """
    # Convert bold
    text = re.sub(r'\*([^*]+)\*', r'<b>\1</b>', text)
    
    # Convert italic (single underscore, avoiding escaped ones)
    text = re.sub(r'(?<!\\)_([^_]+)_', r'<i>\1</i>', text)
    
    # Convert code (single backtick)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    
    # Remove escaping for HTML
    text = text.replace('\\_', '_')
    text = text.replace('\\*', '*')
    text = text.replace('\\[', '[')
    text = text.replace('\\]', ']')
    text = text.replace('\\(', '(')
    text = text.replace('\\)', ')')
    text = text.replace('\\.', '.')
    text = text.replace('\\!', '!')
    
    return text


def _strip_markdown(text: str) -> str:
    """
    Strip all markdown formatting for plain text fallback.
    """
    # Remove bold/italic markers (not escaped ones)
    text = re.sub(r'(?<!\\)\*([^*]+)(?<!\\)\*', r'\1', text)
    text = re.sub(r'(?<!\\)_([^_]+)(?<!\\)_', r'\1', text)
    
    # Remove code markers
    text = re.sub(r'(?<!\\)`([^`]+)(?<!\\)`', r'\1', text)
    
    # Remove links, keep text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    
    # Remove all escape sequences (backslash + special char → just the char)
    escape_chars = ['*', '_', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in escape_chars:
        text = text.replace(f'\\{char}', char)
    
    # Remove remaining double backslashes
    text = text.replace('\\\\', '\\')
    
    return text


def validate_template(template: str, required_vars: list) -> tuple[bool, list]:
    """
    Validate that a template contains all required variables.
    
    Args:
        template: Template string to validate
        required_vars: List of required variable names
        
    Returns:
        Tuple of (is_valid, missing_variables)
    """
    missing_vars = []
    
    for var in required_vars:
        if f'{{{var}}}' not in template:
            missing_vars.append(var)
    
    return len(missing_vars) == 0, missing_vars


def log_parse_error(error: Exception, template: str, variables: Dict[str, Any], correlation_id: str):
    """
    Log parse error with context for debugging.
    
    Args:
        error: Parse error exception
        template: Template that failed
        variables: Variables used in template
        correlation_id: Correlation ID for tracking
    """
    logger.error(
        f"MarkdownV2 parse error: {error}",
        extra={
            'correlation_id': correlation_id,
            'template_preview': template[:200] + "..." if len(template) > 200 else template,
            'variable_count': len(variables),
            'variables': list(variables.keys())
        }
    )


# Common templates for the bot (examples of proper usage)
TEMPLATES = {
    'balance_alert': (
        "🔔 *Boost Service Balance Alert* 🔔\n\n"
        "Current balance on {provider_name} for boosting is low: "
        "{currency} {balance}\n\n"
        "Kindly top up your balance to continue boosting services\\.\n\n"
    ),
    
    'boost_success': (
        "✅ *Boost Order Successful* ✅\n\n"
        "🔗 *Link*: {link}\n"
        "📢 *Provider*: {provider_name}\n"
        "🛠️ *Service ID*: {service_id}\n"
        "📦 *Quantity*: {quantity}\n"
        "🆔 *Order ID*: {order_id}"
    ),
    
    'boost_failed': (
        "❗ *Boost Order Failed* ❗\n\n"
        "🔗 *Link*: {link}\n"
        "📢 *Provider*: {provider_name}\n"
        "🛠️ *Service ID*: {service_id}\n"
        "📦 *Quantity*: {quantity}\n"
        "⚠️ *Reason*: {reason}"
    ),
    
    'provider_switched': (
        "✅ Boost provider switched to: *{provider_name}*"
    ),
    
    'balance_info': (
        "💰 *Your Balance*\n\n"
        "Affiliate Balance: ${affiliate_balance}\n"
        "Reply Balance: ₦{reply_balance}"
    )
}