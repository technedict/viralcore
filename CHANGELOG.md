# Changelog

All notable changes to ViralCore Bot will be documented in this file.

## [2.1.1] - 2025-09-26 - Security Audit & Refactor

### 🔒 **CRITICAL SECURITY FIXES**

#### **Secrets Management**
- **BREAKING**: Removed all hardcoded API keys from `.env` file (moved to `.env.backup`)
- Created secure `.env.example` template for safe configuration
- Added `.env` to `.gitignore` to prevent future secret exposure
- Enhanced `SecretSanitizer` with service-specific patterns (Telegram, JWT, Flutterwave)
- Removed partial API key logging from boost provider utilities

#### **Enhanced Secret Detection**
- Added patterns for Telegram bot tokens (`\d{10}:\w{35}`)
- Added patterns for Flutterwave keys (`FLWSECK-[a-zA-Z0-9\-]+`)
- Added patterns for JWT tokens (`eyJ[a-zA-Z0-9_\-\.]{100,}`)
- Enhanced generic secret detection with improved regex patterns

### 🛡️ **Security Hardening** 

#### **Concurrency & Race Conditions**
- Fixed idempotency mechanism in balance operations to prevent duplicate transactions
- Enhanced database locking with proper `BEGIN EXCLUSIVE` usage
- Improved error handling in concurrent operations
- Added double-check pattern for operation completion inside transactions

#### **SQL Injection Prevention**
- ✅ **VERIFIED SECURE**: All database operations use parameterized queries
- No string concatenation or format injection patterns found
- Added comprehensive audit documentation

### 📨 **Message Template Security**

#### **MarkdownV2 Fixes**
- **Fixed over-escaping bug**: Only escape official MarkdownV2 special characters
- Corrected specification compliance: `$` and `@` are NOT escaped per Telegram spec
- Enhanced template rendering to only escape variable values, not template structure
- Added comprehensive fallback chain: MarkdownV2 → HTML → Plain Text → Document

#### **Safe Message Sending**
- Improved `safe_send()` with better error handling and correlation IDs  
- Enhanced template validation with proper variable requirement checking
- Fixed markdown stripping for fallback scenarios
- Added optional telegram import support for testing environments

### ⚡ **Performance Optimizations**

#### **Database Indexing**
- Added indexes on `users(username, affiliate_balance)`
- Added indexes on `purchases(user_id, plan_type, timestamp, transaction_ref)`
- Added indexes on `processed_transactions(transaction_hash, user_id, processed_at)`
- Improved query performance for common operations

### 🔧 **Development & Testing**

#### **Dependency Management**
- Created `requirements.txt` with pinned versions for security
- Added security scanning tools (bandit, safety, pip-audit)
- Enhanced development setup documentation

#### **Testing Enhancements**
- Fixed messaging system tests with 100% pass rate
- Enhanced balance operation tests with concurrency validation
- Added comprehensive template escaping test coverage

### 🔍 **Audit Tools & Scripts**

- Created `secrets-scan.csv` with comprehensive secret detection
- Created `dependency-scan.csv` with vulnerability assessment  
- Created `sql-injection-scan.csv` with query safety verification
- Added `performance_audit.py` for ongoing performance monitoring
- Created `template_migration.py` for fixing over-escaped templates

### 📋 **Security Assessment Results**

- **SQL Injection**: ✅ SECURE (Parameterized queries throughout)
- **Command Injection**: ✅ SECURE (No shell=True, eval(), exec() usage)
- **Secret Exposure**: ✅ FIXED (All hardcoded secrets removed)
- **Race Conditions**: ✅ SECURE (Atomic operations with proper locking)
- **Template Vulnerabilities**: ✅ FIXED (Proper escaping, safe fallbacks)
- **Dependency Security**: ✅ IMPROVED (Version pinning added)

### ⚠️ **Breaking Changes**

1. **Environment Configuration**: `.env` file is no longer tracked in git
   - **Action Required**: Copy `.env.backup` to `.env` in production
   - **Security**: Rotate all exposed API keys immediately

### 🔧 **Migration Guide**

1. **For Production Deployment**:
   ```bash
   # Copy secrets (DO NOT COMMIT .env)
   cp .env.backup .env
   
   # Rotate all API keys for security
   # Update environment variables in deployment system
   
   # Verify configuration
   python -c "from utils.config import APIConfig; APIConfig.validate()"
   ```

2. **For Development**:
   ```bash
   # Copy example configuration
   cp .env.example .env
   
   # Fill in your development API keys
   # Never commit .env file
   ```

---

## [2.0.0] - 2024-09-26

### Added
- **Atomic Balance Operations**: Implemented race condition protection for all balance updates
  - SQLite EXCLUSIVE transactions for atomic operations
  - Operation ledger table for idempotency and audit trails
  - Comprehensive validation before balance changes
  - Support for both affiliate and reply balance types

- **Admin Interface Improvements**: Scalable admin interfaces for large datasets
  - Pagination system (20 items per page) for user and payment lists
  - Automatic CSV export fallback when messages exceed Telegram limits
  - Navigation controls (Previous/Next) for paginated views
  - Complete data export capabilities with all database fields

- **Graceful Shutdown System**: Reliable job management and recovery
  - Signal handlers for clean shutdown on SIGINT/SIGTERM
  - Persistent job queue with status tracking (queued, in_progress, completed, failed)
  - Automatic recovery of stale/interrupted jobs on startup
  - Background task cleanup and resource management
  - Integration with boost manager for coordinated shutdown

- **Enhanced Error Handling**: Structured API diagnostics and user-friendly messages
  - Comprehensive API client with correlation IDs and structured logging
  - User-friendly error messages that don't expose technical details
  - Detailed diagnostic information for administrators with trace IDs
  - Retry logic with exponential backoff for external API calls

- **Balance Reconciliation Tools**: Data integrity and audit capabilities
  - Automated balance consistency checking across all users
  - Detection of negative balances, suspicious amounts, and data mismatches
  - CSV export of reconciliation findings with severity levels
  - Automated fixes for common issues (with dry-run support)

- **Comprehensive Testing**: Validation of core functionality
  - Concurrency tests for balance operations to prevent race conditions
  - Idempotency tests to ensure operations can be safely retried
  - Balance operation validation tests with edge cases
  - Export functionality tests with real data scenarios

### Changed
- **Database Schema**: Added new tables for enhanced functionality
  - `balance_operations` table for operation ledger and audit trails
  - `reply_balances` table for reply guy balance tracking
  - `job_queue` table for background job management
  - Enhanced error handling in all database operations

- **Payment Processing**: Improved Flutterwave integration
  - Structured API client with comprehensive error handling
  - Better error messages for users when payments fail
  - Trace ID support for debugging payment issues
  - Fallback mechanisms for API connectivity issues

- **Admin Functions**: Enhanced user experience for administrators
  - Replaced single giant messages with paginated views
  - Added export functionality for all admin data views
  - Improved error handling in admin operations
  - Better feedback for admin actions with success/failure indicators

### Fixed
- **Race Conditions**: Eliminated balance swap bugs in concurrent withdrawals
  - Atomic updates prevent partial state changes
  - Proper locking mechanisms using SQLite EXCLUSIVE transactions
  - Validation ensures correct balance types are used for operations

- **Message Length Issues**: Resolved Telegram message size limits
  - Automatic detection of oversized messages
  - Seamless fallback to CSV export when messages are too long
  - Chunked message sending for medium-sized content

- **Service Interruption**: Improved reliability during shutdowns
  - Graceful handling of SIGINT/SIGTERM signals
  - Persistence of in-progress work to prevent data loss
  - Recovery mechanisms for interrupted operations

### Security
- **Input Sanitization**: Enhanced protection against injection attacks
  - Sanitization of sensitive data in logs (API keys, account numbers)
  - Parameterized database queries to prevent SQL injection
  - Validation of user inputs before processing

- **Error Information**: Controlled exposure of system details
  - User-friendly error messages without internal system details
  - Detailed diagnostics available only to administrators
  - Trace IDs for correlation without exposing sensitive data

### Technical Improvements
- **Code Organization**: Better structure and maintainability
  - Separated concerns with dedicated modules for major features
  - Consistent error handling patterns across all components
  - Comprehensive logging with structured format and correlation IDs

- **Performance**: Optimized database operations and API calls
  - Reduced database lock contention with shorter transactions
  - Efficient pagination queries with proper indexing
  - Connection pooling and retry strategies for external APIs

- **Monitoring**: Enhanced observability and debugging capabilities
  - Structured logging with JSON format for log aggregation
  - Correlation IDs for tracing requests across system components
  - Comprehensive metrics for balance operations and API calls

## [1.x.x] - Previous Versions

### Legacy Features
- Basic Telegram bot functionality
- Simple balance management
- Basic admin commands
- Flutterwave payment integration
- User engagement tracking

---

## Migration Guide

### From v1.x.x to v2.0.0

1. **Backup your database**:
   ```bash
   python3 scripts/migrate_database.py --backup
   ```

2. **Run database migrations**:
   ```bash
   python3 scripts/migrate_database.py --apply
   ```

3. **Run balance reconciliation**:
   ```bash
   python3 scripts/reconcile_balances.py --verbose
   ```

4. **Test the upgraded system**:
   ```bash
   python3 test_balance_operations.py
   ```

5. **Verify admin functions**:
   - Test user and payment list pagination
   - Verify CSV export functionality
   - Check error handling in admin operations

### Breaking Changes
- None - all changes are backward compatible
- New tables are created automatically during migration
- Existing functionality continues to work unchanged

### New Configuration Options
- `ADMIN_EXPORT_AS_ATTACHMENT=true` - Force CSV export mode for admin views
- Signal handlers are automatically registered (no configuration needed)
- Job queue settings are configured via database (no environment variables needed)

---

For technical support or questions about this release, please check the balance reconciliation tool first, then contact the development team with specific trace IDs from error logs.