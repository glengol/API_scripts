"""
Unit tests for the resolver module.
"""

import pytest
from unittest.mock import Mock, patch
from resolver import ParentResolver


class TestParentResolver:
    """Test cases for ParentResolver class."""
    
    def setup_method(self):
        """Setup test fixtures."""
        self.mock_client = Mock()
        self.resolver = ParentResolver(self.mock_client)
    
    def test_resolve_ebs_parent_success(self):
        """Test successful EBS parent resolution."""
        snapshot = {
            'id': 'snap-1234567890abcdef0',
            'volume_id': 'vol-1234567890abcdef0'
        }
        
        volume = {
            'id': 'vol-1234567890abcdef0',
            'instance_id': 'i-1234567890abcdef0'
        }
        
        instance = {
            'instance_id': 'i-1234567890abcdef0',
            'state': {'name': 'running'}
        }
        
        self.mock_client.get_volume_details.return_value = volume
        self.mock_client.get_ec2_instance.return_value = instance
        
        parent, orphaned = self.resolver.resolve_ebs_parent(snapshot)
        
        assert orphaned is False
        assert parent == instance
        self.mock_client.get_volume_details.assert_called_once_with(
            'vol-1234567890abcdef0', None, None
        )
        self.mock_client.get_ec2_instance.assert_called_once_with(
            'i-1234567890abcdef0', None, None
        )
    
    def test_resolve_ebs_parent_missing_volume_id(self):
        """Test EBS parent resolution with missing volume_id."""
        snapshot = {
            'id': 'snap-1234567890abcdef0'
            # Missing volume_id
        }
        
        parent, orphaned = self.resolver.resolve_ebs_parent(snapshot)
        
        assert orphaned is True
        assert parent is None
        self.mock_client.get_volume_details.assert_not_called()
        self.mock_client.get_ec2_instance.assert_not_called()
    
    def test_resolve_ebs_parent_volume_not_found(self):
        """Test EBS parent resolution when volume is not found."""
        snapshot = {
            'id': 'snap-1234567890abcdef0',
            'volume_id': 'vol-1234567890abcdef0'
        }
        
        self.mock_client.get_volume_details.return_value = None
        
        parent, orphaned = self.resolver.resolve_ebs_parent(snapshot)
        
        assert orphaned is True
        assert parent is None
        self.mock_client.get_volume_details.assert_called_once()
        self.mock_client.get_ec2_instance.assert_not_called()
    
    def test_resolve_ebs_parent_missing_instance_id(self):
        """Test EBS parent resolution with missing instance_id in volume."""
        snapshot = {
            'id': 'snap-1234567890abcdef0',
            'volume_id': 'vol-1234567890abcdef0'
        }
        
        volume = {
            'id': 'vol-1234567890abcdef0'
            # Missing instance_id
        }
        
        self.mock_client.get_volume_details.return_value = volume
        
        parent, orphaned = self.resolver.resolve_ebs_parent(snapshot)
        
        assert orphaned is True
        assert parent is None
        self.mock_client.get_volume_details.assert_called_once()
        self.mock_client.get_ec2_instance.assert_not_called()
    
    def test_resolve_ebs_parent_instance_not_found(self):
        """Test EBS parent resolution when instance is not found."""
        snapshot = {
            'id': 'snap-1234567890abcdef0',
            'volume_id': 'vol-1234567890abcdef0'
        }
        
        volume = {
            'id': 'vol-1234567890abcdef0',
            'instance_id': 'i-1234567890abcdef0'
        }
        
        self.mock_client.get_volume_details.return_value = volume
        self.mock_client.get_ec2_instance.return_value = None
        
        parent, orphaned = self.resolver.resolve_ebs_parent(snapshot)
        
        assert orphaned is True
        assert parent is None
        self.mock_client.get_volume_details.assert_called_once()
        self.mock_client.get_ec2_instance.assert_called_once()
    
    def test_resolve_db_parent_success(self):
        """Test successful DB parent resolution."""
        snapshot = {
            'id': 'snap-1234567890abcdef0',
            'db_instance_identifier': 'my-db-instance'
        }
        
        instance = {
            'db_instance_identifier': 'my-db-instance',
            'db_instance_status': 'available'
        }
        
        self.mock_client.get_db_instance.return_value = instance
        
        parent, orphaned = self.resolver.resolve_db_parent(snapshot)
        
        assert orphaned is False
        assert parent == instance
        self.mock_client.get_db_instance.assert_called_once_with(
            'my-db-instance', None, None
        )
    
    def test_resolve_db_parent_missing_identifier(self):
        """Test DB parent resolution with missing db_instance_identifier."""
        snapshot = {
            'id': 'snap-1234567890abcdef0'
            # Missing db_instance_identifier
        }
        
        parent, orphaned = self.resolver.resolve_db_parent(snapshot)
        
        assert orphaned is True
        assert parent is None
        self.mock_client.get_db_instance.assert_not_called()
    
    def test_resolve_db_parent_instance_not_found(self):
        """Test DB parent resolution when instance is not found."""
        snapshot = {
            'id': 'snap-1234567890abcdef0',
            'db_instance_identifier': 'my-db-instance'
        }
        
        self.mock_client.get_db_instance.return_value = None
        
        parent, orphaned = self.resolver.resolve_db_parent(snapshot)
        
        assert orphaned is True
        assert parent is None
        self.mock_client.get_db_instance.assert_called_once()
    
    def test_resolve_parent_ebs_type(self):
        """Test parent resolution for EBS snapshot type."""
        snapshot = {'volume_id': 'vol-123'}
        volume = {'instance_id': 'i-123'}
        instance = {'instance_id': 'i-123'}
        
        self.mock_client.get_volume_details.return_value = volume
        self.mock_client.get_ec2_instance.return_value = instance
        
        parent, orphaned = self.resolver.resolve_parent(snapshot, 'ebs')
        
        assert orphaned is False
        assert parent == instance
    
    def test_resolve_parent_db_type(self):
        """Test parent resolution for DB snapshot type."""
        snapshot = {'db_instance_identifier': 'db-123'}
        instance = {'db_instance_identifier': 'db-123'}
        
        self.mock_client.get_db_instance.return_value = instance
        
        parent, orphaned = self.resolver.resolve_parent(snapshot, 'db')
        
        assert orphaned is False
        assert parent == instance
    
    def test_resolve_parent_unknown_type(self):
        """Test parent resolution for unknown snapshot type."""
        snapshot = {'id': 'snap-123'}
        
        parent, orphaned = self.resolver.resolve_parent(snapshot, 'unknown')
        
        assert orphaned is True
        assert parent is None
    
    def test_resolve_with_account_and_region(self):
        """Test parent resolution with account and region parameters."""
        snapshot = {
            'id': 'snap-1234567890abcdef0',
            'volume_id': 'vol-1234567890abcdef0'
        }
        
        volume = {
            'id': 'vol-1234567890abcdef0',
            'instance_id': 'i-1234567890abcdef0'
        }
        
        instance = {
            'instance_id': 'i-1234567890abcdef0',
            'state': {'name': 'running'}
        }
        
        self.mock_client.get_volume_details.return_value = volume
        self.mock_client.get_ec2_instance.return_value = instance
        
        parent, orphaned = self.resolver.resolve_ebs_parent(
            snapshot, '123456789012', 'us-east-1'
        )
        
        assert orphaned is False
        assert parent == instance
        self.mock_client.get_volume_details.assert_called_once_with(
            'vol-1234567890abcdef0', '123456789012', 'us-east-1'
        )
        self.mock_client.get_ec2_instance.assert_called_once_with(
            'i-1234567890abcdef0', '123456789012', 'us-east-1'
        )
