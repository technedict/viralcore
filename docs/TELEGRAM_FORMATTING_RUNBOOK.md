# Telegram Message Formatting Runbook

This document provides guidance on how to validate Telegram message formatting fixes, including before/after examples and a rollback plan.

## Table of Contents

1. [Overview](#overview)
2. [Understanding MarkdownV2](#understanding-markdownv2)
3. [Using the Escape Helpers](#using-the-escape-helpers)
4. [Before/After Examples](#beforeafter-examples)
5. [Validation Steps](#validation-steps)
6. [Rollback Plan](#rollback-plan)
7. [Code Reviewer Checklist](#code-reviewer-checklist)

---

## Overview

Telegram's MarkdownV2 requires specific characters to be escaped when they appear in user-supplied text. The following characters must be escaped with a backslash (`\`):

```
_ * [ ] ( ) ~ ` > # + - = | { } . !
```

**Key Principle**: 
- **Template structure** (bold markers, italic markers, links) should NOT be escaped
- **User-supplied values** (usernames, amounts, bank names, etc.) MUST be escaped

---

## Understanding MarkdownV2

### What Gets Escaped

| Character | Meaning in MarkdownV2 | Must Escape in User Text |
|-----------|----------------------|-------------------------|
| `_` | Italic | Yes |
| `*` | Bold | Yes |
| `[` `]` | Link text | Yes |
| `(` `)` | Link URL | Yes |
| `~` | Strikethrough | Yes |
| ``` ` ``` | Inline code | Yes |
| `>` | Quote | Yes |
| `#` | Heading | Yes |
| `+` `-` `=` | List items | Yes |
| `|` | Table | Yes |
| `{` `}` | Reserved | Yes |
| `.` | Period | Yes |
| `!` | Exclamation | Yes |
| `\` | Escape character | Yes (must be first) |

### What Does NOT Need Escaping

| Character | Safe in MarkdownV2 |
|-----------|-------------------|
| `$` | Yes - currency symbols are safe |
| `@` | Yes - mention prefix is safe |
| `₦` | Yes - Naira symbol is safe |
| Emoji | Yes - all emoji are safe |
| Unicode | Yes - non-ASCII text is safe |

---

## Using the Escape Helpers

### Import the helpers

```python
from utils.messaging import escape_markdown_v2, format_safe, render_markdown_v2
```

### escape_markdown_v2(text)

Escapes a string for inclusion in MarkdownV2 messages.

```python
username = "john_doe"
safe_username = escape_markdown_v2(username)
# Returns: "john\_doe"
```

### format_safe(template, values, parse_mode)

Fills a template with values, automatically escaping based on parse_mode.

```python
template = "Hello *{name}*! Your balance is ${amount}."
message = format_safe(template, {"name": "John_Doe", "amount": "100.50"}, "MarkdownV2")
# Returns: "Hello *John\_Doe*! Your balance is $100\.50."
```

### render_markdown_v2(template, **kwargs)

Convenience wrapper for MarkdownV2 templates.

```python
message = render_markdown_v2(
    "Welcome *{username}*! Balance: ${balance}",
    username="john_doe",
    balance="50.00"
)
# Returns: "Welcome *john\_doe*! Balance: $50\.00"
```

---

## Before/After Examples

### Example 1: Withdrawal Approval Message

**BEFORE (Broken)**:
```python
# Raw template with unescaped values
message = f"✅ Withdrawal Approved!\nUser: {username}\nAmount: ₦{amount}"
await bot.send_message(chat_id, message, parse_mode='MarkdownV2')
# ERROR: "!" and "." are unescaped
```

**AFTER (Fixed)**:
```python
from utils.messaging import escape_markdown_v2

message = (
    f"✅ Withdrawal Approved\\!\n"
    f"User: {escape_markdown_v2(username)}\n"
    f"Amount: ₦{escape_markdown_v2(str(amount))}"
)
await bot.send_message(chat_id, message, parse_mode='MarkdownV2')
```

**Rendered Output**: ✅ Withdrawal Approved! User: john_doe Amount: ₦5000

---

### Example 2: Admin Notification with Link

**BEFORE (Broken)**:
```python
message = f"🚀 New Order!\nUser: @{username}\nLink: {twitter_link}"
await bot.send_message(chat_id, message, parse_mode='MarkdownV2')
# ERROR: "!" "." and underscores in URL are unescaped
```

**AFTER (Fixed)**:
```python
from utils.messaging import escape_markdown_v2

message = (
    f"🚀 New Order\\!\n"
    f"User: @{escape_markdown_v2(username)}\n"
    f"Link: {escape_markdown_v2(twitter_link)}"
)
await bot.send_message(chat_id, message, parse_mode='MarkdownV2')
```

---

### Example 3: Bank Details with Special Characters

**BEFORE (Broken)**:
```python
message = f"🏦 Bank: {bank_name}\n💳 Account: {account_number}\n👤 Name: {account_name}"
await bot.send_message(chat_id, message, parse_mode='MarkdownV2')
# ERROR: Bank names like "First_Bank" would break formatting
```

**AFTER (Fixed)**:
```python
from utils.messaging import escape_markdown_v2

message = (
    f"🏦 Bank: {escape_markdown_v2(bank_name)}\n"
    f"💳 Account: {escape_markdown_v2(account_number)}\n"
    f"👤 Name: {escape_markdown_v2(account_name)}"
)
await bot.send_message(chat_id, message, parse_mode='MarkdownV2')
```

---

### Example 4: Template with Bold and Code

**BEFORE (Broken)**:
```python
message = f"*Status*: {status}\n`Transaction ID`: {tx_id}"
await bot.send_message(chat_id, message, parse_mode='MarkdownV2')
# ERROR: If tx_id contains special chars, it breaks
```

**AFTER (Fixed)**:
```python
from utils.messaging import format_safe

message = format_safe(
    "*Status*: {status}\n`Transaction ID`: {tx_id}",
    {"status": status, "tx_id": tx_id},
    "MarkdownV2"
)
await bot.send_message(chat_id, message, parse_mode='MarkdownV2')
```

---

### Example 5: Complex Admin Message

**BEFORE (Broken)**:
```python
message = f"""
🔔 *NEW WITHDRAWAL REQUEST!* 🔔

User: [{first_name}](tg://user?id={user_id})
Amount: *₦{amount}*
Bank Details:
`{bank_details}`
"""
await bot.send_message(chat_id, message, parse_mode='MarkdownV2')
```

**AFTER (Fixed)**:
```python
from utils.messaging import escape_markdown_v2

escaped_name = escape_markdown_v2(first_name)
escaped_details = escape_markdown_v2(bank_details)

message = f"""
🔔 *NEW WITHDRAWAL REQUEST\\!* 🔔

User: [{escaped_name}](tg://user?id={user_id})
Amount: *₦{amount}*
Bank Details:
`{escaped_details}`
"""
await bot.send_message(chat_id, message, parse_mode='MarkdownV2')
```

---

### Example 6: Plain Text Fallback

**BEFORE (No fallback)**:
```python
await bot.send_message(chat_id, complex_message, parse_mode='MarkdownV2')
# If parsing fails, message is not sent and error is raised
```

**AFTER (With safe_send fallback)**:
```python
from utils.messaging import safe_send

await safe_send(
    bot,
    chat_id,
    complex_message,
    parse_mode='MarkdownV2',
    correlation_id='unique_id_123'
)
# If MarkdownV2 fails, tries HTML, then plain text, then document
```

---

## Validation Steps

### Local Testing

1. **Run unit tests**:
   ```bash
   cd /home/runner/work/viralcore/viralcore
   python tests/test_messaging.py
   ```

2. **Check for syntax errors**:
   ```bash
   python -m py_compile handlers/*.py utils/*.py
   ```

3. **Start the bot in development mode**:
   ```bash
   python main_viral_core_bot.py
   ```

4. **Test message templates manually**:
   - Trigger a withdrawal request
   - Submit a link
   - Process a payment
   - Verify no "Bad Request: can't parse entities" errors

### Staging Validation

1. Deploy to staging environment
2. Test these scenarios:
   - User with underscore in username (e.g., `john_doe`)
   - Bank name with special characters (e.g., `First_Bank`)
   - Twitter links with dots and hyphens
   - Large amounts with decimal points
   - Admin approval/rejection messages
   - Affiliate bonus notifications

### Expected Behavior

✅ All messages display correctly with proper formatting  
✅ Bold text appears bold  
✅ Links are clickable  
✅ Code blocks are monospace  
✅ No visible backslashes or escape characters  
✅ No "can't parse entities" errors in logs  

---

## Rollback Plan

### Quick Rollback (Minimal Risk)

If issues appear in production, revert to the previous commit:

```bash
# Find the commit before the formatting changes
git log --oneline -10

# Revert to specific commit
git checkout <previous-commit-sha> -- utils/messaging.py
git checkout <previous-commit-sha> -- utils/notification_service.py
git checkout <previous-commit-sha> -- handlers/admin_withdrawal_handlers.py
git checkout <previous-commit-sha> -- utils/payment_utils.py

# Commit and deploy
git commit -m "Revert: Rollback formatting changes due to production issue"
git push
```

### Full Rollback

```bash
# Revert the entire merge/PR
git revert <merge-commit-sha>
git push
```

### Fallback Mode

The `safe_send` function automatically falls back to plain text if formatting fails:

1. First tries MarkdownV2
2. Falls back to HTML
3. Falls back to plain text
4. Final fallback: sends as document attachment

This ensures messages are always delivered even if formatting is broken.

---

## Code Reviewer Checklist

When reviewing code that sends Telegram messages, verify:

- [ ] All user-supplied values are escaped with `escape_markdown_v2()`
- [ ] Template structure (bold, italic, links) is NOT escaped
- [ ] Static special characters (like `.` and `!`) in templates use `\\.` and `\\!`
- [ ] `format_safe()` or `render_markdown_v2()` is used for templates with variables
- [ ] Error handling includes fallback for parse failures
- [ ] No visible backslashes in the intended output
- [ ] Unicode and emoji are preserved
- [ ] Links are properly formatted: `[text](url)`
- [ ] Code blocks use backticks: ``` `code` ```
- [ ] Sensitive data is not logged in parse error handlers

---

## Common Mistakes to Avoid

### ❌ Double Escaping

```python
# WRONG: Already escaped value gets escaped again
escaped = escape_markdown_v2(escape_markdown_v2(username))
```

### ❌ Escaping Template Structure

```python
# WRONG: Bold markers should not be escaped
message = f"\\*Bold text\\*"  # This will show "*Bold text*" literally
```

### ❌ Forgetting to Escape User Input

```python
# WRONG: User input is inserted directly
message = f"Hello {username}!"  # Breaks if username has underscores
```

### ❌ Using Wrong Parse Mode

```python
# WRONG: Template uses MarkdownV2 escaping but parse_mode is Markdown
message = f"Price: $10\\.50"
await bot.send_message(chat_id, message, parse_mode='Markdown')  # Will show "\."
```

---

## Support

For issues with message formatting:

1. Check the logs for "BadRequest" or "parse" errors
2. Use `safe_send` to get automatic fallback
3. Test the message in isolation with known values
4. Verify the parse_mode matches the template format
