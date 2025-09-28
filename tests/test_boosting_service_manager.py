#!/usr/bin/env python3
# tests/test_self.service_manager.py
# Tests for boosting service provider management

import unittest
import sqlite3
import os
import tempfile
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set up test database path before imports
TEST_DB = tempfile.mktemp(suffix='.db')

# Mock the DB_FILE constant
import utils.db_utils
utils.db_utils.DB_FILE = TEST_DB

from utils.boosting_service_manager import (
    BoostingService,
    ServiceProviderMapping,
    ServiceType,
    BoostingServiceManager
)
from utils.db_utils import get_connection


class TestBoostingServiceManager(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        """Set up test database with required tables."""
        cls.db_file = TEST_DB
        
        # Create service manager instance
        cls.service_manager = BoostingServiceManager()
        
        with get_connection(cls.db_file) as conn:
            c = conn.cursor()
            
            # Create users table
            c.execute('''
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY,
                    username TEXT,
                    is_admin INTEGER DEFAULT 0
                )
            ''')
            
            # Create boosting services table
            c.execute('''
                CREATE TABLE boosting_services (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    service_type TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                    CHECK (service_type IN ('likes', 'views', 'comments')),
                    CHECK (is_active IN (0, 1))
                )
            ''')
            
            # Create boosting service providers mapping table
            c.execute('''
                CREATE TABLE boosting_service_providers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    service_id INTEGER NOT NULL,
                    provider_name TEXT NOT NULL,
                    provider_service_id INTEGER NOT NULL,
                    created_by INTEGER DEFAULT NULL,
                    updated_by INTEGER DEFAULT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (service_id) REFERENCES boosting_services (id),
                    FOREIGN KEY (created_by) REFERENCES users (id),
                    FOREIGN KEY (updated_by) REFERENCES users (id),
                    UNIQUE(service_id, provider_name)
                )
            ''')
            
            # Create audit log for service provider changes
            c.execute('''
                CREATE TABLE boosting_service_audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    service_provider_id INTEGER NOT NULL,
                    admin_id INTEGER DEFAULT NULL,
                    action TEXT NOT NULL,
                    old_provider_service_id INTEGER DEFAULT NULL,
                    new_provider_service_id INTEGER DEFAULT NULL,
                    reason TEXT DEFAULT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (service_provider_id) REFERENCES boosting_service_providers (id),
                    FOREIGN KEY (admin_id) REFERENCES users (id)
                )
            ''')
            
            # Insert test users
            c.execute('INSERT INTO users (id, username, is_admin) VALUES (1, "admin", 1)')
            
            conn.commit()
    
    @classmethod
    def tearDownClass(cls):
        """Clean up test database."""
        if os.path.exists(cls.db_file):
            os.unlink(cls.db_file)
    
    def setUp(self):
        """Reset database state for each test."""
        with get_connection(self.db_file) as conn:
            c = conn.cursor()
            c.execute('DELETE FROM boosting_services')
            c.execute('DELETE FROM boosting_service_providers')
            c.execute('DELETE FROM boosting_service_audit_log')
            conn.commit()
    
    def test_create_service_and_add_providers(self):
        """Test creating a boosting service and adding provider mappings."""
        # Create a likes service
        service_id = self.service_manager.create_service_if_not_exists(
            "Test Likes Service", ServiceType.LIKES
        )
        
        self.assertIsNotNone(service_id)
        
        # Add provider mappings
        success1 = self.service_manager.add_provider_mapping(
            service_id=service_id,
            provider_name="smmflare",
            provider_service_id=8646,
            created_by=1
        )
        
        success2 = self.service_manager.add_provider_mapping(
            service_id=service_id,
            provider_name="plugsmms",
            provider_service_id=11023,
            created_by=1
        )
        
        self.assertTrue(success1)
        self.assertTrue(success2)
        
        # Get mappings
        mappings = self.service_manager.get_service_provider_mappings(service_id)
        self.assertEqual(len(mappings), 2)
        
        provider_names = [m.provider_name for m in mappings]
        self.assertIn("smmflare", provider_names)
        self.assertIn("plugsmms", provider_names)
    
    def test_get_active_service(self):
        """Test getting active service by type."""
        # Create and activate a service
        service_id = self.service_manager.create_service_if_not_exists(
            "Active Likes Service", ServiceType.LIKES
        )
        
        # Get active service
        active_service = self.service_manager.get_active_service(ServiceType.LIKES)
        
        self.assertIsNotNone(active_service)
        self.assertEqual(active_service.id, service_id)
        self.assertEqual(active_service.service_type, ServiceType.LIKES)
        self.assertTrue(active_service.is_active)
    
    def test_get_provider_service_id(self):
        """Test getting provider service ID for active service."""
        # Create service and add provider mapping
        service_id = self.service_manager.create_service_if_not_exists(
            "Test Views Service", ServiceType.VIEWS
        )
        
        self.service_manager.add_provider_mapping(
            service_id=service_id,
            provider_name="smmstone",
            provider_service_id=5480,
            created_by=1
        )
        
        # Get provider service ID
        provider_service_id = self.service_manager.get_provider_service_id(
            ServiceType.VIEWS, "smmstone"
        )
        
        self.assertEqual(provider_service_id, 5480)
        
        # Test non-existent provider
        provider_service_id = self.service_manager.get_provider_service_id(
            ServiceType.VIEWS, "nonexistent"
        )
        
        self.assertIsNone(provider_service_id)
    
    def test_update_provider_service_mapping(self):
        """Test updating provider service mapping with audit logging."""
        # Create service and add provider mapping
        service_id = self.service_manager.create_service_if_not_exists(
            "Test Likes Service", ServiceType.LIKES
        )
        
        self.service_manager.add_provider_mapping(
            service_id=service_id,
            provider_name="smmflare",
            provider_service_id=8646,
            created_by=1
        )
        
        # Update the mapping
        success = self.service_manager.update_provider_service_mapping(
            service_id=service_id,
            provider_name="smmflare",
            new_provider_service_id=9999,
            admin_id=1,
            reason="Testing update"
        )
        
        self.assertTrue(success)
        
        # Verify the update
        new_service_id = self.service_manager.get_provider_service_id(
            ServiceType.LIKES, "smmflare"
        )
        
        self.assertEqual(new_service_id, 9999)
        
        # Check audit log
        audit_entries = self.service_manager.get_audit_log(limit=1)
        self.assertEqual(len(audit_entries), 1)
        
        entry = audit_entries[0]
        self.assertEqual(entry['action'], 'updated')
        self.assertEqual(entry['old_provider_service_id'], 8646)
        self.assertEqual(entry['new_provider_service_id'], 9999)
        self.assertEqual(entry['reason'], 'Testing update')
    
    def test_validate_provider_service_id(self):
        """Test provider service ID validation."""
        # Valid IDs
        self.assertTrue(self.service_manager.validate_provider_service_id("smmflare", 8646))
        self.assertTrue(self.service_manager.validate_provider_service_id("plugsmms", 11023))
        self.assertTrue(self.service_manager.validate_provider_service_id("unknown_provider", 5000))
        
        # Invalid IDs
        self.assertFalse(self.service_manager.validate_provider_service_id("smmflare", 0))
        self.assertFalse(self.service_manager.validate_provider_service_id("smmflare", -100))
        self.assertFalse(self.service_manager.validate_provider_service_id("smmflare", 999))  # Too low
        self.assertFalse(self.service_manager.validate_provider_service_id("unknown_provider", 0))
        self.assertFalse(self.service_manager.validate_provider_service_id("unknown_provider", 9999999))  # Too high
    
    def test_get_current_provider_mappings_summary(self):
        """Test getting summary of current provider mappings."""
        # Create services and add mappings
        likes_service_id = self.service_manager.create_service_if_not_exists(
            "Likes Service", ServiceType.LIKES
        )
        
        views_service_id = self.service_manager.create_service_if_not_exists(
            "Views Service", ServiceType.VIEWS
        )
        
        # Add provider mappings
        self.service_manager.add_provider_mapping(
            service_id=likes_service_id,
            provider_name="smmflare",
            provider_service_id=8646
        )
        
        self.service_manager.add_provider_mapping(
            service_id=likes_service_id,
            provider_name="plugsmms",
            provider_service_id=11023
        )
        
        self.service_manager.add_provider_mapping(
            service_id=views_service_id,
            provider_name="smmflare",
            provider_service_id=8381
        )
        
        # Get summary
        summary = self.service_manager.get_current_provider_mappings_summary()
        
        self.assertIn("likes", summary)
        self.assertIn("views", summary)
        
        # Check likes mappings
        likes_mappings = summary["likes"]
        self.assertEqual(likes_mappings["smmflare"], 8646)
        self.assertEqual(likes_mappings["plugsmms"], 11023)
        
        # Check views mappings
        views_mappings = summary["views"]
        self.assertEqual(views_mappings["smmflare"], 8381)
    
    def test_duplicate_service_creation(self):
        """Test that creating duplicate services returns existing ID."""
        # Create service twice
        service_id1 = self.service_manager.create_service_if_not_exists(
            "Duplicate Service", ServiceType.LIKES
        )
        
        service_id2 = self.service_manager.create_service_if_not_exists(
            "Duplicate Service", ServiceType.LIKES
        )
        
        # Should return the same ID
        self.assertEqual(service_id1, service_id2)
        
        # Should only have one service in database
        with get_connection(self.db_file) as conn:
            c = conn.cursor()
            c.execute('SELECT COUNT(*) FROM boosting_services WHERE name = ?', ("Duplicate Service",))
            count = c.fetchone()[0]
            self.assertEqual(count, 1)
    
    def test_duplicate_provider_mapping(self):
        """Test that duplicate provider mappings are handled correctly."""
        service_id = self.service_manager.create_service_if_not_exists(
            "Test Service", ServiceType.LIKES
        )
        
        # Add mapping
        success1 = self.service_manager.add_provider_mapping(
            service_id=service_id,
            provider_name="smmflare",
            provider_service_id=8646
        )
        
        # Try to add same mapping again
        success2 = self.service_manager.add_provider_mapping(
            service_id=service_id,
            provider_name="smmflare",
            provider_service_id=9999  # Different service ID
        )
        
        self.assertTrue(success1)
        self.assertFalse(success2)  # Should fail due to unique constraint
        
        # Original mapping should remain unchanged
        provider_service_id = self.service_manager.get_provider_service_id(
            ServiceType.LIKES, "smmflare"
        )
        self.assertEqual(provider_service_id, 8646)


if __name__ == '__main__':
    # Clean up any existing test database
    if os.path.exists(TEST_DB):
        os.unlink(TEST_DB)
    
    unittest.main()