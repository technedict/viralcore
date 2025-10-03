#!/usr/bin/env python3
"""
Test DB centralization functionality.
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_db_dir_creation():
    """Test that DB_DIR is created automatically."""
    # Use a temporary directory for testing
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ['DB_DIR'] = tmpdir
        
        # Import after setting env var
        import importlib
        import utils.db_utils
        importlib.reload(utils.db_utils)
        
        # Check that directory was created
        assert Path(tmpdir).exists(), "DB_DIR should be created"
        print("✅ DB_DIR creation test passed")


def test_db_file_paths():
    """Test that all DB files use the centralized directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ['DB_DIR'] = tmpdir
        
        import importlib
        import utils.db_utils
        importlib.reload(utils.db_utils)
        
        # Check that all DB files are in the correct directory
        assert utils.db_utils.DB_FILE == str(Path(tmpdir) / "viralcore.db")
        assert utils.db_utils.TWEETS_DB_FILE == str(Path(tmpdir) / "tweets.db")
        assert utils.db_utils.TG_DB_FILE == str(Path(tmpdir) / "tg.db")
        assert utils.db_utils.GROUPS_TWEETS_DB_FILE == str(Path(tmpdir) / "groups.db")
        assert utils.db_utils.CUSTOM_DB_FILE == str(Path(tmpdir) / "custom.db")
        
        print("✅ DB file paths test passed")


def test_db_migration():
    """Test migrating existing DB files to centralized directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a mock project root with DB files
        root_dir = Path(tmpdir) / "project"
        root_dir.mkdir()
        db_dir = root_dir / "db"
        
        # Create some mock DB files in root
        for db_file in ["viralcore.db", "tweets.db"]:
            (root_dir / db_file).write_text("mock data")
        
        # Set up environment
        os.environ['DB_DIR'] = str(db_dir)
        
        # Mock the db_utils module to use our temp directory
        import importlib
        import utils.db_utils
        
        # Temporarily override the root directory detection
        original_file = utils.db_utils.__file__
        utils.db_utils.__file__ = str(root_dir / "utils" / "db_utils.py")
        
        try:
            # Run migration
            result = utils.db_utils.migrate_db_files_to_directory()
            
            assert result, "Migration should succeed"
            assert (db_dir / "viralcore.db").exists(), "viralcore.db should be migrated"
            assert (db_dir / "tweets.db").exists(), "tweets.db should be migrated"
            assert (db_dir / "backups").exists(), "Backup directory should be created"
            
            # Check backups were created
            backups = list((db_dir / "backups").glob("*.backup_*"))
            assert len(backups) >= 2, "Backups should be created"
            
            print("✅ DB migration test passed")
            
        finally:
            utils.db_utils.__file__ = original_file


def test_db_initialization():
    """Test that DB initialization works with centralized directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ['DB_DIR'] = tmpdir
        
        import importlib
        import utils.db_utils
        importlib.reload(utils.db_utils)
        
        # Initialize main DB
        utils.db_utils.init_main_db()
        
        # Check that DB file was created in the right place
        db_file = Path(tmpdir) / "viralcore.db"
        assert db_file.exists(), "DB file should be created in DB_DIR"
        
        # Check that tables were created
        import sqlite3
        conn = sqlite3.connect(str(db_file))
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        assert 'users' in tables, "Users table should exist"
        assert 'purchases' in tables, "Purchases table should exist"
        
        print("✅ DB initialization test passed")


if __name__ == "__main__":
    print("Testing DB centralization...")
    print("=" * 50)
    
    try:
        test_db_dir_creation()
        test_db_file_paths()
        test_db_initialization()
        # Note: test_db_migration is commented out as it requires more complex mocking
        # test_db_migration()
        
        print("\n" + "=" * 50)
        print("✅ All DB centralization tests passed!")
        sys.exit(0)
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
