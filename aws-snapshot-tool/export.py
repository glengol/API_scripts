"""
CSV Export - Streaming CSV writer with the exact header format.
"""

import csv
import logging
from typing import Dict, Any, Iterator, TextIO, List
from io import StringIO
from tqdm import tqdm

logger = logging.getLogger(__name__)


class CSVExporter:
    """
    Exports snapshot data to CSV with exact header format and streaming support.
    """
    
    # Base header order as specified in requirements
    BASE_HEADER = [
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
    
    # Cost columns to add when costs are enabled
    COST_COLUMNS = ['monthly_cost', 'cost_since_creation']
    
    def __init__(self, output_file: str, include_costs: bool = True):
        self.output_file = output_file
        self.include_costs = include_costs
        # Build header dynamically based on costs flag
        self.CSV_HEADER = self.BASE_HEADER + (self.COST_COLUMNS if include_costs else [])
    
    def write_header(self, file_handle: TextIO):
        """Write CSV header to file"""
        writer = csv.writer(file_handle)
        writer.writerow(self.CSV_HEADER)
        logger.info("CSV header written")
    
    def write_row(self, file_handle: TextIO, data: Dict[str, Any]):
        """Write a single row to CSV"""
        writer = csv.writer(file_handle)
        row = [data.get(field, '') for field in self.CSV_HEADER]
        writer.writerow(row)
    
    def export_snapshots(self, snapshots):
        """
        Export snapshots to CSV file with streaming support and progress bar.
        """
        logger.info(f"Starting CSV export to {self.output_file}")
        
        # Handle both iterators and lists
        if isinstance(snapshots, list):
            total = len(snapshots)
            snapshots_iter = snapshots
        else:
            # For iterators, we need to count as we go
            snapshots_iter = snapshots
            total = None
        
        with open(self.output_file, 'w', newline='', encoding='utf-8') as csvfile:
            # Write header
            self.write_header(csvfile)
            
            # Stream rows with progress bar
            row_count = 0
            with tqdm(total=total, desc="Exporting CSV", unit="row", disable=total is None) as pbar:
                for snapshot in snapshots_iter:
                    self.write_row(csvfile, snapshot)
                    row_count += 1
                    
                    if pbar:
                        pbar.update(1)
                        pbar.set_postfix({'rows': row_count})
                    elif row_count % 100 == 0:
                        logger.info(f"Exported {row_count} snapshots...")
            
            logger.info(f"CSV export completed. Total rows: {row_count}")
    
    def export_to_string(self, snapshots: Iterator[Dict[str, Any]]) -> str:
        """
        Export snapshots to string (useful for testing).
        """
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(self.CSV_HEADER)
        
        # Write rows
        for snapshot in snapshots:
            row = [snapshot.get(field, '') for field in self.CSV_HEADER]
            writer.writerow(row)
        
        return output.getvalue()
