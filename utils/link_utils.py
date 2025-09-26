#!/usr/bin/env python3
# utils/bitly_utils.py

import os
import re
import logging
from typing import Optional

import requests

# Configure module‐level logger
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

# Bitly API configuration
BITLY_BASE_URL = "https://api-ssl.bitly.com/v4"
BITLY_ACCESS_TOKEN = os.getenv("BITLY_ACCESS_TOKEN")

# Regex for extracting tweet IDs
_TWEET_ID_PATTERN = re.compile(r"status/(?P<tweet_id>\d+)")

class BitlyClient:
    """
    A simple Bitly API client for creating, disabling, and tracking links.
    """
    def __init__(self, access_token: Optional[str] = None):
        token = access_token or BITLY_ACCESS_TOKEN
        if not token:
            raise ValueError("Bitly access token must be provided via BITLY_ACCESS_TOKEN")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        })

    def shorten(self, long_url: str, domain: str = "bit.ly") -> Optional[str]:
        payload = {"long_url": long_url, "domain": domain}
        try:
            resp = self.session.post(f"{BITLY_BASE_URL}/shorten", json=payload)
            resp.raise_for_status()
            link = resp.json().get("link")
            logger.debug("Shortened %s → %s", long_url, link)
            return link
        except requests.RequestException as e:
            logger.error("Bitly shorten error: %s", e)
            return None

    def get_click_count(self, bitly_link: str) -> Optional[int]:
        bitlink = re.sub(r"^https?://", "", bitly_link).split("/")[0]
        try:
            url = f"{BITLY_BASE_URL}/bitlinks/{bitlink}/clicks/summary"
            resp = self.session.get(url)
            resp.raise_for_status()
            count = resp.json().get("total_clicks")
            logger.debug("Click count for %s: %s", bitlink, count)
            return count
        except requests.RequestException as e:
            logger.error("Bitly click count error: %s", e)
            return None

    def disable(self, bitly_link: str) -> bool:
        bitlink = re.sub(r"^https?://", "", bitly_link).split("/")[0]
        try:
            url = f"{BITLY_BASE_URL}/bitlinks/{bitlink}"
            resp = self.session.patch(url, json={"archived": True})
            resp.raise_for_status()
            logger.debug("Disabled link %s", bitlink)
            return True
        except requests.RequestException as e:
            logger.error("Bitly disable error: %s", e)
            return False

# instantiate a single client for module‐level functions
_client = BitlyClient()


def create_shortened_link(long_url: str) -> Optional[str]:
    """
    Create a shortened Bitly link.
    """
    return _client.shorten(long_url)


def get_click_count(bitly_link: str) -> Optional[int]:
    """
    Retrieve the total clicks for a Bitly link.
    """
    return _client.get_click_count(bitly_link)


def disable_bitly_link(bitly_link: str) -> bool:
    """
    Archive (disable) a Bitly link.
    """
    return _client.disable(bitly_link)


def extract_tweet_id(link: str) -> Optional[str]:
    """
    Extract the Tweet ID from a Twitter/X status URL.
    """
    m = _TWEET_ID_PATTERN.search(link)
    return m.group("tweet_id") if m else None

def is_tg_link(link):
    if not isinstance(link, str):
        raise TypeError("Input must be a string.")
    
    telegram_patterns = [
        r"^https?:\/\/(www\.)?(t\.me|telegram\.me|telegram\.dog)\/",
        r"^tg:\/\/(resolve\?domain=|join\?invite=)?[a-zA-Z0-9_-]+",
        r"^tg:" # Catch-all for other tg: deep links
    ]

    for pattern in telegram_patterns:
        if re.match(pattern, link, re.IGNORECASE):
            return True
            
    return False
