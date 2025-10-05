# Withdrawal Notification Message Templates

This document describes the message templates used for user notifications in the withdrawal system.

## Templates Location

Templates are defined in `utils/notification_service.py` in the `USER_NOTIFICATION_TEMPLATES` dictionary.

## Available Templates

### 1. Withdrawal Approved

**Template ID:** `withdrawal_approved`

**Title:** ✅ Withdrawal Approved

**Variables:**
- `{amount_usd}` - Amount in USD
- `{amount_ngn}` - Amount in NGN
- `{bank_name}` - Beneficiary bank name
- `{account_number}` - Masked account number (last 4 digits)
- `{withdrawal_id}` - Unique withdrawal request ID
- `{mode_specific_info}` - Mode-specific processing information
- `{expected_time}` - Expected processing time

**Message Body:**
```
Your withdrawal request has been approved!

💵 Amount: ${amount_usd} USD (₦{amount_ngn} NGN)
🏦 Bank: {bank_name}
💳 Account: {account_number}
📝 Request ID: {withdrawal_id}

{mode_specific_info}

Expected processing time: {expected_time}
Status: Approved

You will be notified once the transfer is completed.
```

**Example (Automatic Mode):**
```
Your withdrawal request has been approved!

💵 Amount: $50.00 USD (₦75000 NGN)
🏦 Bank: GTBank
💳 Account: ****5678
📝 Request ID: 123

⚡ Automatic transfer initiated - payment will be processed shortly

Expected processing time: 2-24 hours
Status: Approved

You will be notified once the transfer is completed.
```

**Example (Manual Mode):**
```
Your withdrawal request has been approved!

💵 Amount: $50.00 USD (₦75000 NGN)
🏦 Bank: GTBank
💳 Account: ****5678
📝 Request ID: 123

📋 Manual processing - admin will process your payment

Expected processing time: 1-3 business days
Status: Approved

You will be notified once the transfer is completed.
```

### 2. Withdrawal Rejected

**Template ID:** `withdrawal_rejected`

**Title:** ❌ Withdrawal Rejected

**Variables:**
- `{amount_usd}` - Amount in USD
- `{amount_ngn}` - Amount in NGN
- `{bank_name}` - Beneficiary bank name
- `{account_number}` - Masked account number
- `{withdrawal_id}` - Unique withdrawal request ID
- `{reason}` - Rejection reason provided by admin

**Message Body:**
```
Your withdrawal request has been rejected.

💵 Amount: ${amount_usd} USD (₦{amount_ngn} NGN)
🏦 Bank: {bank_name}
💳 Account: {account_number}
📝 Request ID: {withdrawal_id}

Reason: {reason}

Next Steps:
- Please verify your bank details are correct
- Ensure you have sufficient balance
- Contact support if you need assistance

You can submit a new withdrawal request anytime.
```

**Example:**
```
Your withdrawal request has been rejected.

💵 Amount: $50.00 USD (₦75000 NGN)
🏦 Bank: GTBank
💳 Account: ****5678
📝 Request ID: 123

Reason: Rejected by admin John

Next Steps:
- Please verify your bank details are correct
- Ensure you have sufficient balance
- Contact support if you need assistance

You can submit a new withdrawal request anytime.
```

### 3. Withdrawal Completed

**Template ID:** `withdrawal_completed`

**Title:** 🎉 Withdrawal Completed

**Variables:**
- `{amount_usd}` - Amount in USD
- `{amount_ngn}` - Amount in NGN
- `{bank_name}` - Beneficiary bank name
- `{account_number}` - Masked account number
- `{withdrawal_id}` - Unique withdrawal request ID
- `{reference}` - Flutterwave transaction reference

**Message Body:**
```
Your withdrawal has been completed successfully!

💵 Amount: ${amount_usd} USD (₦{amount_ngn} NGN)
🏦 Bank: {bank_name}
💳 Account: {account_number}
📝 Request ID: {withdrawal_id}
🔖 Reference: {reference}

The funds should arrive in your account within 24-48 hours.

Thank you for using our service!
```

**Example:**
```
Your withdrawal has been completed successfully!

💵 Amount: $50.00 USD (₦75000 NGN)
🏦 Bank: GTBank
💳 Account: ****5678
📝 Request ID: 123
🔖 Reference: VCW_123_a1b2c3d4

The funds should arrive in your account within 24-48 hours.

Thank you for using our service!
```

## Security Considerations

1. **Account Number Masking**: Account numbers are always masked to show only the last 4 digits (e.g., `****5678`)
2. **No Sensitive Data**: Templates never include full account numbers, API keys, or other sensitive information
3. **Correlation IDs**: All notifications include correlation IDs for tracking but these are safe identifiers

## Localization

Currently, templates are in English. To add localization:

1. Create locale-specific template dictionaries in `notification_service.py`
2. Add user language preference to database
3. Select template based on user's preferred language
4. Example structure:
   ```python
   USER_NOTIFICATION_TEMPLATES = {
       "en": { ... },  # English templates
       "fr": { ... },  # French templates
       "es": { ... }   # Spanish templates
   }
   ```

## Customization

To customize templates:

1. Edit the template strings in `utils/notification_service.py`
2. Ensure all variables in curly braces `{variable}` match the function parameters
3. Test notifications after changes using the runbook procedures

## Notification Channels

Currently, notifications are sent via:
- **Telegram**: Direct message to user's Telegram account

Future channels could include:
- **Email**: If user email is available
- **SMS**: If user phone number is available
- **In-app**: Push notifications if mobile app exists

## Audit Trail

All notification deliveries are recorded in the `user_notifications` table:
- User ID
- Withdrawal ID
- Notification type
- Channel used
- Delivery status (sent/failed)
- Timestamp
- Error message (if failed)

This ensures:
- **Idempotency**: Same notification won't be sent twice
- **Audit compliance**: Full record of all user communications
- **Debugging**: Easy to trace notification delivery issues
