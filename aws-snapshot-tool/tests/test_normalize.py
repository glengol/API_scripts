"""
Unit tests for the normalize module.
"""

import pytest
from datetime import datetime, timezone
from normalize import DataNormalizer


class TestDataNormalizer:
    """Test cases for DataNormalizer class."""
    
    def setup_method(self):
        """Setup test fixtures."""
        self.normalizer = DataNormalizer()
    
    def test_extract_environment_priority_order(self):
        """Test environment tag extraction with priority order."""
        tags = [
            {'key': 'env', 'value': 'staging'},
            {'key': 'environment', 'value': 'production'},
            {'key': 'Environment', 'value': 'dev'}
        ]
        
        # Should return 'production' as 'environment' comes first in priority list
        result = self.normalizer.extract_environment(tags)
        assert result == 'production'
    
    def test_extract_environment_case_insensitive(self):
        """Test environment tag extraction is case-insensitive."""
        tags = [
            {'key': 'ENVIRONMENT', 'value': 'prod'},
            {'key': 'ENV', 'value': 'staging'}
        ]
        
        # Should return 'prod' as 'environment' has higher priority than 'env'
        result = self.normalizer.extract_environment(tags)
        assert result == 'prod'
    
    def test_extract_environment_no_tags(self):
        """Test environment extraction with no tags."""
        result = self.normalizer.extract_environment([])
        assert result is None
    
    def test_extract_environment_missing_keys(self):
        """Test environment extraction with malformed tags."""
        tags = [
            {'key': 'environment', 'value': 'prod'},
            {'key': None, 'value': 'staging'},
            {'key': 'env', 'value': None}
        ]
        
        result = self.normalizer.extract_environment(tags)
        assert result == 'prod'
    
    def test_extract_name_ec2_with_name_tag(self):
        """Test name extraction for EC2 instance with Name tag."""
        resource = {
            'instance_id': 'i-1234567890abcdef0',
            'tags': [
                {'key': 'Name', 'value': 'web-server-01'},
                {'key': 'environment', 'value': 'prod'}
            ]
        }
        
        result = self.normalizer.extract_name(resource, 'ec2_instance')
        assert result == 'web-server-01'
    
    def test_extract_name_ec2_fallback_to_id(self):
        """Test name extraction for EC2 instance falls back to instance ID."""
        resource = {
            'resourceId': 'i-1234567890abcdef0',  # Updated to Firefly API field name
            'tags': [
                {'key': 'environment', 'value': 'prod'}
            ]
        }
        
        result = self.normalizer.extract_name(resource, 'ec2_instance')
        assert result == 'i-1234567890abcdef0'
    
    def test_extract_name_db_instance(self):
        """Test name extraction for DB instance."""
        resource = {
            'db_instance_identifier': 'my-db-instance',
            'tags': [
                {'key': 'Name', 'value': 'production-database'}
            ]
        }
        
        result = self.normalizer.extract_name(resource, 'db_instance')
        assert result == 'production-database'
    
    def test_parse_date_utc(self):
        """Test date parsing with UTC timezone."""
        date_str = "2024-01-15T10:30:00Z"
        result = self.normalizer.parse_date(date_str)
        
        assert result is not None
        assert result.tzinfo == timezone.utc
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
    
    def test_parse_date_local_timezone(self):
        """Test date parsing with local timezone converts to UTC."""
        date_str = "2024-01-15T10:30:00-05:00"
        result = self.normalizer.parse_date(date_str)
        
        assert result is not None
        assert result.tzinfo == timezone.utc
    
    def test_parse_date_no_timezone(self):
        """Test date parsing without timezone defaults to UTC."""
        date_str = "2024-01-15T10:30:00"
        result = self.normalizer.parse_date(date_str)
        
        assert result is not None
        assert result.tzinfo == timezone.utc
    
    def test_parse_date_invalid(self):
        """Test date parsing with invalid date returns None."""
        date_str = "invalid-date"
        result = self.normalizer.parse_date(date_str)
        
        assert result is None
    
    def test_calculate_age_days(self):
        """Test age calculation in days."""
        # Create a date 5 days ago using timedelta for safety
        from datetime import timedelta
        past_date = datetime.now(timezone.utc) - timedelta(days=5)
        
        result = self.normalizer.calculate_age_days(past_date)
        assert result == 5
    
    def test_calculate_age_days_future_date(self):
        """Test age calculation with future date returns 0."""
        from datetime import timedelta
        future_date = datetime.now(timezone.utc) + timedelta(days=1)
        
        result = self.normalizer.calculate_age_days(future_date)
        assert result == 0
    
    def test_normalize_snapshot_data_ebs_with_parent(self):
        """Test normalization of EBS snapshot with resolved parent."""
        snapshot = {
            'assetId': 'snap-1234567890abcdef0',  # Updated to Firefly API field name
            'resourceCreationDate': 1705312200,  # Epoch timestamp for 2024-01-15T10:30:00Z
            'size': 100,  # Updated to Firefly API field name
            'providerId': '123456789012',  # Updated to Firefly API field name
            'region': 'us-east-1',  # Updated to Firefly API field name
            'tags': [
                {'key': 'environment', 'value': 'prod'}
            ]
        }
        
        parent = {
            'resourceId': 'i-1234567890abcdef0',  # Updated to Firefly API field name
            'tags': [
                {'key': 'Name', 'value': 'web-server-01'}
            ],
            'state': 'running'  # Updated to Firefly API field name
        }
        
        result = self.normalizer.normalize_snapshot_data(
            snapshot, 'ebs', parent, False
        )
        
        assert result['snapshot_id'] == 'snap-1234567890abcdef0'
        assert result['snapshot_type'] == 'ebs'
        assert result['size_gb'] == '100'
        assert result['account_id'] == '123456789012'
        assert result['region'] == 'us-east-1'
        assert result['environment'] == 'prod'
        assert result['parent_resource_type'] == 'ec2_instance'
        assert result['parent_resource_id'] == 'i-1234567890abcdef0'
        assert result['parent_name'] == 'web-server-01'
        assert result['parent_state'] == 'running'
        assert result['orphaned'] is False
        assert result['age_days'] > 0
    
    def test_normalize_snapshot_data_orphaned(self):
        """Test normalization of orphaned snapshot."""
        snapshot = {
            'id': 'snap-1234567890abcdef0',
            'start_time': '2024-01-15T10:30:00Z',
            'volume_size': 100,
            'owner_id': '123456789012',
            'availability_zone': 'us-east-1a',
            'tags': []
        }
        
        result = self.normalizer.normalize_snapshot_data(
            snapshot, 'ebs', None, True
        )
        
        assert result['orphaned'] is True
        assert result['parent_resource_type'] == ''
        assert result['parent_resource_id'] == ''
        assert result['parent_name'] == ''
        assert result['parent_state'] == ''
