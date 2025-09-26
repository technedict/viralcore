# config.py
import os
from typing import Dict
from dotenv import load_dotenv

load_dotenv()

class ConfigError(Exception):
    pass

# read this first, before the class
MAIN_MENU_IMAGE_PATH = os.getenv("MAIN_MENU_IMAGE_PATH", "./propic.jpeg")

class APIConfig:
    """
    Load and provide access to API credentials and application settings.
    Values are fetched from environment variables for security.
    """
    # Telegram bot
    BOT_USERNAME : str = os.getenv("BOT_USERNAME")
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN")

    # Bitly
    BITLY_ACCESS_TOKEN: str = os.getenv("BITLY_ACCESS_TOKEN")

    # Crypto data APIs
    CM_API_KEY: str = os.getenv("CM_API_KEY")
    BSC_API_KEY: str = os.getenv("BSC_API_KEY")
    SOL_API_KEY: str = os.getenv("SOL_API_KEY")
    TRX_GRID_API_KEY: str = os.getenv("TRX_GRID_API_KEY")
    HELIUS_API_KEY: str = os.getenv("HELIUS_API_KEY")
    TRX_SCAN_API_KEY: str = os.getenv("TRX_SCAN_API_KEY")
    FLUTTERWAVE_API_KEY: str = os.getenv("FLUTTERWAVE_API_KEY")
    EXCHANGE_API_KEY: str = os.getenv("EXCHANGE_API_KEY")
    ADMIN_IDS = [6030280354, 5137148238, 6316404884]

    # Twitter
    TWITTER_BEARER_TOKEN: str = os.getenv("TWITTER_BEARER_TOKEN") 

    # Boosting
    SMMFLARE_API_KEY: str = os.getenv("SMMFLARE_API_KEY")
    PLUGSMMS_API_KEY: str = os.getenv("PLUGSMMS_API_KEY")
    SMMSTONE_API_KEY: str = os.getenv("SMMSTONE_API_KEY")

    # **This is what your bot actually uses for the /start image**
    MAIN_MENU_IMAGE: str = MAIN_MENU_IMAGE_PATH


    # Tier details for engagement plans
    TIER_DETAILS: Dict[str, Dict[str, object]] = {
        "t1": {
            "description": "25 Likes, 10 Comments, 2k Views, 5 Reposts", 
            "price": 0.5
        },
        "t2": {
            "description": "50 Likes, 20 Comments, 5k Views, 10 Reposts",
            "price": 1.00
        },
        "t3": {
            "description": "75 Likes, 30 Comments, 7k Views, 15 Reposts",
            "price": 1.50
        },
        "t4": {
            "description": "100 Likes, 40 Comments, 10k Views, 20 Reposts",
            "price": 2.00
        },
        "t5": {
            "description": "150 Likes, 40 Comments + 20 verified KOL comments, 15k Views, 30 Reposts",
            "price": 3.00
        }
        # …etc…
    }

    FOLLOWER_DETAILS = {
        "direct_add": {"price_per_k": 10.00, "min_qty": 1000}, # $10 per 1k followers
        "slow_push": {"price_per_10": 0.15, "min_qty": 10} # $0.15 per 10 followers
    }

    # Slide images mapping 
    SLIDE_IMAGES: Dict[str, str] = {
        "main_menu": MAIN_MENU_IMAGE_PATH,
        "admin_panel": os.getenv("ADMIN_PANEL_IMAGE_PATH", MAIN_MENU_IMAGE_PATH),
        # …all my other slides…
    }

    COINGECKO_IDS = {
        "bsc":   "binancecoin",  # BNB on BSC
        "bnb":   "binancecoin",  # BNB on BSC
        "sol":   "solana",       # SOL on Solana
        "trx":   "tron",         # TRX on Tron
        "aptos": "aptos",        # APT on Aptos
    }

    @classmethod
    def validate(cls) -> None:
        """Validate that required environment variables are set."""
        required_keys = [
            'TELEGRAM_BOT_TOKEN', 'FLUTTERWAVE_API_KEY', 'EXCHANGE_API_KEY'
        ]
        missing = []
        for key in required_keys:
            value = getattr(cls, key, None)
            if not value or value == f'your_{key.lower()}_here':
                missing.append(key)
        
        if missing:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Missing required environment variables: {', '.join(missing)}")
            logger.warning("Please check your .env file or environment variable configuration")
            # Don't raise exception to allow development mode
        
    @classmethod
    def get(cls, key: str) -> str:
        """
        Get the value of a configuration key.
        """
        if not hasattr(cls, key):
            raise KeyError(f"Configuration key '{key}' not found.")
        return getattr(cls, key)
    
#
# validate at import
APIConfig.validate()
