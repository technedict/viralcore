#!/usr/bin/env python3
"""
Tests for the messaging and MarkdownV2 functionality.
"""

import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.messaging import escape_markdown_v2, render_markdown_v2, validate_template, _strip_markdown
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
        
        print("\n✅ All messaging tests passed!")
        return 0
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())