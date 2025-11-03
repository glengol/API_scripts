#!/usr/bin/env python3
"""
Simple AWS snapshot pricing fetcher using local JSON file.
This provides a lightweight way to get EBS and RDS snapshot pricing per region.
"""

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class AWSPricingFetcher:
    def __init__(self, cache_dir: str = "./aws"):
        self.cache_dir = Path(cache_dir)
        self.pricing_file = self.cache_dir / "snapshot-prices.json"
        self.pricing_data = None
        
    def ensure_pricing_loaded(self):
        """Ensure pricing data is loaded from the JSON file."""
        if self.pricing_data is None:
            self._load_pricing_data()
    
    def _load_pricing_data(self):
        """Load pricing data from the local JSON file."""
        if not self.pricing_file.exists():
            logger.warning(f"Pricing file not found: {self.pricing_file}")
            self.pricing_data = {}
            return
        
        try:
            with open(self.pricing_file, 'r') as f:
                self.pricing_data = json.load(f)
            logger.info(f"Loaded pricing data from {self.pricing_file}")
            logger.info(f"Available regions: {len(self.pricing_data.get('regions', {}))}")
        except Exception as e:
            logger.error(f"Error loading pricing data: {e}")
            self.pricing_data = {}
    
    def get_ebs_price(self, region: str, storage_tier: Optional[str] = None) -> Optional[float]:
        """Get EBS snapshot price for a region.
        
        Args:
            region: AWS region code
            storage_tier: Storage tier ('standard' or 'archive'). If None or 'standard', 
                        returns standard price. If 'archive', returns archive price.
        
        Returns:
            Price per GB per month, or None if not available
        """
        self.ensure_pricing_loaded()
        
        region_data = self.pricing_data.get('regions', {}).get(region, {})
        
        # For archive tier, use archive pricing
        if storage_tier == 'archive':
            return region_data.get('ebs_snapshot_archive_gb_month')
        
        # For standard tier or None, use standard pricing
        return region_data.get('ebs_snapshot_gb_month')
    
    def get_rds_price(self, region: str) -> Optional[float]:
        """Get RDS snapshot price for a region."""
        self.ensure_pricing_loaded()
        
        region_data = self.pricing_data.get('regions', {}).get(region, {})
        return region_data.get('rds_snapshot_gb_month')
    
    def calculate_monthly_cost(self, size_gb: float, region: str, snapshot_type: str, 
                              storage_tier: Optional[str] = None) -> Optional[float]:
        """Calculate monthly cost for a snapshot.
        
        Args:
            size_gb: Snapshot size in gigabytes
            region: AWS region code
            snapshot_type: Type of snapshot ('ebs' or 'db')
            storage_tier: Storage tier for EBS snapshots ('standard' or 'archive'). 
                         Ignored for DB snapshots.
        
        Returns:
            Monthly cost in USD, or None if pricing not available
        """
        if snapshot_type == 'ebs':
            price = self.get_ebs_price(region, storage_tier)
        elif snapshot_type == 'db':
            price = self.get_rds_price(region)
        else:
            return None
        
        if price is None:
            return None
        
        return size_gb * price
    
    def calculate_cost_since_creation(self, size_gb: float, region: str, snapshot_type: str, 
                                     age_days: int, storage_tier: Optional[str] = None) -> Optional[float]:
        """Calculate total cost since creation.
        
        Args:
            size_gb: Snapshot size in gigabytes
            region: AWS region code
            snapshot_type: Type of snapshot ('ebs' or 'db')
            age_days: Age of snapshot in days
            storage_tier: Storage tier for EBS snapshots ('standard' or 'archive'). 
                         Ignored for DB snapshots.
        
        Returns:
            Total cost in USD since creation, or None if pricing not available
        """
        monthly_cost = self.calculate_monthly_cost(size_gb, region, snapshot_type, storage_tier)
        if monthly_cost is None:
            return None
        
        # Convert days to months (approximate)
        months = age_days / 30.44  # Average days per month
        return monthly_cost * months
    
    def print_pricing_table(self):
        """Print a formatted table of all snapshot prices."""
        self.ensure_pricing_loaded()
        
        if not self.pricing_data.get('regions'):
            print("No pricing data available")
            return
        
        print(f"AWS Snapshot Pricing (Generated: {self.pricing_data.get('generated_at', 'Unknown')})")
        print(f"Currency: {self.pricing_data.get('currency', 'USD')}")
        print("-" * 100)
        print(f"{'Region':<15} {'EBS Standard':<15} {'EBS Archive':<15} {'RDS Snapshot':<15}")
        print("-" * 100)
        
        regions = sorted(self.pricing_data['regions'].keys())
        for region in regions:
            region_data = self.pricing_data['regions'][region]
            ebs_price = region_data.get('ebs_snapshot_gb_month', 'N/A')
            ebs_archive_price = region_data.get('ebs_snapshot_archive_gb_month', 'N/A')
            rds_price = region_data.get('rds_snapshot_gb_month', 'N/A')
            
            if isinstance(ebs_price, (int, float)):
                ebs_price = f"${ebs_price:.4f}"
            if isinstance(ebs_archive_price, (int, float)):
                ebs_archive_price = f"${ebs_archive_price:.4f}"
            if isinstance(rds_price, (int, float)):
                rds_price = f"${rds_price:.4f}"
            
            print(f"{region:<15} {ebs_price:<15} {ebs_archive_price:<15} {rds_price:<15}")

def print_pricing_table():
    """Standalone function to print pricing table."""
    fetcher = AWSPricingFetcher()
    fetcher.print_pricing_table()

if __name__ == "__main__":
    print_pricing_table()
