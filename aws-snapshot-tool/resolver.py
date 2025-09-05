"""
Parent Resource Resolver - Logic to resolve parents only via documented relationships/fields.
"""

import logging
from typing import Dict, Any, Optional, Tuple, List
from firefly_client import FireflyClient

logger = logging.getLogger(__name__)


class ParentResolver:
    """
    Resolves parent resources for snapshots using only documented Firefly API relationships.
    """
    
    def __init__(self, client: FireflyClient):
        self.client = client
    
    def resolve_ebs_parent(self, snapshot: Dict[str, Any], account_id: Optional[str] = None,
                           region: Optional[str] = None) -> Tuple[Optional[Dict[str, Any]], bool]:
        """
        Resolve parent EC2 instance for EBS snapshot.
        Returns (parent_data, orphaned) tuple.
        """
        # Extract volume ID from EBS snapshot - using actual Firefly API field names
        volume_id = snapshot.get('tfObject', {}).get('volume_id')
        
        if not volume_id:
            # Fallback to other possible fields
            volume_id = snapshot.get('volumeId') or snapshot.get('volume_id')
            if not volume_id:
                # Try to extract from ARN or other available fields
                arn = snapshot.get('arn', '')
                if arn and 'volume' in arn:
                    # ARN format: arn:aws:ec2:region:account:volume/vol-id
                    volume_id = arn.split('/')[-1]
                    logger.info(f"Extracted volume ID from ARN: {volume_id}")
                else:
                    logger.debug("Missing volume ID — not found in EBS snapshot schema (this is normal for some snapshots)")
                    return None, True
        
        # Use batch volume lookup if available (this will be called from the optimized main loop)
        # For now, fall back to individual lookup
        volume = self.client.get_volume_details(volume_id, account_id, region)
        if not volume:
            logger.debug(f"Volume {volume_id} not found in inventory (likely deleted), will try instance-first resolution...")
            # Don't return here - continue to instance-first resolution
            volume = None  # Set volume to None to skip volume-based resolution
        
        # Extract instance ID from volume - using actual Firefly API field names
        # Strategy 1: Check volume attachments array first (only if volume exists)
        instance_id = None
        
        if volume:
            # Check attachments array (as shown in your data)
            attachments = volume.get('attachments', [])
            if attachments and len(attachments) > 0:
                instance_id = attachments[0].get('instance_id')
            
            # Fallback to direct fields
            if not instance_id:
                instance_id = volume.get('instanceId') or volume.get('instance_id') or volume.get('attachedInstanceId')
        
        # Strategy 2: If volume attachments are empty, search instances for this volume
        found_instance = None
        if not instance_id:
            logger.debug(f"Volume {volume_id} has no attachments, searching instances for volume reference...")
            try:
                # Search for instances that reference this volume
                instances = list(self.client.list_ec2_instances(account_id, region))
                for instance in instances:
                    ebs_devices = instance.get('tfObject', {}).get('ebs_block_device', [])
                    for device in ebs_devices:
                        if device.get('volume_id') == volume_id:
                            instance_id = instance.get('resourceId')
                            found_instance = instance  # Store the instance data we found
                            logger.info(f"Found instance {instance_id} referencing volume {volume_id} via ebs_block_device")
                            break
                    if instance_id:
                        break
            except Exception as e:
                logger.debug(f"Error searching instances for volume {volume_id}: {e}")
        
        # Strategy 3: If volume lookup fails entirely, try instance-first resolution
        if not instance_id:
            logger.debug(f"Volume {volume_id} not found in inventory, trying instance-first resolution...")
            try:
                # Search for instances that reference this volume
                instances = list(self.client.list_ec2_instances(account_id, region))
                for instance in instances:
                    ebs_devices = instance.get('tfObject', {}).get('ebs_block_device', [])
                    for device in ebs_devices:
                        if device.get('volume_id') == volume_id:
                            instance_id = instance.get('resourceId')
                            found_instance = instance  # Store the instance data we found
                            logger.info(f"Found instance {instance_id} referencing volume {volume_id} via ebs_block_device (instance-first resolution)")
                            break
                    if instance_id:
                        break
            except Exception as e:
                logger.debug(f"Error searching instances for volume {volume_id}: {e}")
        
        # If we found an instance, get its details
        if instance_id:
            try:
                instance = self.client.get_ec2_instance_details(instance_id, account_id, region)
                if instance:
                    return instance, False
                else:
                    logger.debug(f"Instance {instance_id} not found in inventory (likely deleted)")
            except Exception as e:
                logger.debug(f"Error fetching instance {instance_id}: {e}")
        
        # If we found an instance via ebs_block_device but couldn't fetch details, return what we have
        if found_instance:
            return found_instance, False
        
        # No parent found
        return None, True
    
    def resolve_ebs_parents_batch(self, snapshots: List[Dict[str, Any]], account_id: Optional[str] = None,
                                  region: Optional[str] = None) -> Dict[str, Tuple[Optional[Dict[str, Any]], bool]]:
        """
        Batch resolve parent EC2 instances for multiple EBS snapshots.
        This dramatically reduces API calls by fetching volumes and instances in batches.
        """
        if not snapshots:
            return {}
        
        # Extract all volume IDs from snapshots
        volume_ids = []
        snapshot_volume_map = {}  # snapshot_id -> volume_id
        
        for snapshot in snapshots:
            volume_id = snapshot.get('tfObject', {}).get('volume_id')
            if not volume_id:
                volume_id = snapshot.get('volumeId') or snapshot.get('volume_id')
                if not volume_id:
                    arn = snapshot.get('arn', '')
                    if arn and 'volume' in arn:
                        volume_id = arn.split('/')[-1]
            
            if volume_id:
                volume_ids.append(volume_id)
                snapshot_volume_map[snapshot.get('resourceId')] = volume_id
        
        # Batch fetch all volumes
        volumes = self.client.get_volumes_batch(volume_ids, account_id, region)
        
        # Batch fetch all EC2 instances
        instances = self.client.get_ec2_instances_batch(account_id, region)
        
        # Build instance lookup map for ebs_block_device references
        instance_volume_map = {}  # volume_id -> instance
        for instance in instances:
            ebs_devices = instance.get('tfObject', {}).get('ebs_block_device', [])
            for device in ebs_devices:
                vol_id = device.get('volume_id')
                if vol_id:
                    instance_volume_map[vol_id] = instance
        
        # Resolve parents for each snapshot
        results = {}
        for snapshot in snapshots:
            snapshot_id = snapshot.get('resourceId')
            volume_id = snapshot_volume_map.get(snapshot_id)
            
            if not volume_id:
                results[snapshot_id] = (None, True)
                continue
            
            # Check volume attachments first
            volume = volumes.get(volume_id)
            instance_id = None
            found_instance = None
            
            if volume:
                attachments = volume.get('attachments', [])
                if attachments:
                    instance_id = attachments[0].get('instance_id')
            
            # If no attachment, check ebs_block_device references
            if not instance_id and volume_id in instance_volume_map:
                found_instance = instance_volume_map[volume_id]
                instance_id = found_instance.get('resourceId')
            
            # Get instance details if found
            if instance_id:
                # Find instance in our batch-fetched instances
                for instance in instances:
                    if instance.get('resourceId') == instance_id:
                        results[snapshot_id] = (instance, False)
                        break
                else:
                    # Instance not in batch, fetch individually
                    try:
                        instance = self.client.get_ec2_instance_details(instance_id, account_id, region)
                        results[snapshot_id] = (instance, False) if instance else (None, True)
                    except Exception:
                        results[snapshot_id] = (None, True)
            elif found_instance:
                results[snapshot_id] = (found_instance, False)
            else:
                results[snapshot_id] = (None, True)
        
        return results
    
    def resolve_db_parent(self, snapshot: Dict[str, Any], account_id: Optional[str] = None,
                          region: Optional[str] = None) -> Tuple[Optional[Dict[str, Any]], bool]:
        """
        Resolve parent DB instance for DB snapshot.
        Returns (parent_data, orphaned) tuple.
        """
        # Extract DB instance identifier from DB snapshot - using actual Firefly API field names
        instance_id = snapshot.get('tfObject', {}).get('db_instance_identifier')
        
        if not instance_id:
            # Fallback to other possible fields
            instance_id = snapshot.get('dbInstanceIdentifier') or snapshot.get('db_instance_identifier') or snapshot.get('sourceDbInstanceIdentifier')
            if not instance_id:
                # Try to extract from ARN or other available fields
                arn = snapshot.get('arn', '')
                if arn and 'db' in arn:
                    # ARN format: arn:aws:rds:region:account:db-snapshot:snapshot-id
                    # The source DB instance might be in the snapshot name or other fields
                    logger.info(f"Extracted DB snapshot ARN: {arn}")
                    # For now, we'll need to rely on the direct field or leave as orphaned
                    logger.debug("Missing DB instance identifier — not found in DB snapshot schema (this is normal for some snapshots)")
                    return None, True
                else:
                    logger.debug("Missing DB instance identifier — not found in DB snapshot schema (this is normal for some snapshots)")
                    return None, True
        
        # Get DB instance details
        instance = self.client.get_db_instance(instance_id, account_id, region)
        if not instance:
            logger.debug(f"Could not resolve DB instance {instance_id} for snapshot {snapshot.get('id')} (this is normal for deleted instances)")
            return None, True
        
        return instance, False
    
    def resolve_parent(self, snapshot: Dict[str, Any], snapshot_type: str,
                       account_id: Optional[str] = None, region: Optional[str] = None) -> Tuple[Optional[Dict[str, Any]], bool]:
        """
        Resolve parent resource based on snapshot type.
        Returns (parent_data, orphaned) tuple.
        """
        if snapshot_type == 'ebs':
            return self.resolve_ebs_parent(snapshot, account_id, region)
        elif snapshot_type == 'db':
            return self.resolve_db_parent(snapshot, account_id, region)
        else:
            logger.error(f"Unknown snapshot type: {snapshot_type}")
            return None, True
