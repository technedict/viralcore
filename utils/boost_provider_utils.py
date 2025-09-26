import json
import os
import logging # Import the logging module
from typing import Dict
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Configure logging for this module
logger = logging.getLogger(__name__)
# Ensure logger is not duplicated if this file is imported multiple times
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO) # Set default logging level to INFO, adjust as needed

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "settings", "provider_config.json")
CONFIG_PATH = os.path.abspath(CONFIG_PATH)
DEFAULT_PROVIDER = "smmstone"

class ProviderConfig:
    def __init__(self, name: str, api_url: str, api_key: str, view_service_id: int, like_service_id: int):
        self.name = name
        self.api_url = api_url
        self.api_key = api_key
        self.view_service_id = view_service_id
        self.like_service_id = like_service_id

    @staticmethod
    def get_active_provider_name() -> str:
        """
        Reads the active provider name from the configuration file.
        If the file doesn't exist or an error occurs, it sets the default provider
        and returns its name.
        """
        try:
            if not os.path.exists(CONFIG_PATH):
                logger.info(f"[ProviderConfig] Config file not found at {CONFIG_PATH}. Setting default provider to {DEFAULT_PROVIDER}.")
                ProviderConfig.set_active_provider_name(DEFAULT_PROVIDER)
                return DEFAULT_PROVIDER

            with open(CONFIG_PATH, "r") as f:
                data = json.load(f)
                active_provider = data.get("active_provider", DEFAULT_PROVIDER)
                logger.debug(f"[ProviderConfig] Read active provider: {active_provider}")
                return active_provider
        except json.JSONDecodeError:
            logger.error(f"[ProviderConfig] Error decoding JSON from config file: {CONFIG_PATH}. Setting default provider.", exc_info=True)
            ProviderConfig.set_active_provider_name(DEFAULT_PROVIDER)
            return DEFAULT_PROVIDER
        except FileNotFoundError:
            logger.error(f"[ProviderConfig] Config file not found during read (unexpected): {CONFIG_PATH}. Setting default provider.", exc_info=True)
            ProviderConfig.set_active_provider_name(DEFAULT_PROVIDER)
            return DEFAULT_PROVIDER
        except Exception as e:
            logger.error(f"[ProviderConfig] Unexpected error reading config file: {e}. Setting default provider.", exc_info=True)
            ProviderConfig.set_active_provider_name(DEFAULT_PROVIDER)
            return DEFAULT_PROVIDER

    @staticmethod
    def set_active_provider_name(provider_name: str) -> bool:
        """
        Writes the active provider name to the configuration file.
        """
        try:
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            with open(CONFIG_PATH, "w") as f:
                json.dump({"active_provider": provider_name}, f, indent=2)
            logger.info(f"[ProviderConfig] Active provider set to: {provider_name} in {CONFIG_PATH}")
            return True
        except IOError as e:
            logger.error(f"[ProviderConfig] IO error writing config file: {e}. Path: {CONFIG_PATH}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"[ProviderConfig] Unexpected error writing config: {e}. Path: {CONFIG_PATH}", exc_info=True)
            return False


PROVIDERS: Dict[str, ProviderConfig] = {
    "smmflare": ProviderConfig(
        name="smmflare",
        api_url="https://smmflare.com/api/v2",
        api_key=os.getenv("SMMFLARE_API_KEY", "MISSING_KEY"),
        view_service_id=8381, # ID: 8381 which is NGN 76 per 1000 views ID: 6361 which is $0.12 per 1000 views or ID: 6631 which is NGN 46 per 1000 views
        like_service_id=8646
    ),
    "plugsmms": ProviderConfig(
        name="plugsmms",
        api_url="https://panel.plugsmmservice.com/api/v2",
        api_key=os.getenv("PLUGSMMS_API_KEY", "MISSING_KEY"),
        view_service_id=7750, 
        like_service_id=11023
    ),
    "smmstone": ProviderConfig(
        name="smmstone",
        api_url="https://smmstone.com/api/v2",
        api_key=os.getenv("SMMSTONE_API_KEY", "MISSING_KEY"),
        view_service_id=5480,
        like_service_id=6662
    ),
}

def get_active_provider() -> ProviderConfig:
    """
    Retrieves the ProviderConfig object for the currently active provider.
    Falls back to the default provider if the active one is not found.
    """
    name = ProviderConfig.get_active_provider_name()
    provider = PROVIDERS.get(name)
    if provider is None:
        logger.warning(f"[ProviderConfig] Provider '{name}' not found in PROVIDERS dictionary. Falling back to default: {DEFAULT_PROVIDER}.")
        provider = PROVIDERS[DEFAULT_PROVIDER]
    logger.debug(f"[ProviderConfig] Returning active provider: {provider.name}")
    return provider


if __name__ == "__main__":
    # Example usage for testing purposes
    logger.info("--- boost_provider_utils.py Test Run ---")
    active_provider = get_active_provider()
    logger.info(f"Active Provider: {active_provider.name}")
    logger.info(f"API URL: {active_provider.api_url}")
    logger.info(f"API Key: {active_provider.api_key[:5]}... (first 5 chars)") # Mask API key for display
    logger.info(f"View Service ID: {active_provider.view_service_id}")
    logger.info(f"Like Service ID: {active_provider.like_service_id}")

    # Test setting a new provider
    test_provider_name = "plugsmms"
    logger.info(f"\nAttempting to set active provider to: {test_provider_name}")
    if ProviderConfig.set_active_provider_name(test_provider_name):
        logger.info("Successfully set provider.")
        new_active_provider = get_active_provider()
        logger.info(f"New Active Provider: {new_active_provider.name}")
        logger.info(f"New View Service ID: {new_active_provider.view_service_id}")
    else:
        logger.error("Failed to set provider.")

    # Reset to default for clean state if run repeatedly
    logger.info(f"\nResetting active provider to default: {DEFAULT_PROVIDER}")
    ProviderConfig.set_active_provider_name(DEFAULT_PROVIDER)
    logger.info("--- Test Run Finished ---")