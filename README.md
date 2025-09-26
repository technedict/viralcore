# ViralCore Bot

A comprehensive Telegram bot for managing viral content engagement and affiliate rewards with enhanced security, reliability, and provider safety.

## New Features (v2.1.0)

### 🔒 Enhanced Provider Security & Service ID Leak Prevention
- **Immutable Job Snapshots**: Provider configurations captured at job creation prevent service_id leaks during provider switches
- **Concurrency-Safe Operations**: Database locking (SELECT...FOR UPDATE) prevents race conditions 
- **Provider Validation**: Defensive validation ensures service_id belongs to correct provider
- **Idempotency**: Duplicate boost requests are handled safely with idempotency keys

### 🛡️ Safe External Provider Error Handling  
- **Circuit Breaker**: Automatic protection against failing providers with exponential backoff
- **Error Classification**: TRANSIENT vs PERMANENT error mapping with appropriate retry strategies
- **Safe Client Responses**: External provider errors never leak to clients - only safe, standardized responses
- **Structured Logging**: Full provider responses logged for debugging while keeping clients safe

### 📝 Enhanced Logging & Observability
- **Structured JSON Logging**: Correlation IDs, secret sanitization, and proper log levels
- **Intelligent Log Routing**: WARNING/ERROR → bot.log, INFO/DEBUG → debug.log/console  
- **Rotating Log Files**: 10MB max size, 5 backup files, automatic cleanup
- **Secret Sanitization**: API keys, tokens, and sensitive data automatically redacted

### 🎯 Fixed MarkdownV2 Message Formatting
- **Smart Escaping**: Only user variables escaped, not entire templates  
- **Fallback Parsing**: MarkdownV2 → HTML → Plain Text → Document on parse errors
- **Template Validation**: Built-in validation and error recovery
- **Centralized Messaging**: Consistent message formatting across the bot

## Features

- **Atomic Balance Operations**: Secure balance management with race condition protection
- **Admin Pagination**: Scalable admin interfaces with CSV export capabilities  
- **Graceful Shutdown**: Reliable job queue with recovery on restart
- **Structured Error Handling**: Comprehensive API error diagnostics and user-friendly messages
- **Balance Reconciliation**: Tools to detect and fix balance discrepancies
- **Provider Safety**: External service errors never exposed to users

## Quick Start

### Prerequisites
- Python 3.8+
- SQLite3
- Telegram Bot Token
- Flutterwave API Key

### Installation

1. Clone the repository:
```bash
git clone https://github.com/technedict/viralcore.git
cd viralcore
```

2. Install dependencies:
```bash
pip install python-telegram-bot python-dotenv requests aiohttp
```

3. Configure environment variables:
```bash
cp .env.example .env
# Edit .env with your API keys
```

4. Run database migrations:
```bash
python3 scripts/migrate_database.py --backup --apply
```

5. Start the bot:
```bash
python3 main_viral_core_bot.py
```

## Running Tests

### Job System Tests
```bash
python3 tests/test_job_system.py
```

### Balance Operations Tests
```bash
python3 test_balance_operations.py
```

### Export CSV Tests
```bash
python3 scripts/export_users_csv.py --verbose
```

## Running Reconciliation & Safety Scripts

### Check for service ID mismatches:
```bash
python3 scripts/check_serviceid_mismatches.py --verbose --output mismatches.csv
```

### Normalize over-escaped templates:  
```bash
python3 scripts/normalize_templates.py --report template_issues.html
```

### Review job snapshot pattern:
```bash
python3 scripts/snapshot_and_dispatch_example.py
```

### Check balance consistency:
```bash
python3 scripts/reconcile_balances.py --verbose
```

### Fix issues (dry run first):
```bash
python3 scripts/reconcile_balances.py --dry-run
python3 scripts/reconcile_balances.py --fix
```

## Logging Configuration

The enhanced logging system provides better observability:

### Log Files
- `bot.log` - WARNING and ERROR messages only (structured JSON)
- `debug.log` - INFO and DEBUG messages (structured JSON)  
- Console - INFO level messages (human-readable format)

### Switching Logging Targets
```python
from utils.logging import setup_logging

# Custom logging configuration
setup_logging(
    bot_log_level=logging.ERROR,      # Only errors to bot.log
    console_log_level=logging.DEBUG,  # More verbose console
    use_structured_format=False       # Use simple format
)
```

### Log Rotation Settings
- Maximum file size: 10MB
- Backup files kept: 5
- Automatic cleanup of old logs
- Secret sanitization enabled by default

## Architecture

### Core Components
- **Job System**: `utils/job_system.py` - Immutable provider snapshots and concurrency control
- **Enhanced Boost Service**: `utils/boost_utils_enhanced.py` - Safe provider error handling
- **Messaging System**: `utils/messaging.py` - Safe MarkdownV2 handling and templates
- **Enhanced Logging**: `utils/logging.py` - Structured logging with correlation IDs
- **Balance Operations**: `utils/balance_operations.py` - Atomic balance management
- **Admin Pagination**: `utils/admin_pagination.py` - Scalable admin interfaces
- **Graceful Shutdown**: `utils/graceful_shutdown.py` - Job queue and cleanup
- **API Client**: `utils/api_client.py` - Structured external API calls
- **Database Utils**: `utils/db_utils.py` - Core database operations

### Key Security Features

#### Provider Service ID Leak Prevention
- Immutable snapshots capture provider_id, service_id at job creation
- Workers use job snapshots, never current active provider
- Concurrency control prevents race conditions during provider switches
- Defensive validation rejects mismatched provider/service combinations

#### Safe External Error Handling  
- Circuit breaker protects against failing providers
- Provider errors classified and mapped to safe client responses
- Exponential backoff with jitter for transient errors
- Full diagnostic logging while keeping clients protected

#### Enhanced Security Measures
- Structured logging with automatic secret sanitization
- Input validation and parameterized database queries
- Correlation IDs for request tracing without data exposure
- Safe message templates with variable-only escaping

## Configuration

### Environment Variables
- `TELEGRAM_BOT_TOKEN` - Telegram bot API token
- `FLUTTERWAVE_API_KEY` - Payment processor API key
- `ADMIN_EXPORT_AS_ATTACHMENT` - Force CSV export mode (true/false)
- `SMMFLARE_API_KEY` - SMMFlare provider API key
- `PLUGSMMS_API_KEY` - PlugSMMS provider API key  
- `SMMSTONE_API_KEY` - SMMStone provider API key

### Provider Configuration
Provider settings stored in `settings/provider_config.json`:
```json
{
  "active_provider": "smmstone"
}
```

### Message Templates
Common templates in `utils/messaging.py`:
- `balance_alert` - Low balance notifications
- `boost_success` - Successful boost confirmation
- `boost_failed` - Safe boost failure message
- `provider_switched` - Provider change confirmation

## Database Schema

### Core Tables
- `users` - User accounts and affiliate balances
- `purchases` - Transaction records and service purchases
- `balance_operations` - Operation ledger for balance changes
- `reply_balances` - Reply guy balance tracking
- `job_queue` - Background job management
- `jobs` - New job system with provider snapshots

### New Job System Schema
```sql
CREATE TABLE jobs (
    job_id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    provider_snapshot TEXT NOT NULL,  -- JSON snapshot
    payload TEXT NOT NULL,           -- JSON payload  
    idempotency_key TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    error_message TEXT,
    correlation_id TEXT
);
```

## Monitoring & Observability

### Logging with Correlation IDs
```python
from utils.logging import correlation_context, get_logger

logger = get_logger(__name__)

with correlation_context() as correlation_id:
    logger.info("Processing request", extra={'user_id': 123})
    # All logs in this context get the same correlation_id
```

### Safe Provider Error Logging
```python  
from utils.logging import log_provider_error

log_provider_error(
    logger, 
    provider_name="smmflare",
    error_response=raw_response,
    correlation_id=correlation_id,
    job_id=job_id,
    user_id=user_id
)
```

### Message Template Usage
```python
from utils.messaging import render_markdown_v2, safe_send, TEMPLATES

# Safe template rendering
message = render_markdown_v2(
    TEMPLATES['boost_success'],
    provider_name=provider.name,
    link=boost_link,
    quantity=100
)

# Safe sending with fallbacks
await safe_send(
    bot,
    chat_id=chat_id,
    text=message,
    correlation_id=correlation_id
)
```

## Changelog

### v2.1.0 (Latest) - Security & Reliability Update
- ✅ **Provider Security**: Fixed service_id leak vulnerability with immutable job snapshots
- ✅ **Safe Error Handling**: External provider errors never exposed to clients
- ✅ **Enhanced Logging**: Structured JSON logging with correlation IDs and secret sanitization  
- ✅ **MarkdownV2 Fixes**: Proper escaping of user variables only, not entire templates
- ✅ **Reconciliation Tools**: Scripts to detect and fix service_id mismatches and template issues
- ✅ **Circuit Breaker**: Automatic protection against failing external providers
- ✅ **Comprehensive Testing**: Unit tests for core functionality and concurrency scenarios

### v2.0.0 (Previous)
- ✅ **Security**: Implemented atomic balance operations with race condition protection
- ✅ **Scalability**: Added admin pagination and CSV export for large datasets
- ✅ **Reliability**: Built graceful shutdown system with job recovery
- ✅ **Observability**: Enhanced error handling with structured logging and trace IDs
- ✅ **Maintainability**: Added balance reconciliation tools and comprehensive tests

### Previous Versions
- v1.x.x - Basic bot functionality with engagement tracking

## Deployment Checklist

### Pre-deployment
1. Run reconciliation scripts to check for existing issues
2. Backup database: `python3 scripts/migrate_database.py --backup`
3. Test in staging environment
4. Review and update provider API keys

### Post-deployment  
1. Monitor bot.log for WARNING/ERROR messages
2. Verify debug.log contains INFO/DEBUG messages
3. Run service_id mismatch check: `python3 scripts/check_serviceid_mismatches.py`
4. Monitor provider error rates and circuit breaker status
5. Verify message templates render correctly without parse errors

### Rollback Plan
1. Stop bot service
2. Restore database backup: `cp viralcore.db.backup_TIMESTAMP viralcore.db`
3. Revert to previous code version
4. Restart bot with previous configuration

## Support

For issues and support:
1. Check reconciliation tools for data inconsistencies
2. Review structured logs with correlation IDs for API errors  
3. Use export tools to backup data before major changes
4. Run template normalization for MarkdownV2 issues
5. Contact development team with specific error correlation IDs

## License

Private - Contact repository owner for licensing information.