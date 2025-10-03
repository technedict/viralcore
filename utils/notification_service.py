#!/usr/bin/env python3
# utils/notification_service.py
# Abstraction layer for multi-channel notifications (Email, Slack, Telegram, etc.)

import logging
import os
import json
from typing import Optional, Dict, Any, List
from enum import Enum
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


class NotificationChannel(Enum):
    """Supported notification channels."""
    TELEGRAM = "telegram"
    EMAIL = "email"
    SLACK = "slack"


@dataclass
class NotificationMessage:
    """Structured notification message."""
    title: str
    body: str
    correlation_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    priority: str = "normal"  # low, normal, high, critical
    action_url: Optional[str] = None


class NotificationService:
    """
    Multi-channel notification service for admin alerts.
    
    Supports:
    - Telegram groups
    - Email (SMTP)
    - Slack webhooks
    
    Configuration via environment variables:
    - ADMIN_GROUP_ENDPOINT: Comma-separated list of Telegram group IDs
    - ADMIN_CONTACTS: Comma-separated list of admin email addresses
    - SLACK_WEBHOOK_URL: Slack webhook URL for notifications
    - DISABLE_NOTIFICATIONS: Set to 'true' to disable all notifications (for testing)
    """
    
    def __init__(self):
        self.telegram_enabled = False
        self.email_enabled = False
        self.slack_enabled = False
        
        # Load configuration
        self._load_config()
        
    def _load_config(self):
        """Load notification configuration from environment."""
        # Telegram configuration
        self.telegram_group_ids = self._parse_csv_env("ADMIN_GROUP_ENDPOINT")
        if self.telegram_group_ids:
            self.telegram_enabled = True
            logger.info(f"Telegram notifications enabled for {len(self.telegram_group_ids)} groups")
        
        # Email configuration
        self.admin_emails = self._parse_csv_env("ADMIN_CONTACTS")
        self.smtp_host = os.getenv("SMTP_HOST")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER")
        self.smtp_password = os.getenv("SMTP_PASSWORD")
        self.email_from = os.getenv("EMAIL_FROM", self.smtp_user)
        
        if self.admin_emails and self.smtp_host and self.smtp_user:
            self.email_enabled = True
            logger.info(f"Email notifications enabled for {len(self.admin_emails)} recipients")
        
        # Slack configuration
        self.slack_webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        if self.slack_webhook_url:
            self.slack_enabled = True
            logger.info("Slack notifications enabled")
        
        # Global disable flag
        if os.getenv("DISABLE_NOTIFICATIONS", "").lower() == "true":
            self.telegram_enabled = False
            self.email_enabled = False
            self.slack_enabled = False
            logger.warning("All notifications disabled via DISABLE_NOTIFICATIONS")
    
    def _parse_csv_env(self, key: str) -> List[str]:
        """Parse comma-separated environment variable."""
        value = os.getenv(key, "")
        if not value:
            return []
        return [item.strip() for item in value.split(",") if item.strip()]
    
    async def send_notification(
        self,
        message: NotificationMessage,
        channels: Optional[List[NotificationChannel]] = None
    ) -> Dict[str, bool]:
        """
        Send notification to specified channels.
        
        Args:
            message: NotificationMessage to send
            channels: List of channels to use (default: all enabled channels)
        
        Returns:
            Dict mapping channel name to success status
        """
        if channels is None:
            # Use all enabled channels
            channels = []
            if self.telegram_enabled:
                channels.append(NotificationChannel.TELEGRAM)
            if self.email_enabled:
                channels.append(NotificationChannel.EMAIL)
            if self.slack_enabled:
                channels.append(NotificationChannel.SLACK)
        
        results = {}
        
        for channel in channels:
            try:
                if channel == NotificationChannel.TELEGRAM:
                    success = await self._send_telegram(message)
                    results["telegram"] = success
                elif channel == NotificationChannel.EMAIL:
                    success = await self._send_email(message)
                    results["email"] = success
                elif channel == NotificationChannel.SLACK:
                    success = await self._send_slack(message)
                    results["slack"] = success
            except Exception as e:
                logger.error(f"Failed to send notification via {channel.value}: {e}", exc_info=True)
                results[channel.value] = False
        
        return results
    
    async def _send_telegram(self, message: NotificationMessage) -> bool:
        """Send notification via Telegram."""
        if not self.telegram_enabled:
            return False
        
        try:
            from telegram import Bot
            from utils.config import APIConfig
            
            bot = Bot(token=APIConfig.TELEGRAM_BOT_TOKEN)
            
            # Format message
            text = self._format_telegram_message(message)
            
            # Send to all configured groups
            success_count = 0
            for group_id in self.telegram_group_ids:
                try:
                    await bot.send_message(
                        chat_id=int(group_id),
                        text=text,
                        parse_mode="MarkdownV2"
                    )
                    success_count += 1
                except Exception as e:
                    logger.error(f"Failed to send Telegram notification to {group_id}: {e}")
            
            return success_count > 0
            
        except Exception as e:
            logger.error(f"Telegram notification failed: {e}", exc_info=True)
            return False
    
    async def _send_email(self, message: NotificationMessage) -> bool:
        """Send notification via email."""
        if not self.email_enabled:
            return False
        
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = message.title
            msg['From'] = self.email_from
            msg['To'] = ", ".join(self.admin_emails)
            
            # Format message body
            html_body = self._format_email_message(message)
            msg.attach(MIMEText(html_body, 'html'))
            
            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            
            logger.info(f"Email notification sent to {len(self.admin_emails)} recipients")
            return True
            
        except Exception as e:
            logger.error(f"Email notification failed: {e}", exc_info=True)
            return False
    
    async def _send_slack(self, message: NotificationMessage) -> bool:
        """Send notification via Slack webhook."""
        if not self.slack_enabled:
            return False
        
        try:
            import aiohttp
            
            # Format Slack message
            payload = self._format_slack_message(message)
            
            async with aiohttp.ClientSession() as session:
                async with session.post(self.slack_webhook_url, json=payload) as response:
                    if response.status == 200:
                        logger.info("Slack notification sent successfully")
                        return True
                    else:
                        logger.error(f"Slack notification failed with status {response.status}")
                        return False
                        
        except Exception as e:
            logger.error(f"Slack notification failed: {e}", exc_info=True)
            return False
    
    def _format_telegram_message(self, message: NotificationMessage) -> str:
        """Format message for Telegram with MarkdownV2 escaping."""
        def escape_md(text: str) -> str:
            """Escape special characters for MarkdownV2."""
            special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
            for char in special_chars:
                text = text.replace(char, f'\\{char}')
            return text
        
        lines = [
            f"*{escape_md(message.title)}*",
            "",
            escape_md(message.body)
        ]
        
        if message.correlation_id:
            lines.append("")
            lines.append(f"📋 Correlation ID: `{escape_md(message.correlation_id)}`")
        
        if message.action_url:
            lines.append("")
            lines.append(f"🔗 [View Details]({escape_md(message.action_url)})")
        
        if message.metadata:
            lines.append("")
            lines.append("*Details:*")
            for key, value in message.metadata.items():
                lines.append(f"  • {escape_md(key)}: {escape_md(str(value))}")
        
        return "\n".join(lines)
    
    def _format_email_message(self, message: NotificationMessage) -> str:
        """Format message for email (HTML)."""
        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                .header {{ background-color: #f8f9fa; padding: 20px; border-left: 4px solid #007bff; }}
                .body {{ padding: 20px; }}
                .metadata {{ background-color: #f8f9fa; padding: 10px; margin-top: 20px; }}
                .footer {{ color: #6c757d; font-size: 12px; margin-top: 20px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>{message.title}</h2>
            </div>
            <div class="body">
                <p>{message.body.replace(chr(10), '<br>')}</p>
                
                {f'<p><strong>Correlation ID:</strong> {message.correlation_id}</p>' if message.correlation_id else ''}
                
                {f'<p><a href="{message.action_url}">View Details</a></p>' if message.action_url else ''}
                
                {self._format_metadata_html(message.metadata) if message.metadata else ''}
            </div>
            <div class="footer">
                <p>This is an automated notification from ViralCore Bot</p>
            </div>
        </body>
        </html>
        """
        return html
    
    def _format_metadata_html(self, metadata: Dict[str, Any]) -> str:
        """Format metadata as HTML table."""
        rows = []
        for key, value in metadata.items():
            rows.append(f"<tr><td><strong>{key}:</strong></td><td>{value}</td></tr>")
        
        return f"""
        <div class="metadata">
            <table>
                {' '.join(rows)}
            </table>
        </div>
        """
    
    def _format_slack_message(self, message: NotificationMessage) -> Dict[str, Any]:
        """Format message for Slack."""
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": message.title
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": message.body
                }
            }
        ]
        
        if message.metadata:
            fields = []
            for key, value in message.metadata.items():
                fields.append({
                    "type": "mrkdwn",
                    "text": f"*{key}:*\n{value}"
                })
            
            blocks.append({
                "type": "section",
                "fields": fields
            })
        
        if message.correlation_id:
            blocks.append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Correlation ID: `{message.correlation_id}`"
                    }
                ]
            })
        
        if message.action_url:
            blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "View Details"
                        },
                        "url": message.action_url
                    }
                ]
            })
        
        return {"blocks": blocks}


# Global notification service instance
_notification_service = None


def get_notification_service() -> NotificationService:
    """Get or create the global notification service instance."""
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service
