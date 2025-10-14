#!/usr/bin/env python3
"""
Test script to verify that admin changes to service IDs are properly used
instead of hardcoded values.
"""

import sys
import os

# Add current directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.boost_provider_utils import get_active_provider, ProviderConfig
from utils.boosting_service_manager import get_boosting_service_manager, ServiceType
from utils.job_system import ProviderSnapshot, _get_provider_service_id

def test_service_id_retrieval():
    """Test that service IDs are correctly retrieved from database."""
    print("=== Testing Service ID Retrieval ===")
    
    # Get active provider (should be plugsmms if set as active)
    provider = get_active_provider()
    print(f"Active provider: {provider.name}")
    
    # Show hardcoded values from PROVIDERS dict
    print(f"\nHardcoded values from PROVIDERS dict:")
    print(f"  Views service ID: {provider.view_service_id}")
    print(f"  Likes service ID: {provider.like_service_id}")
    
    # Get values from database via BoostingServiceManager
    service_manager = get_boosting_service_manager()
    db_views_id = service_manager.get_provider_service_id(ServiceType.VIEWS, provider.name)
    db_likes_id = service_manager.get_provider_service_id(ServiceType.LIKES, provider.name)
    
    print(f"\nDatabase values from BoostingServiceManager:")
    print(f"  Views service ID: {db_views_id}")
    print(f"  Likes service ID: {db_likes_id}")
    
    # Test the helper functions
    helper_views_id = _get_provider_service_id(provider, ServiceType.VIEWS)
    helper_likes_id = _get_provider_service_id(provider, ServiceType.LIKES)
    
    print(f"\nHelper function values (what boost system will use):")
    print(f"  Views service ID: {helper_views_id}")
    print(f"  Likes service ID: {helper_likes_id}")
    
    # Test ProviderSnapshot creation (used by job system)
    snapshot = ProviderSnapshot.from_provider_config(provider)
    print(f"\nProviderSnapshot values (what job system will use):")
    print(f"  Views service ID: {snapshot.view_service_id}")
    print(f"  Likes service ID: {snapshot.like_service_id}")
    
    # Verify the fix worked
    if provider.name == "plugsmms":
        print(f"\n=== VERIFICATION FOR PLUGSMMS ===")
        print(f"Expected database values: views=7750, likes=11023")
        print(f"Hardcoded values:        views={provider.view_service_id}, likes={provider.like_service_id}")
        print(f"Helper function values:  views={helper_views_id}, likes={helper_likes_id}")
        print(f"Snapshot values:         views={snapshot.view_service_id}, likes={snapshot.like_service_id}")
        
        views_fixed = helper_views_id == 7750
        likes_fixed = helper_likes_id == 11023
        snapshot_views_fixed = snapshot.view_service_id == 7750
        snapshot_likes_fixed = snapshot.like_service_id == 11023
        
        print(f"\n✅ Views service ID correctly uses database value: {views_fixed}")
        print(f"✅ Likes service ID correctly uses database value: {likes_fixed}")
        print(f"✅ Snapshot views service ID correctly uses database value: {snapshot_views_fixed}")
        print(f"✅ Snapshot likes service ID correctly uses database value: {snapshot_likes_fixed}")
        
        if all([views_fixed, likes_fixed, snapshot_views_fixed, snapshot_likes_fixed]):
            print(f"\n🎉 SUCCESS: Admin service ID changes are now working!")
        else:
            print(f"\n❌ FAILURE: Some values are still using hardcoded values")
    else:
        print(f"\nNote: Test designed for plugsmms provider, current provider is {provider.name}")

if __name__ == "__main__":
    test_service_id_retrieval()