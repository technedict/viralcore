# Telegram Message Formatting - Technical Note

## Root Causes Analysis

After auditing the codebase, the following root causes were identified for Telegram message formatting issues:

### Root Cause 1: Inconsistent Escaping Approaches

**Problem**: Different parts of the codebase used different escaping methods:
- Some files had local `escape_md()` functions
- Some used `telegram.helpers.escape_markdown()`
- Some used hardcoded escape sequences
- Some used the central `escape_markdown_v2()` from `utils/messaging.py`

**Impact**: This led to inconsistent behavior where some messages displayed correctly while others showed visible backslashes or broke entirely.

**Example Found**:
```python
# In utils/notification_service.py - local escape function missing backslash handling
def escape_md(text: str) -> str:
    special_chars = ['_', '*', '[', ']', ...]  # Missing '\\'
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text
```

### Root Cause 2: Pre-Escaped Template Strings

**Problem**: Template strings contained pre-escaped characters like `\\!` and `\\.` mixed with dynamic values that weren't escaped.

**Impact**: When dynamic values contained special characters, the message would fail to parse, while the template structure appeared to work in isolation.

**Example Found**:
```python
# Pre-escaped static text, but dynamic values weren't escaped
message = f"✅ Request Approved\\!\nUser: {username}"  # username not escaped
```

### Root Cause 3: Missing Escape for Dynamic Values

**Problem**: User-provided data (usernames, bank names, transaction IDs, URLs) were inserted directly into MarkdownV2 messages without escaping.

**Impact**: If a username contained underscores (common in Twitter usernames like `john_doe`), the message would break or display incorrectly.

**Example Found**:
```python
admin_message = (
    f"User ID: `{user_id}`\n"
    f"Username: @{user_username if user_username else 'N/A'}\n"  # Not escaped
)
```

### Root Cause 4: Mixed Parse Modes

**Problem**: Some handlers use MarkdownV2, others use legacy Markdown, and others use HTML. The escaping requirements are different for each.

**Impact**: Using MarkdownV2 escaping with Markdown parse_mode (or vice versa) causes visible escape characters or parsing failures.

**Example Found**:
```python
# Template uses MarkdownV2-style escaping
text = f"Status: *{status}*\\."
# But message is sent with legacy Markdown
await msg.reply_text(text, parse_mode="Markdown")  # Wrong!
```

---

## Fixes Implemented

1. **Centralized Escape Helpers** (`utils/messaging.py`):
   - `escape_markdown_v2()` - Escapes all 19 MarkdownV2 special characters
   - `escape_markdown()` - Escapes legacy Markdown characters
   - `sanitize_html()` - Sanitizes HTML for Telegram
   - `format_safe()` - Template formatting with auto-escaping by parse_mode

2. **Updated Notification Service**: Replaced local `escape_md()` with central `escape_markdown_v2()`

3. **Fixed Handler Templates**: Added proper escaping for dynamic values in:
   - `admin_withdrawal_handlers.py`
   - `payment_utils.py`

4. **Added Comprehensive Tests**: Unit tests for all escape functions, malicious input handling, and representative templates

---

## Recommended Follow-Up Items

### Recommendation 1: Template Style Guide

Create a template style guide document that defines:

- **Template format requirements**: All templates should use `{placeholder}` syntax for dynamic values
- **Naming conventions**: Template names should follow `snake_case`
- **Required fields**: Each template should have documented required variables
- **Parse mode labeling**: Templates should be labeled with their target parse mode

**Implementation**:
```python
# Example template registry with metadata
TEMPLATES = {
    'withdrawal_approved': {
        'template': "✅ *Withdrawal Approved*\n\nAmount: ₦{amount}\nUser: {username}",
        'parse_mode': 'MarkdownV2',
        'required_vars': ['amount', 'username'],
        'description': 'Sent to user when withdrawal is approved'
    }
}
```

### Recommendation 2: Template Validator

Implement a CI/CD check that validates templates before deployment:

**Features**:
- Detect templates with mixed escaping (pre-escaped + unescaped)
- Verify all placeholders are documented
- Check for common escaping mistakes
- Validate parse_mode compatibility

**Implementation**:
```python
# Add to CI pipeline
def validate_template(template: str, parse_mode: str) -> list[str]:
    issues = []
    
    # Check for unbalanced formatting
    if template.count('*') % 2 != 0:
        issues.append("Unbalanced bold markers (*)")
    
    # Check for double-escaped characters
    if '\\\\.' in template:
        issues.append("Double-escaped period found")
    
    # Check for missing escapes in static text
    if parse_mode == 'MarkdownV2':
        for char in ['.', '!']:
            if char in template and f'\\{char}' not in template:
                issues.append(f"Unescaped '{char}' in MarkdownV2 template")
    
    return issues
```

### Recommendation 3: Stricter Template Storage Rules

If templates are stored externally (database, config files):

**Rules**:
1. **Store templates unescaped**: Templates should be stored without pre-escaping
2. **Escape at render time**: Use `format_safe()` when rendering
3. **Version templates**: Track template changes with version numbers
4. **Migration support**: Provide tools to migrate old escaped templates

**Database Schema Example**:
```sql
CREATE TABLE message_templates (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    template TEXT NOT NULL,  -- Stored WITHOUT escaping
    parse_mode TEXT DEFAULT 'MarkdownV2',
    required_vars TEXT,  -- JSON array of variable names
    version INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Migration Script**:
```python
def migrate_template(old_template: str) -> str:
    """Convert pre-escaped template to clean format."""
    # Remove pre-escaping from template structure
    clean = old_template
    clean = clean.replace('\\!', '!')
    clean = clean.replace('\\.', '.')
    # ... more replacements
    return clean
```

---

## Summary

The Telegram message formatting issues stemmed from inconsistent escaping practices across the codebase. By centralizing escape helpers and establishing clear guidelines, future formatting issues can be prevented.

The three recommended follow-ups (style guide, validator, storage rules) will help maintain message quality as the codebase grows.
