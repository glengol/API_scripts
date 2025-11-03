"""
Data Normalization - Tag extraction, name selection, state mapping, date parsing, age calculation.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Union
from dateutil import parser

logger = logging.getLogger(__name__)


class DataNormalizer:
    """
    Normalizes data from Firefly API responses to standardized CSV format.
    """
    
    def __init__(self, pricing_fetcher):
        self.environment_tag_keys = ['environment', 'env', 'Environment']
        self.pricing_fetcher = pricing_fetcher
    
    def extract_environment(self, tags: Union[Dict[str, Any], List[Dict[str, Any]]]) -> Optional[str]:
        """
        Extract environment from tags using case-insensitive priority order.
        """
        if not tags:
            return None
        
        # Check priority order - first match wins
        for key in self.environment_tag_keys:
            # Handle dict tags (as in your data: {"Name": "attached-ebs"})
            if isinstance(tags, dict):
                if key.lower() in [k.lower() for k in tags.keys()]:
                    # Find the actual key (case-insensitive)
                    actual_key = next(k for k in tags.keys() if k.lower() == key.lower())
                    return tags[actual_key]
            
            # Handle list tags (fallback for other formats)
            elif isinstance(tags, list):
                for tag in tags:
                    tag_key = tag.get('key')
                    tag_value = tag.get('value')
                    if tag_key and tag_value and tag_key.lower() == key.lower():
                        return tag_value
        
        return None
    
    def extract_name(self, resource: Dict[str, Any], resource_type: str) -> str:
        """
        Extract resource name from tags or fallback to ID.
        """
        # Handle different tag structures from Firefly API
        tags = resource.get('tags', {})
        
        # Check if tags is a dict (as in your data: {"Name": "attached-ebs"})
        if isinstance(tags, dict):
            name_value = tags.get('Name')
            if name_value:
                return name_value
        
        # Check if tags is a list (fallback for other formats)
        elif isinstance(tags, list):
            for tag in tags:
                key = tag.get('key')
                value = tag.get('value')
                if key and key.lower() == 'name' and value:
                    return value
        
        # Fallback to identifier
        if resource_type == 'ec2_instance':
            return resource.get('resourceId', '') or resource.get('assetId', '') or resource.get('id', 'unknown')
        elif resource_type == 'db_instance':
            return resource.get('resourceId', '') or resource.get('assetId', '') or resource.get('id', 'unknown')
        else:
            return resource.get('assetId', '') or resource.get('resourceId', '') or resource.get('id', 'unknown')
    
    def extract_state(self, resource: Dict[str, Any], resource_type: str) -> str:
        """
        Extract resource state from documented fields.
        """
        # Extract state using actual Firefly API field names
        if resource_type == 'ec2_instance':
            # Check multiple possible state fields
            state = (resource.get('state') or 
                    resource.get('instance_state') or 
                    resource.get('resource_status'))
        elif resource_type == 'db_instance':
            state = (resource.get('state') or 
                    resource.get('db_instance_status') or 
                    resource.get('resource_status'))
        else:
            state = (resource.get('state') or 
                    resource.get('resource_status'))
        
        return state if state else 'unknown'
    
    def parse_date(self, date_str: str) -> Optional[datetime]:
        """
        Parse date string to UTC datetime.
        """
        if not date_str:
            return None
        
        try:
            # Parse the date string
            dt = parser.parse(date_str)
            
            # Ensure it's timezone-aware, default to UTC if not
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                # Convert to UTC
                dt = dt.astimezone(timezone.utc)
            
            return dt
        except (ValueError, TypeError) as e:
            logger.warning(f"Could not parse date '{date_str}': {e}")
            return None
    
    def calculate_age_days(self, creation_date: datetime) -> int:
        """
        Calculate age in days from creation date.
        """
        if not creation_date:
            return 0
        
        now = datetime.now(timezone.utc)
        age_delta = now - creation_date
        age_days = int(age_delta.days)
        
        # Return 0 for future dates (negative age)
        return max(0, age_days)
    
    def normalize_snapshot_data(self, snapshot: Dict[str, Any], snapshot_type: str,
                               parent: Optional[Dict[str, Any]] = None,
                               orphaned: bool = False) -> Dict[str, Any]:
        """
        Normalize snapshot data to CSV format.
        """
        # Use Firefly API field names
        normalized = {
            'snapshot_id': snapshot.get('assetId', '') or snapshot.get('resourceId', '') or snapshot.get('id', ''),
            'snapshot_type': snapshot_type,
            'creation_date': '',
            'size_gb': '',
            'storage_tier': '',  # Store storage tier for EBS snapshots
            'parent_resource_type': '',
            'parent_resource_id': '',
            'parent_name': '',
            'parent_state': '',
            'account_id': '',
            'environment': '',
            'region': '',
            'orphaned': orphaned,
            'age_days': 0
        }
        
        # Parse creation date - using Firefly API field names
        creation_date_str = snapshot.get('resourceCreationDate') or snapshot.get('resource_creation_time')
        if creation_date_str:
            # Convert epoch timestamp to datetime
            try:
                creation_date = datetime.fromtimestamp(creation_date_str, tz=timezone.utc)
                normalized['creation_date'] = creation_date.isoformat()
                normalized['age_days'] = self.calculate_age_days(creation_date)
            except (ValueError, TypeError):
                logger.warning("Invalid creation date format — not found in snapshot schema")
        else:
            logger.warning("Missing creation date — not found in snapshot schema")
        
        # Extract size - using actual Firefly API field names
        if snapshot_type == 'ebs':
            tf_object = snapshot.get('tfObject', {})
            storage_tier = tf_object.get('storage_tier')
            # Store storage_tier for cost calculation
            normalized['storage_tier'] = storage_tier if storage_tier else ''
            size_gb = None
            
            if storage_tier == 'standard':
                # For standard tier: try full_snapshot_size_in_bytes first, fallback to volume_size
                full_size_bytes = tf_object.get('full_snapshot_size_in_bytes')
                if full_size_bytes is not None:
                    # Convert bytes to GB
                    size_gb = full_size_bytes / (1024 * 1024 * 1024)
                    logger.debug(f"Using full_snapshot_size_in_bytes for standard tier snapshot {snapshot.get('assetId', '') or snapshot.get('resourceId', '')}")
                else:
                    # Fallback to volume_size if full_snapshot_size_in_bytes is missing
                    size_gb = tf_object.get('volume_size')
                    if size_gb is not None:
                        logger.debug(f"Using volume_size as fallback for standard tier snapshot {snapshot.get('assetId', '') or snapshot.get('resourceId', '')}")
            else:
                # For archive tier or any other tier (including None/missing): always use volume_size
                size_gb = tf_object.get('volume_size')
                if size_gb is not None:
                    logger.debug(f"Using volume_size for {storage_tier or 'unspecified'} tier snapshot {snapshot.get('assetId', '') or snapshot.get('resourceId', '')}")
            
            # Log detailed warning if size is still missing
            if size_gb is None:
                snapshot_id = snapshot.get('assetId', '') or snapshot.get('resourceId', '') or 'unknown'
                logger.warning(
                    f"Missing size information for snapshot {snapshot_id}: "
                    f"storage_tier={storage_tier}, "
                    f"full_snapshot_size_in_bytes={tf_object.get('full_snapshot_size_in_bytes')}, "
                    f"volume_size={tf_object.get('volume_size')}"
                )
        elif snapshot_type == 'db':
            size_gb = snapshot.get('tfObject', {}).get('allocated_storage')
        else:
            size_gb = None
            
        if size_gb is not None:
            normalized['size_gb'] = str(size_gb)
        else:
            normalized['size_gb'] = ''  # Leave blank as per requirements
        
        # Extract account and region
        account_id = snapshot.get('providerId') or snapshot.get('owner_id')
        if account_id:
            normalized['account_id'] = str(account_id)
        else:
            logger.warning("Missing account ID — not found in snapshot schema")
        
        # Extract region from ARN or other available fields
        region = snapshot.get('region') or snapshot.get('availabilityZone')
        if region:
            # Extract region from AZ (e.g., "us-east-1a" -> "us-east-1")
            if region.endswith(('a', 'b', 'c', 'd', 'e', 'f')):
                region = region[:-1]
            normalized['region'] = region
        else:
            # Try to extract region from ARN if available
            arn = snapshot.get('arn', '')
            if arn and ':' in arn:
                # ARN format: arn:aws:ec2:region:account:volume/vol-id
                # or: arn:aws:ec2:region::snapshot/snap-id
                parts = arn.split(':')
                if len(parts) >= 4:
                    region = parts[3]
                    normalized['region'] = region
                else:
                    logger.warning("Could not extract region from ARN")
            else:
                logger.warning("Missing region information — not found in snapshot schema")
        
        # Extract environment from tags - handle different tag structures
        tags = snapshot.get('tfObject', {}).get('tags', {})
        if tags:
            normalized['environment'] = self.extract_environment(tags) or ''
        else:
            # Check if tagsList has any content
            tags_list = snapshot.get('tagsList', [])
            if tags_list:
                # Convert tagsList to dict format for compatibility
                tags_dict = {}
                for tag in tags_list:
                    if isinstance(tag, dict) and 'key' in tag and 'value' in tag:
                        tags_dict[tag['key']] = tag['value']
                    elif isinstance(tag, str) and '=' in tag:
                        key, value = tag.split('=', 1)
                        tags_dict[key] = value
                if tags_dict:
                    normalized['environment'] = self.extract_environment(tags_dict) or ''
                # No warning for missing tags - this is normal for many AWS resources
            # No warning for missing tags - this is normal for many AWS resources
        
        # Handle parent resource data
        if parent and not orphaned:
            if snapshot_type == 'ebs':
                normalized['parent_resource_type'] = 'ec2_instance'
                normalized['parent_resource_id'] = parent.get('resourceId', '') or parent.get('assetId', '') or parent.get('id', '')
                normalized['parent_name'] = self.extract_name(parent, 'ec2_instance')
                normalized['parent_state'] = self.extract_state(parent, 'ec2_instance')
            elif snapshot_type == 'db':
                normalized['parent_resource_type'] = 'db_instance'
                normalized['parent_resource_id'] = parent.get('resourceId', '') or parent.get('assetId', '') or parent.get('id', '')
                normalized['parent_name'] = self.extract_name(parent, 'db_instance')
                normalized['parent_state'] = self.extract_state(parent, 'db_instance')
        else:
            # Set default values for orphaned snapshots
            normalized['parent_resource_type'] = ''
            normalized['parent_resource_id'] = ''
            normalized['parent_name'] = ''
            normalized['parent_state'] = ''
        
        # Calculate costs
        normalized['monthly_cost'] = self.calculate_monthly_cost(normalized)
        normalized['cost_since_creation'] = self.calculate_cost_since_creation(normalized)
        
        return normalized
    
    def calculate_monthly_cost(self, snapshot_data: Dict[str, Any]) -> str:
        """Calculate monthly cost for a snapshot."""
        self.pricing_fetcher.ensure_pricing_loaded() # Ensure pricing data is loaded
        size_gb = snapshot_data.get('size_gb')
        region = snapshot_data.get('region')
        snapshot_type = snapshot_data.get('snapshot_type')
        storage_tier = snapshot_data.get('storage_tier')  # Get storage tier for EBS snapshots
        
        if not all([size_gb, region, snapshot_type]):
            return 'prices_not_provided'
        try:
            # Pass storage_tier for EBS snapshots (None for DB snapshots)
            tier = storage_tier if storage_tier and snapshot_type == 'ebs' else None
            cost = self.pricing_fetcher.calculate_monthly_cost(float(size_gb), region, snapshot_type, tier)
            if cost is not None:
                return f"${cost:.4f}"
        except (ValueError, TypeError):
            pass
        return 'prices_not_provided'
    
    def calculate_cost_since_creation(self, snapshot_data: Dict[str, Any]) -> str:
        """Calculate total cost since creation."""
        self.pricing_fetcher.ensure_pricing_loaded() # Ensure pricing data is loaded
        size_gb = snapshot_data.get('size_gb')
        region = snapshot_data.get('region')
        snapshot_type = snapshot_data.get('snapshot_type')
        age_days = snapshot_data.get('age_days')
        storage_tier = snapshot_data.get('storage_tier')  # Get storage tier for EBS snapshots
        
        # Fixed: age_days can be 0, which is falsy. Check for None instead.
        if not all([size_gb, region, snapshot_type]) or age_days is None:
            return 'prices_not_provided'
        try:
            # Pass storage_tier for EBS snapshots (None for DB snapshots)
            tier = storage_tier if storage_tier and snapshot_type == 'ebs' else None
            cost = self.pricing_fetcher.calculate_cost_since_creation(float(size_gb), region, snapshot_type, int(age_days), tier)
            if cost is not None:
                return f"${cost:.4f}"
        except (ValueError, TypeError):
            pass
        return 'prices_not_provided'
