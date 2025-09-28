#!/usr/bin/env python3
# utils/boosting_service_manager.py
# Service for managing boosting service provider mappings

import sqlite3
import logging
import json
from typing import Optional, List, Dict, Any
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

from utils.db_utils import get_connection, DB_FILE

logger = logging.getLogger(__name__)

class ServiceType(Enum):
    LIKES = "likes"
    VIEWS = "views"
    COMMENTS = "comments"

@dataclass
class BoostingService:
    """Boosting service model."""
    id: Optional[int] = None
    name: str = None
    service_type: ServiceType = None
    is_active: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BoostingService':
        """Create BoostingService from database row."""
        return cls(
            id=data.get('id'),
            name=data.get('name'),
            service_type=ServiceType(data.get('service_type')),
            is_active=bool(data.get('is_active', 0)),
            created_at=data.get('created_at'),
            updated_at=data.get('updated_at')
        )

@dataclass
class ServiceProviderMapping:
    """Service provider mapping model."""
    id: Optional[int] = None
    service_id: int = None
    provider_name: str = None
    provider_service_id: int = None
    created_by: Optional[int] = None
    updated_by: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ServiceProviderMapping':
        """Create ServiceProviderMapping from database row."""
        return cls(
            id=data.get('id'),
            service_id=data.get('service_id'),
            provider_name=data.get('provider_name'),
            provider_service_id=data.get('provider_service_id'),
            created_by=data.get('created_by'),
            updated_by=data.get('updated_by'),
            created_at=data.get('created_at'),
            updated_at=data.get('updated_at')
        )

class BoostingServiceManager:
    """Manager for boosting service provider mappings."""
    
    def get_active_service(self, service_type: ServiceType) -> Optional[BoostingService]:
        """Get the currently active service for a given type."""
        
        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            c.execute('''
                SELECT * FROM boosting_services 
                WHERE service_type = ? AND is_active = 1
                ORDER BY id DESC
                LIMIT 1
            ''', (service_type.value,))
            
            row = c.fetchone()
            if row:
                columns = [desc[0] for desc in c.description]
                service_data = dict(zip(columns, row))
                return BoostingService.from_dict(service_data)
            
            return None
    
    def get_service_provider_mappings(self, service_id: int) -> List[ServiceProviderMapping]:
        """Get all provider mappings for a service."""
        
        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            c.execute('''
                SELECT * FROM boosting_service_providers 
                WHERE service_id = ?
                ORDER BY provider_name
            ''', (service_id,))
            
            mappings = []
            columns = [desc[0] for desc in c.description]
            
            for row in c.fetchall():
                mapping_data = dict(zip(columns, row))
                mappings.append(ServiceProviderMapping.from_dict(mapping_data))
            
            return mappings
    
    def get_provider_service_id(self, service_type: ServiceType, provider_name: str) -> Optional[int]:
        """Get provider service ID for active service of given type and provider."""
        
        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            c.execute('''
                SELECT bsp.provider_service_id
                FROM boosting_service_providers bsp
                JOIN boosting_services bs ON bsp.service_id = bs.id
                WHERE bs.service_type = ? AND bs.is_active = 1 
                AND bsp.provider_name = ?
                LIMIT 1
            ''', (service_type.value, provider_name))
            
            row = c.fetchone()
            return row[0] if row else None
    
    def update_provider_service_mapping(
        self,
        service_id: int,
        provider_name: str,
        new_provider_service_id: int,
        admin_id: int,
        reason: str = None
    ) -> bool:
        """
        Update provider service ID for a service/provider combination.
        
        Args:
            service_id: Service ID
            provider_name: Provider name
            new_provider_service_id: New provider service ID
            admin_id: Admin user ID performing the update
            reason: Optional reason for the update
            
        Returns:
            True if successful, False otherwise
        """
        
        with get_connection(DB_FILE) as conn:
            try:
                conn.execute('BEGIN IMMEDIATE')  # Start exclusive transaction
                
                c = conn.cursor()
                
                # Get current mapping
                c.execute('''
                    SELECT * FROM boosting_service_providers 
                    WHERE service_id = ? AND provider_name = ?
                ''', (service_id, provider_name))
                
                row = c.fetchone()
                if not row:
                    logger.warning(f"No mapping found for service {service_id} and provider {provider_name}")
                    return False
                
                columns = [desc[0] for desc in c.description]
                mapping_data = dict(zip(columns, row))
                old_mapping = ServiceProviderMapping.from_dict(mapping_data)
                
                old_provider_service_id = old_mapping.provider_service_id
                
                # Update the mapping
                c.execute('''
                    UPDATE boosting_service_providers 
                    SET provider_service_id = ?, updated_by = ?, updated_at = ?
                    WHERE service_id = ? AND provider_name = ?
                ''', (
                    new_provider_service_id,
                    admin_id,
                    datetime.utcnow().isoformat(),
                    service_id,
                    provider_name
                ))
                
                # Log audit event
                c.execute('''
                    INSERT INTO boosting_service_audit_log (
                        service_provider_id, admin_id, action, 
                        old_provider_service_id, new_provider_service_id, reason
                    ) VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    old_mapping.id,
                    admin_id,
                    "updated",
                    old_provider_service_id,
                    new_provider_service_id,
                    reason
                ))
                
                conn.commit()
                
                logger.info(
                    f"Updated provider service ID for service {service_id}, provider {provider_name}: "
                    f"{old_provider_service_id} -> {new_provider_service_id} by admin {admin_id}"
                )
                
                return True
                
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to update provider service mapping: {str(e)}")
                return False
    
    def get_current_provider_mappings_summary(self) -> Dict[str, Dict[str, int]]:
        """
        Get summary of current provider mappings for active services.
        
        Returns:
            Dict mapping service types to provider mappings
            Example: {"likes": {"smmflare": 8646, "plugsmms": 11023}, "views": {...}}
        """
        
        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            c.execute('''
                SELECT bs.service_type, bsp.provider_name, bsp.provider_service_id
                FROM boosting_services bs
                JOIN boosting_service_providers bsp ON bs.id = bsp.service_id
                WHERE bs.is_active = 1
                ORDER BY bs.service_type, bsp.provider_name
            ''')
            
            mappings = {}
            for row in c.fetchall():
                service_type, provider_name, provider_service_id = row
                
                if service_type not in mappings:
                    mappings[service_type] = {}
                
                mappings[service_type][provider_name] = provider_service_id
            
            return mappings
    
    def validate_provider_service_id(self, provider_name: str, provider_service_id: int) -> bool:
        """
        Validate provider service ID format.
        
        Args:
            provider_name: Provider name
            provider_service_id: Provider service ID to validate
            
        Returns:
            True if valid, False otherwise
        """
        
        # Basic validation - must be positive integer
        if not isinstance(provider_service_id, int) or provider_service_id <= 0:
            return False
        
        # Provider-specific validation rules can be added here
        provider_rules = {
            'smmflare': lambda x: 1000 <= x <= 99999,  # Typical range for SMMFlare
            'plugsmms': lambda x: 1000 <= x <= 99999,  # Typical range for PlugSMMS
            'smmstone': lambda x: 1000 <= x <= 99999,  # Typical range for SMMStone
        }
        
        if provider_name in provider_rules:
            return provider_rules[provider_name](provider_service_id)
        
        # Default validation for unknown providers
        return 1 <= provider_service_id <= 999999
    
    def get_audit_log(self, service_provider_id: int = None, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get audit log for service provider changes.
        
        Args:
            service_provider_id: Optional specific service provider ID
            limit: Maximum number of records to return
            
        Returns:
            List of audit log entries
        """
        
        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            
            if service_provider_id:
                c.execute('''
                    SELECT bsal.*, u.username as admin_username
                    FROM boosting_service_audit_log bsal
                    LEFT JOIN users u ON bsal.admin_id = u.id
                    WHERE bsal.service_provider_id = ?
                    ORDER BY bsal.created_at DESC
                    LIMIT ?
                ''', (service_provider_id, limit))
            else:
                c.execute('''
                    SELECT bsal.*, u.username as admin_username
                    FROM boosting_service_audit_log bsal
                    LEFT JOIN users u ON bsal.admin_id = u.id
                    ORDER BY bsal.created_at DESC
                    LIMIT ?
                ''', (limit,))
            
            entries = []
            columns = [desc[0] for desc in c.description]
            
            for row in c.fetchall():
                entry_data = dict(zip(columns, row))
                entries.append(entry_data)
            
            return entries
    
    def create_service_if_not_exists(self, name: str, service_type: ServiceType) -> int:
        """Create a new boosting service if it doesn't exist."""
        
        with get_connection(DB_FILE) as conn:
            c = conn.cursor()
            
            # Check if service already exists
            c.execute('''
                SELECT id FROM boosting_services 
                WHERE name = ? AND service_type = ?
            ''', (name, service_type.value))
            
            row = c.fetchone()
            if row:
                return row[0]
            
            # Create new service
            c.execute('''
                INSERT INTO boosting_services (name, service_type, is_active, created_at, updated_at)
                VALUES (?, ?, 1, ?, ?)
            ''', (
                name,
                service_type.value,
                datetime.utcnow().isoformat(),
                datetime.utcnow().isoformat()
            ))
            
            conn.commit()
            service_id = c.lastrowid
            
            logger.info(f"Created new boosting service: {name} ({service_type.value}) with ID {service_id}")
            return service_id
    
    def add_provider_mapping(
        self,
        service_id: int,
        provider_name: str,
        provider_service_id: int,
        created_by: int = None
    ) -> bool:
        """Add a new provider mapping for a service."""
        
        with get_connection(DB_FILE) as conn:
            try:
                c = conn.cursor()
                
                c.execute('''
                    INSERT INTO boosting_service_providers (
                        service_id, provider_name, provider_service_id,
                        created_by, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    service_id,
                    provider_name,
                    provider_service_id,
                    created_by,
                    datetime.utcnow().isoformat(),
                    datetime.utcnow().isoformat()
                ))
                
                conn.commit()
                
                logger.info(f"Added provider mapping: service {service_id}, provider {provider_name}, service_id {provider_service_id}")
                return True
                
            except sqlite3.IntegrityError as e:
                logger.warning(f"Provider mapping already exists: {str(e)}")
                return False
            except Exception as e:
                logger.error(f"Failed to add provider mapping: {str(e)}")
                return False


# Global service instance cache
_boosting_service_manager = None

def get_boosting_service_manager():
    """Get or create boosting service manager instance."""
    global _boosting_service_manager
    if _boosting_service_manager is None:
        _boosting_service_manager = BoostingServiceManager()
    return _boosting_service_manager