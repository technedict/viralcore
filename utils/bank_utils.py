import os
import requests
import json
from datetime import datetime, timedelta
from fuzzywuzzy import fuzz

# Determine cache path relative to this script's parent directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.abspath(os.path.join(BASE_DIR, os.pardir))
CACHE_DIR = os.path.join(PARENT_DIR, 'settings')
CACHE_FILE = os.path.join(CACHE_DIR, 'banks_cache.json')

# Time-to-live for cache in days
CACHE_TTL_DAYS = 2

# Flutterwave API settings
API_URL = "https://api.flutterwave.com/v3/banks/NG"
HEADERS = {
    "accept": "application/json",
    "Authorization": "Bearer FLWSECK-5f8488d60a1481b9c8597b572d5e1933-19742af68aavt-X",
    "Content-Type": "application/json"
}

def load_banks(cache_file=CACHE_FILE):
    """
    Load bank list from local cache if available and fresh.
    Otherwise fetch from Flutterwave API and save to cache.
    """
    def fetch_and_cache():
        response = requests.get(API_URL, headers=HEADERS)
        response.raise_for_status()
        # Safely parse JSON
        try:
            data = response.json()
        except (ValueError, json.JSONDecodeError) as e:
            raise RuntimeError("Invalid JSON received from API.") from e

        if data.get("status") == "success":
            banks = data.get("data", [])
            # Ensure directory exists
            os.makedirs(os.path.dirname(cache_file), exist_ok=True)
            # Save to cache
            with open(cache_file, 'w') as f:
                json.dump(banks, f)
            return banks

        raise RuntimeError(f"Error fetching banks: {data.get('message', 'Unknown')}")

    # If cache exists and is fresh, use it
    if os.path.exists(cache_file):
        mtime = datetime.fromtimestamp(os.path.getmtime(cache_file))
        if datetime.now() - mtime < timedelta(days=CACHE_TTL_DAYS):
            with open(cache_file, 'r') as f:
                try:
                    return json.load(f)
                except json.JSONDecodeError:
                    # Corrupted cache, refetch
                    return fetch_and_cache()
        # Cache is stale
        return fetch_and_cache()

    # No cache exists
    return fetch_and_cache()


def get_bank_code_by_name_fuzzy(bank_name_text: str, threshold: int = 75) -> str:
    """
    Return the bank code for a given bank name using fuzzy matching.
    Loads and caches the bank list automatically.
    """
    banks = load_banks()
    best_match_code = None
    highest_score = -1

    for bank in banks:
        name = bank.get("name", "") or ""
        score = fuzz.partial_ratio(bank_name_text.lower(), name.lower())
        if score > highest_score and score >= threshold:
            highest_score = score
            best_match_code = bank.get("code")

    if best_match_code:
        return best_match_code
    return f"Bank '{bank_name_text}' not found or no close match (score below {threshold})."

# Example usage
if __name__ == "__main__":
    samples = [
        "First Bank of Nigeria",
        "Zenith Bnkk",   # typo
        "Access",        # partial
        "palmpay",
        "gtbank",        # case variation
        "FCMB"
    ]
    for name in samples:
        try:
            code = get_bank_code_by_name_fuzzy(name)
            print(f"Searching for '{name}': Code -> {code}")
        except Exception as e:
            print(f"Error retrieving code for '{name}': {e}")
