#!/usr/bin/env python3
"""
Tests for the messaging and MarkdownV2 functionality.

This module tests:
- escape_markdown_v2(): MarkdownV2 special character escaping
- escape_markdown(): Legacy Markdown special character escaping
- sanitize_html(): HTML sanitization for Telegram
- format_safe(): Template formatting with auto-escaping based on parse_mode
- render_markdown_v2(): MarkdownV2 template rendering
- validate_template(): Template variable validation
- _strip_markdown(): Markdown stripping for plain text fallback
"""

import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.messaging import (
    escape_markdown_v2, 
    escape_markdown,
    sanitize_html,
    format_safe,
    render_markdown_v2, 
    validate_template, 
    _strip_markdown
)
from utils.logging import setup_logging

def test_escape_markdown_v2():
    """Test MarkdownV2 escaping functionality."""
    print("Testing MarkdownV2 escaping...")
    
    # Test basic special characters (according to official Telegram MarkdownV2 spec)
    test_cases = [
        ("Hello_world!", "Hello\\_world\\!"),
        ("Price: $100.50", "Price: $100\\.50"),  # $ is NOT special in MarkdownV2
        ("User@domain.com", "User@domain\\.com"),  # @ is NOT special in MarkdownV2  
        ("Test [link](url)", "Test \\[link\\]\\(url\\)"),
        ("Hash #tag", "Hash \\#tag"),
        ("Code `block`", "Code \\`block\\`"),
    ]
    
    for original, expected in test_cases:
        escaped = escape_markdown_v2(original)
        assert escaped == expected, f"Expected {expected}, got {escaped}"
        print(f"✓ '{original}' -> '{escaped}'")
    
    # Test empty string
    assert escape_markdown_v2("") == ""
    print("✓ Empty string handled")
    
    # Test non-string input
    assert escape_markdown_v2(123) == "123"
    print("✓ Non-string input handled")


def test_render_markdown_v2():
    """Test template rendering with escaping."""
    print("Testing template rendering...")
    
    # Test basic template
    template = "Hello *{username}*! Your balance is ${amount}."
    rendered = render_markdown_v2(template, username="john_doe", amount="100.50")
    expected = "Hello *john\\_doe*! Your balance is $100\\.50."
    assert rendered == expected, f"Expected {expected}, got {rendered}"
    print(f"✓ Basic template: '{rendered}'")
    
    # Test template with special characters in variables (@ is NOT escaped in MarkdownV2)
    template = "Welcome *{name}*! Visit {url}"
    rendered = render_markdown_v2(template, name="user@domain.com", url="https://example.com")
    expected = "Welcome *user@domain\\.com*! Visit https://example\\.com"
    assert rendered == expected, f"Expected {expected}, got {rendered}"
    print(f"✓ Special chars in vars: '{rendered}'")
    
    # Test missing variable
    template = "Hello {name}! Your score: {score}"
    rendered = render_markdown_v2(template, name="Alice")  # Missing score
    assert "ERROR: Missing variable" in rendered
    print("✓ Missing variable handled")
    
    # Test complex template
    template = "🔔 *Balance Alert*\\n\\nProvider: {provider}\\nBalance: {currency} {amount}\\."
    rendered = render_markdown_v2(template, provider="test_provider", currency="USD", amount="5.50")
    print(f"✓ Complex template: '{rendered}'")


def test_validate_template():
    """Test template validation."""
    print("Testing template validation...")
    
    template = "Hello {name}! Balance: {amount}"
    
    # Test valid template
    valid, missing = validate_template(template, ['name', 'amount'])
    assert valid == True
    assert missing == []
    print("✓ Valid template passes")
    
    # Test missing variables
    valid, missing = validate_template(template, ['name', 'amount', 'email'])
    assert valid == False
    assert 'email' in missing
    print(f"✓ Missing variables detected: {missing}")
    
    # Test extra variables - should still be valid (template has name/amount, we only require name)
    valid, missing = validate_template(template, ['name'])
    assert valid == True  # Should be valid since 'name' is present in template
    assert missing == []
    print("✓ Subset of variables allowed")


def test_strip_markdown():
    """Test markdown stripping for fallback."""
    print("Testing markdown stripping...")
    
    test_cases = [
        ("*bold text*", "bold text"),
        ("_italic text_", "italic text"),
        ("`code block`", "code block"),
        ("[link text](url)", "link text"),
        ("\\*escaped\\*", "*escaped*"),
        ("Multiple *bold* and _italic_ text", "Multiple bold and italic text"),
    ]
    
    for markdown, expected in test_cases:
        stripped = _strip_markdown(markdown)
        assert stripped == expected, f"Expected {expected}, got {stripped}"
        print(f"✓ '{markdown}' -> '{stripped}'")


def test_edge_cases():
    """Test edge cases and error conditions."""
    print("Testing edge cases...")
    
    # Empty template
    result = render_markdown_v2("", name="test")
    assert result == ""
    print("✓ Empty template handled")
    
    # Template with no variables
    result = render_markdown_v2("Static text")
    assert result == "Static text"
    print("✓ Static template handled")
    
    # Very long text
    long_text = "a" * 1000
    escaped = escape_markdown_v2(long_text)
    assert len(escaped) == 1000  # No special chars to escape
    print("✓ Long text handled")
    
    # Special characters that shouldn't be escaped in template structure
    template = "*{text}* and `{code}`"
    rendered = render_markdown_v2(template, text="hello", code="print()")
    expected = "*hello* and `print\\(\\)`"
    assert rendered == expected
    print(f"✓ Template structure preserved: '{rendered}'")


def test_escape_markdown():
    """Test legacy Markdown escaping functionality."""
    print("Testing legacy Markdown escaping...")
    
    # Test basic special characters (legacy Markdown has fewer)
    test_cases = [
        ("Hello_world", "Hello\\_world"),
        ("Bold *text*", "Bold \\*text\\*"),
        ("Code `block`", "Code \\`block\\`"),
        ("[link]", "\\[link]"),  # Only [ is escaped in legacy
        ("Normal.text!", "Normal.text!"),  # . and ! NOT escaped in legacy Markdown
    ]
    
    for original, expected in test_cases:
        escaped = escape_markdown(original)
        assert escaped == expected, f"Expected {expected}, got {escaped}"
        print(f"✓ '{original}' -> '{escaped}'")


def test_sanitize_html():
    """Test HTML sanitization for Telegram."""
    print("Testing HTML sanitization...")
    
    # Test basic HTML escaping (single quotes are escaped as &#x27; by html.escape)
    test_cases = [
        ("<script>alert(1)</script>", "&lt;script&gt;alert(1)&lt;/script&gt;"),
        ("Hello <world>", "Hello &lt;world&gt;"),
        ("A & B", "A &amp; B"),
    ]
    
    for original, expected in test_cases:
        sanitized = sanitize_html(original, preserve_allowed_tags=False)
        assert sanitized == expected, f"Expected {expected}, got {sanitized}"
        print(f"✓ '{original}' -> '{sanitized}'")
    
    # Test preserving allowed tags
    allowed_tag_cases = [
        ("<b>Bold</b>", "<b>Bold</b>"),
        ("<i>Italic</i>", "<i>Italic</i>"),
        ("<code>code</code>", "<code>code</code>"),
    ]
    
    for original, expected in allowed_tag_cases:
        sanitized = sanitize_html(original, preserve_allowed_tags=True)
        assert sanitized == expected, f"Expected {expected}, got {sanitized}"
        print(f"✓ Allowed tag preserved: '{original}'")


def test_format_safe():
    """Test the format_safe helper for all parse modes."""
    print("Testing format_safe...")
    
    template = "Hello *{name}*! Your balance is ${amount}."
    values = {"name": "John_Doe", "amount": "100.50"}
    
    # Test MarkdownV2
    result = format_safe(template, values, "MarkdownV2")
    expected = "Hello *John\\_Doe*! Your balance is $100\\.50."
    assert result == expected, f"MarkdownV2: Expected {expected}, got {result}"
    print(f"✓ MarkdownV2: '{result}'")
    
    # Test legacy Markdown
    result = format_safe(template, values, "Markdown")
    expected = "Hello *John\\_Doe*! Your balance is $100.50."
    assert result == expected, f"Markdown: Expected {expected}, got {result}"
    print(f"✓ Markdown: '{result}'")
    
    # Test HTML
    html_template = "Hello <b>{name}</b>! Script: {script}"
    html_values = {"name": "User", "script": "<script>"}
    result = format_safe(html_template, html_values, "HTML")
    expected = "Hello <b>User</b>! Script: &lt;script&gt;"
    assert result == expected, f"HTML: Expected {expected}, got {result}"
    print(f"✓ HTML: '{result}'")
    
    # Test no parse mode (no escaping)
    result = format_safe(template, values, None)
    expected = "Hello *John_Doe*! Your balance is $100.50."
    assert result == expected, f"None: Expected {expected}, got {result}"
    print(f"✓ No parse mode: '{result}'")


def test_malicious_inputs():
    """Test handling of potentially malicious user inputs."""
    print("Testing malicious input handling...")
    
    # MarkdownV2 injection attempts
    malicious_cases = [
        ("*bold attempt*", "\\*bold attempt\\*"),
        ("_italic_attempt_", "\\_italic\\_attempt\\_"),
        ("[link](http://evil.com)", "\\[link\\]\\(http://evil\\.com\\)"),
        ("```code block```", "\\`\\`\\`code block\\`\\`\\`"),
        ("\\escape\\me\\", "\\\\escape\\\\me\\\\"),
        ("Emoji 🎉 test", "Emoji 🎉 test"),  # Emoji should pass through
        ("مرحبا العالم", "مرحبا العالم"),  # Arabic text should pass through
        ("日本語テスト", "日本語テスト"),  # Japanese text should pass through
    ]
    
    for original, expected in malicious_cases:
        escaped = escape_markdown_v2(original)
        assert escaped == expected, f"Expected {expected}, got {escaped}"
        preview = original[:20] + '...' if len(original) > 20 else original
        print(f"✓ Malicious input escaped: '{preview}'")
    
    # HTML injection attempts with sanitize_html
    html_malicious = [
        ("<script>alert(1)</script>", "&lt;script&gt;alert(1)&lt;/script&gt;"),
        ("<img onerror=alert(1)>", "&lt;img onerror=alert(1)&gt;"),
    ]
    
    for original, expected in html_malicious:
        sanitized = sanitize_html(original, preserve_allowed_tags=False)
        assert sanitized == expected, f"Expected {expected}, got {sanitized}"
        preview = original[:30] + '...' if len(original) > 30 else original
        print(f"✓ HTML injection blocked: '{preview}'")


def test_representative_templates():
    """Test real-world template patterns used in the bot."""
    print("Testing representative templates...")
    
    # Withdrawal approval message
    template = (
        "✅ *Withdrawal Approved*\n\n"
        "💵 Amount: ₦{amount}\n"
        "🏦 Bank: {bank}\n"
        "📝 Request ID: {request_id}"
    )
    values = {"amount": "5000.50", "bank": "First_Bank", "request_id": "WD-123"}
    result = format_safe(template, values, "MarkdownV2")
    assert "5000\\.50" in result
    assert "First\\_Bank" in result
    assert "WD\\-123" in result
    print("✓ Withdrawal template formatted correctly")
    
    # Admin notification
    template = (
        "🚀 *New Order*\n"
        "User: {username}\n"
        "Link: {link}\n"
        "Status: *Paid*"
    )
    values = {"username": "@john_doe", "link": "https://x.com/status/123"}
    result = format_safe(template, values, "MarkdownV2")
    assert "@john\\_doe" in result
    assert "https://x\\.com/status/123" in result
    print("✓ Admin notification template formatted correctly")
    
    # Balance info with currency symbols
    template = "Balance: ${usd} | ₦{ngn}"
    values = {"usd": "100.00", "ngn": "150000"}
    result = format_safe(template, values, "MarkdownV2")
    assert "$100\\.00" in result
    assert "₦150000" in result
    print("✓ Balance template formatted correctly")


def main():
    """Run all tests."""
    print("Starting messaging system tests...")
    
    # Setup logging
    setup_logging(console_log_level=30)  # WARNING level to reduce noise
    
    try:
        # Run tests
        test_escape_markdown_v2()
        test_render_markdown_v2()
        test_validate_template()
        test_strip_markdown()
        test_edge_cases()
        test_escape_markdown()
        test_sanitize_html()
        test_format_safe()
        test_malicious_inputs()
        test_representative_templates()
        
        print("\n✅ All messaging tests passed!")
        return 0
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())