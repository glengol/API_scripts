"""
Unit tests for the export module.
"""

import pytest
import tempfile
import os
from export import CSVExporter


class TestCSVExporter:
    """Test cases for CSVExporter class."""
    
    def setup_method(self):
        """Setup test fixtures."""
        self.temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv')
        self.temp_file.close()
        self.exporter = CSVExporter(self.temp_file.name)
    
    def teardown_method(self):
        """Cleanup test fixtures."""
        if os.path.exists(self.temp_file.name):
            os.unlink(self.temp_file.name)
    
    def test_csv_header_format(self):
        """Test CSV header has exact format and order."""
        expected_header = [
            'snapshot_id',
            'snapshot_type',
            'creation_date',
            'size_gb',
            'parent_resource_type',
            'parent_resource_id',
            'parent_name',
            'parent_state',
            'account_id',
            'environment',
            'region',
            'orphaned',
            'age_days'
        ]
        
        assert self.exporter.CSV_HEADER == expected_header
    
    def test_write_header(self):
        """Test CSV header writing."""
        with open(self.temp_file.name, 'r') as f:
            content = f.read()
            assert content == ''
        
        with open(self.temp_file.name, 'w') as f:
            self.exporter.write_header(f)
        
        with open(self.temp_file.name, 'r') as f:
            content = f.read()
            expected = 'snapshot_id,snapshot_type,creation_date,size_gb,parent_resource_type,parent_resource_id,parent_name,parent_state,account_id,environment,region,orphaned,age_days\n'
            assert content == expected
    
    def test_write_row(self):
        """Test CSV row writing."""
        data = {
            'snapshot_id': 'snap-1234567890abcdef0',
            'snapshot_type': 'ebs',
            'creation_date': '2024-01-15T10:30:00Z',
            'size_gb': '100',
            'parent_resource_type': 'ec2_instance',
            'parent_resource_id': 'i-1234567890abcdef0',
            'parent_name': 'web-server-01',
            'parent_state': 'running',
            'account_id': '123456789012',
            'environment': 'prod',
            'region': 'us-east-1',
            'orphaned': False,
            'age_days': 5
        }
        
        with open(self.temp_file.name, 'w') as f:
            self.exporter.write_header(f)
            self.exporter.write_row(f, data)
        
        with open(self.temp_file.name, 'r') as f:
            lines = f.readlines()
            assert len(lines) == 2
            assert lines[0].strip() == ','.join(self.exporter.CSV_HEADER)
            assert 'snap-1234567890abcdef0' in lines[1]
            assert 'ebs' in lines[1]
            assert '100' in lines[1]
    
    def test_write_row_missing_fields(self):
        """Test CSV row writing with missing fields."""
        data = {
            'snapshot_id': 'snap-1234567890abcdef0',
            'snapshot_type': 'ebs'
            # Missing other fields
        }
        
        with open(self.temp_file.name, 'w') as f:
            self.exporter.write_header(f)
            self.exporter.write_row(f, data)
        
        with open(self.temp_file.name, 'r') as f:
            lines = f.readlines()
            assert len(lines) == 2
            # Check that missing fields are empty
            row_parts = lines[1].strip().split(',')
            assert row_parts[0] == 'snap-1234567890abcdef0'  # snapshot_id
            assert row_parts[1] == 'ebs'  # snapshot_type
            assert row_parts[2] == ''  # creation_date (missing)
            assert row_parts[3] == ''  # size_gb (missing)
    
    def test_export_snapshots_streaming(self):
        """Test streaming CSV export."""
        snapshots = [
            {
                'snapshot_id': 'snap-1',
                'snapshot_type': 'ebs',
                'creation_date': '2024-01-15T10:30:00Z',
                'size_gb': '100',
                'parent_resource_type': 'ec2_instance',
                'parent_resource_id': 'i-1',
                'parent_name': 'server-1',
                'parent_state': 'running',
                'account_id': '123456789012',
                'environment': 'prod',
                'region': 'us-east-1',
                'orphaned': False,
                'age_days': 5
            },
            {
                'snapshot_id': 'snap-2',
                'snapshot_type': 'db',
                'creation_date': '2024-01-16T10:30:00Z',
                'size_gb': '200',
                'parent_resource_type': 'db_instance',
                'parent_resource_id': 'db-1',
                'parent_name': 'database-1',
                'parent_state': 'available',
                'account_id': '123456789012',
                'environment': 'staging',
                'region': 'us-west-2',
                'orphaned': False,
                'age_days': 4
            }
        ]
        
        self.exporter.export_snapshots(iter(snapshots))
        
        with open(self.temp_file.name, 'r') as f:
            lines = f.readlines()
            assert len(lines) == 3  # Header + 2 data rows
            
            # Check header
            assert lines[0].strip() == ','.join(self.exporter.CSV_HEADER)
            
            # Check first row
            assert 'snap-1' in lines[1]
            assert 'ebs' in lines[1]
            assert '100' in lines[1]
            assert 'prod' in lines[1]
            
            # Check second row
            assert 'snap-2' in lines[2]
            assert 'db' in lines[2]
            assert '200' in lines[2]
            assert 'staging' in lines[2]
    
    def test_export_to_string(self):
        """Test CSV export to string."""
        snapshots = [
            {
                'snapshot_id': 'snap-1',
                'snapshot_type': 'ebs',
                'creation_date': '2024-01-15T10:30:00Z',
                'size_gb': '100',
                'parent_resource_type': 'ec2_instance',
                'parent_resource_id': 'i-1',
                'parent_name': 'server-1',
                'parent_state': 'running',
                'account_id': '123456789012',
                'environment': 'prod',
                'region': 'us-east-1',
                'orphaned': False,
                'age_days': 5
            }
        ]
        
        result = self.exporter.export_to_string(iter(snapshots))
        
        assert 'snapshot_id,snapshot_type,creation_date,size_gb' in result
        assert 'snap-1,ebs,2024-01-15T10:30:00Z,100' in result
        assert 'prod' in result
    
    def test_export_empty_snapshots(self):
        """Test CSV export with no snapshots."""
        empty_snapshots = iter([])
        
        self.exporter.export_snapshots(empty_snapshots)
        
        with open(self.temp_file.name, 'r') as f:
            lines = f.readlines()
            assert len(lines) == 1  # Only header
            assert lines[0].strip() == ','.join(self.exporter.CSV_HEADER)
    
    def test_csv_encoding(self):
        """Test CSV encoding and special characters."""
        data = {
            'snapshot_id': 'snap-123',
            'snapshot_type': 'ebs',
            'creation_date': '2024-01-15T10:30:00Z',
            'size_gb': '100',
            'parent_resource_type': 'ec2_instance',
            'parent_resource_id': 'i-123',
            'parent_name': 'server with spaces & special chars',
            'parent_state': 'running',
            'account_id': '123456789012',
            'environment': 'prod',
            'region': 'us-east-1',
            'orphaned': False,
            'age_days': 5
        }
        
        with open(self.temp_file.name, 'w') as f:
            self.exporter.write_header(f)
            self.exporter.write_row(f, data)
        
        with open(self.temp_file.name, 'r') as f:
            content = f.read()
            assert 'server with spaces & special chars' in content
