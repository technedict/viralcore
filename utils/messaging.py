#!/usr/bin/env python3
"""
Messaging utilities for safe MarkdownV2 handling and template rendering.
Fixes issues with over-escaping templates and provides safe send functionality.

This module provides:
- escape_markdown_v2(): Escape special characters for Telegram MarkdownV2 parse mode
- escape_markdown(): Escape special characters for legacy Telegram Markdown parse mode  
- sanitize_html(): Remove dangerous HTML but preserve allowed tags for HTML parse mode
- format_safe(): Fill templates and escape values based on parse_mode
- render_markdown_v2(): Render MarkdownV2 templates with escaped variables
- safe_send(): Send messages with automatic fallback on parse errors
"""

import logging
import re
import html as html_module
from typing import Dict, Any, Optional, Union

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

# ============================================================================
# MarkdownV2 Special Characters (per Telegram Bot API specification)
# https://core.telegram.org/bots/api#markdownv2-style
# ============================================================================
MARKDOWN_V2_SPECIAL_CHARS = ['\\', '_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']

# Legacy Markdown special characters (subset of MarkdownV2)
MARKDOWN_SPECIAL_CHARS = ['\\', '_', '*', '`', '[']

# HTML tags allowed by Telegram (for sanitize_html)
ALLOWED_HTML_TAGS = {'b', 'strong', 'i', 'em', 'u', 'ins', 's', 'strike', 'del', 
                     'span', 'tg-spoiler', 'a', 'code', 'pre', 'tg-emoji'}


def escape_markdown_v2(text: str) -> str:
    """
    Escape MarkdownV2 special characters in user-supplied text.
    
    According to Telegram MarkdownV2 specification, these characters need escaping:
    '_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!'
    
    Note: Backslashes must be escaped first to avoid double-escaping.
    Note: '$' and '@' are NOT special in MarkdownV2.
    
    Args:
        text: Text to escape (user input, dynamic values)
        
    Returns:
        Text with MarkdownV2 special characters escaped
        
    Example:
        >>> escape_markdown_v2("Hello_world!")
        'Hello\\_world\\!'
        >>> escape_markdown_v2("Price: $100.50")
        'Price: $100\\.50'
    """
    if not isinstance(text, str):
        text = str(text)
    
    result = text
    for char in MARKDOWN_V2_SPECIAL_CHARS:
        result = result.replace(char, f'\\{char}')
    
    return result


def escape_markdown(text: str) -> str:
    """
    Escape special characters for legacy Telegram Markdown parse mode.
    
    Legacy Markdown has fewer special characters than MarkdownV2:
    '_', '*', '`', '['
    
    Args:
        text: Text to escape (user input, dynamic values)
        
    Returns:
        Text with Markdown special characters escaped
        
    Example:
        >>> escape_markdown("Hello_world")
        'Hello\\_world'
        >>> escape_markdown("Use `code` blocks")
        'Use \\`code\\` blocks'
    """
    if not isinstance(text, str):
        text = str(text)
    
    result = text
    for char in MARKDOWN_SPECIAL_CHARS:
        result = result.replace(char, f'\\{char}')
    
    return result


def sanitize_html(text: str, preserve_allowed_tags: bool = True) -> str:
    """
    Sanitize text for HTML parse mode in Telegram.
    
    Removes or escapes dangerous HTML while optionally preserving
    Telegram-allowed tags (b, i, u, s, code, pre, a, etc.).
    
    Args:
        text: Text to sanitize (may contain user input)
        preserve_allowed_tags: If True, keep allowed Telegram HTML tags.
                               If False, escape all HTML.
        
    Returns:
        Sanitized text safe for HTML parse mode
        
    Example:
        >>> sanitize_html("<script>alert('xss')</script>Hello")
        '&lt;script&gt;alert(\\'xss\\')&lt;/script&gt;Hello'
        >>> sanitize_html("<b>Bold</b> and <evil>bad</evil>")
        '<b>Bold</b> and &lt;evil&gt;bad&lt;/evil&gt;'
    """
    if not isinstance(text, str):
        text = str(text)
    
    if not preserve_allowed_tags:
        # Escape all HTML entities
        return html_module.escape(text)
    
    # Preserve allowed tags while escaping others
    # Pattern to match HTML tags
    tag_pattern = re.compile(r'<(/?)(\w+)([^>]*)>')
    
    def replace_tag(match):
        is_closing = match.group(1)
        tag_name = match.group(2).lower()
        attributes = match.group(3)
        
        if tag_name in ALLOWED_HTML_TAGS:
            # Keep allowed tags, but sanitize attributes for safety
            if tag_name == 'a' and attributes:
                # Only allow href attribute for links
                href_match = re.search(r'href\s*=\s*["\']([^"\']+)["\']', attributes, re.IGNORECASE)
                if href_match:
                    href = html_module.escape(href_match.group(1))
                    return f'<{is_closing}a href="{href}">'
                return f'<{is_closing}a>'
            return f'<{is_closing}{tag_name}>'
        else:
            # Escape disallowed tags
            return html_module.escape(match.group(0))
    
    result = tag_pattern.sub(replace_tag, text)
    
    # Escape any remaining < or > that aren't part of valid tags
    # This is a simplified approach - in production you might want more thorough parsing
    
    return result


def format_safe(template: str, values: Dict[str, Any], parse_mode: str = 'MarkdownV2') -> str:
    """
    Fill a template with values, escaping them based on parse_mode.
    
    This is the recommended way to create messages with dynamic content.
    The template structure (formatting markers like *bold*) is preserved,
    while all values are properly escaped for the target parse mode.
    
    Args:
        template: Template string with {placeholder} markers
        values: Dictionary of placeholder names to values
        parse_mode: 'MarkdownV2', 'Markdown', 'HTML', or None
        
    Returns:
        Rendered template with safely escaped values
        
    Example:
        >>> format_safe("Hello *{name}*!", {"name": "John_Doe"}, "MarkdownV2")
        'Hello *John\\_Doe*!'
        >>> format_safe("Hello <b>{name}</b>!", {"name": "<script>"}, "HTML")
        'Hello <b>&lt;script&gt;</b>!'
    """
    escaped_values = {}
    
    for key, value in values.items():
        str_value = str(value) if value is not None else ''
        
        if parse_mode == 'MarkdownV2':
            escaped_values[key] = escape_markdown_v2(str_value)
        elif parse_mode == 'Markdown':
            escaped_values[key] = escape_markdown(str_value)
        elif parse_mode == 'HTML':
            escaped_values[key] = sanitize_html(str_value, preserve_allowed_tags=False)
        else:
            # No parse mode - no escaping needed
            escaped_values[key] = str_value
    
    try:
        return template.format(**escaped_values)
    except KeyError as e:
        logger.error(f"Missing template variable: {e}")
        return template + f" [ERROR: Missing variable {e}]"
    except Exception as e:
        logger.error(f"Template formatting error: {e}")
        return template + f" [ERROR: {e}]"


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