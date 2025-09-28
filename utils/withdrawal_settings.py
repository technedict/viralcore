#!/usr/bin/env python3
# utils/withdrawal_settings.py
# Withdrawal mode settings management

import sqlite3
import logging
from typing import Optional
from enum import Enum

from utils.db_utils import get_connection, DB_FILE

logger = logging.getLogger(__name__)

class WithdrawalMode(Enum):
    MANUAL = "manual"
    AUTOMATIC = "automatic"

def init_withdrawal_settings_table():
    """Initialize withdrawal settings table."""
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS withdrawal_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_by INTEGER
            );
        ''')
        
        # Set default to automatic mode if not exists
        c.execute('''
            INSERT OR IGNORE INTO withdrawal_settings (key, value)
            VALUES ('withdrawal_mode', 'automatic')
        ''')
        
        conn.commit()

def get_withdrawal_mode() -> WithdrawalMode:
    """Get current withdrawal mode from settings."""
    init_withdrawal_settings_table()
    
    with get_connection(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('SELECT value FROM withdrawal_settings WHERE key = ?', ('withdrawal_mode',))
        row = c.fetchone()
        
        if row:
            try:
                return WithdrawalMode(row[0])
            except ValueError:
                logger.warning(f"Invalid withdrawal mode in database: {row[0]}, defaulting to automatic")
                return WithdrawalMode.AUTOMATIC
        else:
            return WithdrawalMode.AUTOMATIC

def set_withdrawal_mode(mode: WithdrawalMode, admin_id: int) -> bool:
    """Set withdrawal mode in settings."""
    try:
        init_withdrawal_settings_table()
        
        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            c.execute('''
                INSERT OR REPLACE INTO withdrawal_settings (key, value, updated_by)
                VALUES ('withdrawal_mode', ?, ?)
            ''', (mode.value, admin_id))
            conn.commit()
            
        logger.info(f"Withdrawal mode set to {mode.value} by admin {admin_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to set withdrawal mode: {e}")
        return False

def get_withdrawal_mode_display() -> str:
    """Get display string for current withdrawal mode."""
    mode = get_withdrawal_mode()
    if mode == WithdrawalMode.MANUAL:
        return "🔧 Manual Mode (Admin approval required)"
    else:
        return "⚡ Automatic Mode (Instant processing)"