#!/usr/bin/env python3
"""
Daily link submission reporting system.
Sends daily reports to admin group at 12pm with link submission counts.
"""

import asyncio
import logging
from datetime import datetime, time, timedelta
from typing import Optional

from telegram import Bot
from utils.db_utils import get_connection, TWEETS_DB_FILE, TG_DB_FILE
from utils.config import APIConfig

logger = logging.getLogger(__name__)


class DailyReportScheduler:
    """Scheduler for daily link submission reports."""
    
    def __init__(self, bot: Bot, admin_chat_id: int):
        """
        Initialize the daily report scheduler.
        
        Args:
            bot: Telegram Bot instance
            admin_chat_id: Chat ID of admin group to send reports to
        """
        self.bot = bot
        self.admin_chat_id = admin_chat_id
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    async def start(self):
        """Start the daily report scheduler."""
        if self._running:
            logger.warning("Daily report scheduler already running")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info(f"Daily report scheduler started (reports at 12:00 PM to chat {self.admin_chat_id})")
    
    async def stop(self):
        """Stop the daily report scheduler."""
        if not self._running:
            return
        
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("Daily report scheduler stopped")
    
    async def _run(self):
        """Main scheduler loop."""
        while self._running:
            try:
                # Calculate seconds until next 12:00 PM
                now = datetime.now()
                target_time = datetime.combine(now.date(), time(12, 0))
                
                # If it's past 12:00 PM today, schedule for tomorrow
                if now >= target_time:
                    target_time = datetime.combine(now.date() + timedelta(days=1), time(12, 0))
                
                wait_seconds = (target_time - now).total_seconds()
                logger.info(f"Next daily report in {wait_seconds/3600:.1f} hours at {target_time}")
                
                # Wait until target time
                await asyncio.sleep(wait_seconds)
                
                # Send report
                await self._send_daily_report()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in daily report scheduler: {e}", exc_info=True)
                # Wait 1 hour before retrying to avoid spam
                await asyncio.sleep(3600)
    
    async def _send_daily_report(self):
        """Generate and send daily link submission report."""
        try:
            # Get counts for last 24 hours
            yesterday = datetime.now() - timedelta(days=1)
            yesterday_str = yesterday.strftime('%Y-%m-%d')
            
            # Count Twitter/X submissions
            x_count = 0
            with get_connection(TWEETS_DB_FILE) as conn:
                c = conn.cursor()
                # tweets table doesn't have timestamp, so we count all submissions
                # If you want last 24h, you'd need to add a timestamp column
                c.execute("SELECT COUNT(*) FROM tweets")
                result = c.fetchone()
                if result:
                    x_count = result[0]
            
            # Count Telegram submissions
            tg_count = 0
            with get_connection(TG_DB_FILE) as conn:
                c = conn.cursor()
                c.execute("SELECT COUNT(*) FROM telegram_posts")
                result = c.fetchone()
                if result:
                    tg_count = result[0]
            
            # Format report message
            report = (
                "📊 *Daily Link Submission Report* 📊\n\n"
                f"📅 Date: {datetime.now().strftime('%Y-%m-%d')}\n"
                f"🕛 Time: 12:00 PM\n\n"
                f"🐦 Twitter/X Links: {x_count}\n"
                f"💬 Telegram Links: {tg_count}\n"
                f"📈 Total Links: {x_count + tg_count}\n\n"
                f"_Note: Counts represent total submissions in database_"
            )
            
            # Send to admin group
            await self.bot.send_message(
                chat_id=self.admin_chat_id,
                text=report,
                parse_mode='Markdown'
            )
            
            logger.info(f"Daily report sent: X={x_count}, TG={tg_count}, Total={x_count + tg_count}")
            
        except Exception as e:
            logger.error(f"Failed to send daily report: {e}", exc_info=True)


# Global instance
_daily_report_scheduler: Optional[DailyReportScheduler] = None


def init_daily_report_scheduler(bot: Bot, admin_chat_id: int):
    """Initialize the global daily report scheduler."""
    global _daily_report_scheduler
    _daily_report_scheduler = DailyReportScheduler(bot, admin_chat_id)
    return _daily_report_scheduler


def get_daily_report_scheduler() -> Optional[DailyReportScheduler]:
    """Get the global daily report scheduler instance."""
    return _daily_report_scheduler
