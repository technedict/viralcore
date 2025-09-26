# ViralCore Bot

A comprehensive Telegram bot for managing viral content engagement and affiliate rewards.

## Features

- **Atomic Balance Operations**: Secure balance management with race condition protection
- **Admin Pagination**: Scalable admin interfaces with CSV export capabilities  
- **Graceful Shutdown**: Reliable job queue with recovery on restart
- **Structured Error Handling**: Comprehensive API error diagnostics and user-friendly messages
- **Balance Reconciliation**: Tools to detect and fix balance discrepancies

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
pip install python-telegram-bot python-dotenv requests
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

### Balance Operations Tests
```bash
python3 test_balance_operations.py
```

### Export CSV Tests
```bash
python3 scripts/export_users_csv.py --verbose
```

## Running Reconciliation

### Check balance consistency:
```bash
python3 scripts/reconcile_balances.py --verbose
```

### Fix issues (dry run first):
```bash
python3 scripts/reconcile_balances.py --dry-run
python3 scripts/reconcile_balances.py --fix
```

## Backup and Recovery

### Create database backup:
```bash
python3 scripts/migrate_database.py --backup
```

### Restore from backup:
```bash
cp viralcore.db.backup_TIMESTAMP viralcore.db
```

### Export user data:
```bash
python3 scripts/export_users_csv.py -o users_backup.csv
```

## Architecture

### Core Components
- **Balance Operations**: `utils/balance_operations.py` - Atomic balance management
- **Admin Pagination**: `utils/admin_pagination.py` - Scalable admin interfaces
- **Graceful Shutdown**: `utils/graceful_shutdown.py` - Job queue and cleanup
- **API Client**: `utils/api_client.py` - Structured external API calls
- **Database Utils**: `utils/db_utils.py` - Core database operations

### Key Features

#### Atomic Balance Updates
- Race condition protection using SQLite EXCLUSIVE transactions
- Operation ledger for idempotency and audit trails
- Comprehensive validation before balance changes
- Support for both affiliate and reply balances

#### Admin Interface Improvements  
- Pagination for large datasets (20 items per page)
- Automatic CSV export fallback for oversized messages
- User-friendly navigation controls
- Complete data export capabilities

#### Graceful Shutdown System
- Signal handlers for clean shutdown (SIGINT/SIGTERM)
- Persistent job queue with status tracking
- Automatic recovery of interrupted jobs on restart
- Background task cleanup and resource management

#### Enhanced Error Handling
- Structured API client with correlation IDs
- User-friendly error messages for end users
- Detailed diagnostic information for administrators
- Comprehensive logging with trace IDs

## Database Schema

### Core Tables
- `users` - User accounts and affiliate balances
- `purchases` - Transaction records and service purchases
- `balance_operations` - Operation ledger for balance changes
- `reply_balances` - Reply guy balance tracking
- `job_queue` - Background job management

## Configuration

### Environment Variables
- `TELEGRAM_BOT_TOKEN` - Telegram bot API token
- `FLUTTERWAVE_API_KEY` - Payment processor API key
- `ADMIN_EXPORT_AS_ATTACHMENT` - Force CSV export mode (true/false)

## Changelog

### v2.0.0 (Latest)
- ✅ **Security**: Implemented atomic balance operations with race condition protection
- ✅ **Scalability**: Added admin pagination and CSV export for large datasets
- ✅ **Reliability**: Built graceful shutdown system with job recovery
- ✅ **Observability**: Enhanced error handling with structured logging and trace IDs
- ✅ **Maintainability**: Added balance reconciliation tools and comprehensive tests

### Previous Versions
- v1.x.x - Basic bot functionality with engagement tracking

## Support

For issues and support:
1. Check the balance reconciliation tool for data inconsistencies
2. Review logs with trace IDs for API errors  
3. Use the export tools to backup data before major changes
4. Contact the development team with specific error trace IDs

## License

Private - Contact repository owner for licensing information.