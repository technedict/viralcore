#!/bin/bash
################################################################################
# migrate_and_run.sh
# 
# Robust shell script to migrate database files and start the ViralCore bot.
# This script:
# - Loads .env configuration
# - Creates ./db directory if missing
# - Runs database schema migrations
# - Migrates existing .db files to ./db with timestamped backups
# - Starts the Python application
#
# Usage:
#   ./scripts/migrate_and_run.sh [--skip-migrations] [--help]
#
# Options:
#   --skip-migrations  Skip database migrations (for testing)
#   --help            Show this help message
#
# Exit codes:
#   0 - Success
#   1 - Configuration error
#   2 - Migration error
#   3 - Application startup error
################################################################################

set -e  # Exit on error
set -u  # Exit on undefined variable

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${PROJECT_ROOT}/.env"
DB_DIR="${DB_DIR:-${PROJECT_ROOT}/db}"
SKIP_MIGRATIONS=false

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Help message
show_help() {
    head -n 25 "$0" | grep "^#" | sed 's/^# *//' | sed 's/^#//'
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --skip-migrations)
                SKIP_MIGRATIONS=true
                shift
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done
}

# Load environment variables
load_env() {
    log_info "Loading environment configuration..."
    
    if [[ -f "${ENV_FILE}" ]]; then
        # Export all variables from .env file
        set -a
        source "${ENV_FILE}"
        set +a
        log_success "Loaded environment from ${ENV_FILE}"
    else
        log_warning ".env file not found at ${ENV_FILE}"
        log_warning "Using system environment variables only"
    fi
    
    # Update DB_DIR if set in .env
    DB_DIR="${DB_DIR:-${PROJECT_ROOT}/db}"
}

# Create DB directory
create_db_directory() {
    log_info "Ensuring database directory exists..."
    
    if [[ ! -d "${DB_DIR}" ]]; then
        mkdir -p "${DB_DIR}"
        chmod 755 "${DB_DIR}"
        log_success "Created database directory: ${DB_DIR}"
    else
        log_info "Database directory already exists: ${DB_DIR}"
    fi
    
    # Create backups subdirectory
    mkdir -p "${DB_DIR}/backups"
    chmod 755 "${DB_DIR}/backups"
}

# Migrate existing database files
migrate_db_files() {
    log_info "Checking for database files to migrate..."
    
    cd "${PROJECT_ROOT}"
    
    local migrated=false
    local db_files=("viralcore.db" "tweets.db" "tg.db" "groups.db" "custom.db")
    
    for db_file in "${db_files[@]}"; do
        if [[ -f "${db_file}" ]] && [[ ! -f "${DB_DIR}/${db_file}" ]]; then
            local timestamp=$(date +%Y%m%d_%H%M%S)
            local backup_file="${DB_DIR}/backups/${db_file}.backup_${timestamp}"
            
            log_info "Migrating ${db_file} to ${DB_DIR}/"
            
            # Create backup
            cp "${db_file}" "${backup_file}"
            log_success "Backed up to ${backup_file}"
            
            # Move to new location
            mv "${db_file}" "${DB_DIR}/"
            log_success "Migrated ${db_file} to ${DB_DIR}/"
            
            migrated=true
        fi
    done
    
    if [[ "${migrated}" == "true" ]]; then
        log_success "Database files migrated successfully"
    else
        log_info "No database files to migrate (already in ${DB_DIR})"
    fi
}

# Run database migrations
run_migrations() {
    if [[ "${SKIP_MIGRATIONS}" == "true" ]]; then
        log_warning "Skipping database migrations (--skip-migrations flag set)"
        return 0
    fi
    
    log_info "Running database migrations..."
    
    cd "${PROJECT_ROOT}"
    
    # Check if migration script exists
    if [[ ! -f "scripts/migrate_database.py" ]]; then
        log_error "Migration script not found: scripts/migrate_database.py"
        return 2
    fi
    
    # Run migrations with backup
    if python3 scripts/migrate_database.py --backup --apply; then
        log_success "Database migrations completed successfully"
        return 0
    else
        log_error "Database migrations failed"
        return 2
    fi
}

# Start the application
start_application() {
    log_info "Starting ViralCore application..."
    
    cd "${PROJECT_ROOT}"
    
    # Determine the correct command to start the app
    if [[ -n "${GUNICORN_CMD:-}" ]]; then
        # Use gunicorn if specified in env
        log_info "Starting with gunicorn: ${GUNICORN_CMD}"
        exec ${GUNICORN_CMD}
    elif [[ -f "main_viral_core_bot.py" ]]; then
        # Default: start main bot
        log_info "Starting main_viral_core_bot.py"
        exec python3 main_viral_core_bot.py
    else
        log_error "No application entry point found"
        log_error "Set GUNICORN_CMD in .env or ensure main_viral_core_bot.py exists"
        return 3
    fi
}

# Main execution
main() {
    log_info "ViralCore Migration and Startup Script"
    log_info "========================================"
    
    # Parse arguments
    parse_args "$@"
    
    # Step 1: Load environment
    load_env || {
        log_error "Failed to load environment"
        exit 1
    }
    
    # Step 2: Create DB directory
    create_db_directory || {
        log_error "Failed to create database directory"
        exit 1
    }
    
    # Step 3: Migrate existing DB files
    migrate_db_files || {
        log_error "Failed to migrate database files"
        exit 2
    }
    
    # Step 4: Run migrations
    run_migrations || {
        log_error "Failed to run database migrations"
        exit 2
    }
    
    # Step 5: Start application
    start_application || {
        log_error "Failed to start application"
        exit 3
    }
}

# Run main function
main "$@"
