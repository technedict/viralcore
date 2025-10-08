#!/usr/bin/env python3
"""
Tests for duplicate link submission feature.
"""

import pytest
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.db_utils import get_connection, TWEETS_DB_FILE, TG_DB_FILE, init_tweet_db, init_tg_db


class TestDuplicateLinkSubmission:
    """Test that users can submit the same link multiple times."""
    
    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        """Setup and teardown for each test."""
        # Initialize databases
        init_tweet_db()
        init_tg_db()
        
        # Clear tweets table before each test
        with get_connection(TWEETS_DB_FILE) as conn:
            c = conn.cursor()
            c.execute("DELETE FROM tweets")
            conn.commit()
        
        # Clear telegram_posts table
        with get_connection(TG_DB_FILE) as conn:
            c = conn.cursor()
            c.execute("DELETE FROM telegram_posts")
            conn.commit()
        
        yield
        
        # Cleanup after test
        with get_connection(TWEETS_DB_FILE) as conn:
            c = conn.cursor()
            c.execute("DELETE FROM tweets")
            conn.commit()
        
        with get_connection(TG_DB_FILE) as conn:
            c = conn.cursor()
            c.execute("DELETE FROM telegram_posts")
            conn.commit()
    
    def test_duplicate_tweet_submission_allowed(self):
        """Test that the same tweet can be submitted multiple times."""
        tweet_id = "1234567890"
        twitter_link = "https://twitter.com/user/status/1234567890"
        
        # Insert first submission
        with get_connection(TWEETS_DB_FILE) as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO tweets
                (tweet_id, twitter_link, target_likes, target_retweets, target_comments, target_views, click_count)
                VALUES (?, ?, ?, ?, ?, ?, 0)
            """, (tweet_id, twitter_link, 100, 50, 25, 5000))
            conn.commit()
        
        # Insert second submission with same tweet_id (should succeed)
        with get_connection(TWEETS_DB_FILE) as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO tweets
                (tweet_id, twitter_link, target_likes, target_retweets, target_comments, target_views, click_count)
                VALUES (?, ?, ?, ?, ?, ?, 0)
            """, (tweet_id, twitter_link, 150, 75, 35, 7500))
            conn.commit()
        
        # Verify both submissions exist
        with get_connection(TWEETS_DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM tweets WHERE tweet_id = ?", (tweet_id,))
            count = c.fetchone()[0]
            assert count == 2, "Should allow duplicate tweet submissions"
    
    def test_duplicate_tg_submission_allowed(self):
        """Test that the same Telegram link can be submitted multiple times."""
        tg_link = "https://t.me/channel/123"
        
        # Insert first submission
        with get_connection(TG_DB_FILE) as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO telegram_posts
                (tg_link, target_comments, target_reactions)
                VALUES (?, ?, ?)
            """, (tg_link, 50, 50))
            conn.commit()
        
        # Insert second submission with same link (should succeed)
        with get_connection(TG_DB_FILE) as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO telegram_posts
                (tg_link, target_comments, target_reactions)
                VALUES (?, ?, ?)
            """, (tg_link, 75, 75))
            conn.commit()
        
        # Verify both submissions exist
        with get_connection(TG_DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM telegram_posts WHERE tg_link = ?", (tg_link,))
            count = c.fetchone()[0]
            assert count == 2, "Should allow duplicate Telegram link submissions"
    
    def test_multiple_duplicate_submissions(self):
        """Test that links can be submitted more than twice."""
        tweet_id = "9876543210"
        twitter_link = "https://twitter.com/user/status/9876543210"
        
        # Insert 5 submissions
        for i in range(5):
            with get_connection(TWEETS_DB_FILE) as conn:
                c = conn.cursor()
                c.execute("""
                    INSERT INTO tweets
                    (tweet_id, twitter_link, target_likes, target_retweets, target_comments, target_views, click_count)
                    VALUES (?, ?, ?, ?, ?, ?, 0)
                """, (tweet_id, twitter_link, 100 + i*10, 50, 25, 5000))
                conn.commit()
        
        # Verify all 5 submissions exist
        with get_connection(TWEETS_DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM tweets WHERE tweet_id = ?", (tweet_id,))
            count = c.fetchone()[0]
            assert count == 5, "Should allow multiple duplicate submissions"
    
    def test_different_links_still_separate(self):
        """Test that different links are still tracked separately."""
        tweet_id_1 = "1111111111"
        tweet_id_2 = "2222222222"
        twitter_link_1 = "https://twitter.com/user/status/1111111111"
        twitter_link_2 = "https://twitter.com/user/status/2222222222"
        
        # Insert submissions for different tweets
        with get_connection(TWEETS_DB_FILE) as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO tweets
                (tweet_id, twitter_link, target_likes, target_retweets, target_comments, target_views, click_count)
                VALUES (?, ?, ?, ?, ?, ?, 0)
            """, (tweet_id_1, twitter_link_1, 100, 50, 25, 5000))
            
            c.execute("""
                INSERT INTO tweets
                (tweet_id, twitter_link, target_likes, target_retweets, target_comments, target_views, click_count)
                VALUES (?, ?, ?, ?, ?, ?, 0)
            """, (tweet_id_2, twitter_link_2, 150, 75, 35, 7500))
            conn.commit()
        
        # Verify separate tracking
        with get_connection(TWEETS_DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM tweets WHERE tweet_id = ?", (tweet_id_1,))
            count1 = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM tweets WHERE tweet_id = ?", (tweet_id_2,))
            count2 = c.fetchone()[0]
            
            assert count1 == 1, "First tweet should have 1 submission"
            assert count2 == 1, "Second tweet should have 1 submission"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
