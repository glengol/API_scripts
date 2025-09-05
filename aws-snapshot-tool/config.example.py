"""
Example configuration file for Volume Snapshot Tool.
Copy this file to config.py and update with your actual Firefly API endpoints.
"""

# Firefly API Configuration
FIREFLY_CONFIG = {
    # Base URL for your Firefly API instance
    'base_url': 'https://api.firefly.ai',
    
    # API endpoints - Based on .firefly-api/externalAPI.json
    'endpoints': {
        # Main inventory endpoint for all asset types
        'inventory': '/api/v1.0/inventory',
        
        # Authentication endpoint
        'login': '/api/v1.0/login',
        
        # Asset types for filtering
        'asset_types': {
            'ebs_snapshot': 'aws_ebs_snapshot',
            'db_snapshot': 'aws_db_snapshot',
            'ec2_instance': 'aws_instance',
            'db_instance': 'aws_db_instance',
            'ebs_volume': 'aws_ebs_volume'
        }
    },
    
    # Field mappings - Based on .firefly-api/externalAPI.json
    'field_mappings': {
        'snapshot': {
            'id': 'assetId',               # Snapshot ID field (Firefly API)
            'creation_date': 'resourceCreationDate', # Creation timestamp field (epoch)
            'size_gb': 'size',             # Size in GB field (may not be available)
            'account_id': 'providerId',    # Account ID field
            'region': 'region',            # Region field (may need extraction from ARN)
            'tags': 'tags',                # Tags array field (may be in tfObject)
            'arn': 'arn',                  # ARN for additional context
        },
        'ebs_snapshot': {
            'volume_id': 'volumeId',       # Volume ID for parent resolution
        },
        'db_snapshot': {
            'db_instance_id': 'dbInstanceIdentifier', # DB instance ID for parent resolution
        },
        'volume': {
            'instance_id': 'instanceId',   # EC2 instance ID field
        },
        'ec2_instance': {
            'instance_id': 'resourceId',   # Instance ID field
            'state': 'state',              # State field
            'tags': 'tags',                # Tags array field
        },
        'db_instance': {
            'db_instance_id': 'resourceId', # DB instance ID field
            'state': 'state',              # State field
            'tags': 'tags',                # Tags array field
        },
        'tag': {
            'key': 'key',                  # Tag key field
            'value': 'value',              # Tag value field
        }
    },
    
    # Pagination configuration - Based on .firefly-api/externalAPI.json
    'pagination': {
        'type': 'after_key',              # Firefly API uses afterKey for pagination
        'after_key_field': 'afterKey',    # Field name for next page key
        'results_field': 'responseObjects', # Field name containing results array
        'max_page_size': 10000,           # Maximum items per page
    },
    
    # Rate limiting and retry configuration
    'rate_limiting': {
        'max_retries': 5,
        'base_delay': 1,  # seconds
        'max_delay': 60,  # seconds
        'retry_status_codes': [429, 502, 503, 504],
    }
}

# Example usage in your code:
# from config import FIREFLY_CONFIG
# 
# base_url = FIREFLY_CONFIG['base_url']
# ebs_endpoint = FIREFLY_CONFIG['endpoints']['ebs_snapshots']
# snapshot_id_field = FIREFLY_CONFIG['field_mappings']['snapshot']['id']
