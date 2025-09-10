#!/usr/bin/env python3
"""
Performance Test Script - Demonstrates the performance improvements
from batch processing and caching optimizations.
"""

import time
import logging
from firefly_client import FireflyClient
from resolver import ParentResolver

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_individual_lookup(client, resolver, snapshots, account_id=None, region=None):
    """Test individual lookup performance (old method)"""
    logger.info("Testing individual lookup performance...")
    start_time = time.time()
    
    results = []
    for snapshot in snapshots:
        parent, orphaned = resolver.resolve_ebs_parent(snapshot, account_id, region)
        results.append((parent, orphaned))
    
    elapsed = time.time() - start_time
    logger.info(f"Individual lookup: {len(snapshots)} snapshots in {elapsed:.2f}s ({elapsed/len(snapshots):.3f}s per snapshot)")
    return results, elapsed

def test_batch_lookup(client, resolver, snapshots, account_id=None, region=None):
    """Test batch lookup performance (new method)"""
    logger.info("Testing batch lookup performance...")
    start_time = time.time()
    
    results = resolver.resolve_ebs_parents_batch(snapshots, account_id, region)
    
    elapsed = time.time() - start_time
    logger.info(f"Batch lookup: {len(snapshots)} snapshots in {elapsed:.2f}s ({elapsed/len(snapshots):.3f}s per snapshot)")
    return results, elapsed

def main():
    """Run performance comparison tests"""
    logger.info("Starting Performance Test")
    
    # You'll need to set these environment variables or modify the script
    import os
    base_url = os.getenv('FIREFLY_BASE_URL', 'https://api.firefly.ai')
    access_key = os.getenv('FIREFLY_ACCESS_KEY')
    secret_key = os.getenv('FIREFLY_SECRET_KEY')
    
    if not access_key or not secret_key:
        logger.error("Please set FIREFLY_ACCESS_KEY and FIREFLY_SECRET_KEY environment variables")
        return
    
    try:
        # Initialize client
        client = FireflyClient(base_url, access_key, secret_key)
        resolver = ParentResolver(client)
        
        # Get a sample of EBS snapshots for testing
        logger.info("Fetching sample EBS snapshots for testing...")
        snapshots = list(client.list_ebs_snapshots())
        
        if not snapshots:
            logger.warning("No snapshots found for testing")
            return
        
        # Limit to first 10 for testing
        test_snapshots = snapshots[:10]
        logger.info(f"Testing with {len(test_snapshots)} snapshots")
        
        # Test individual lookup
        individual_results, individual_time = test_individual_lookup(
            client, resolver, test_snapshots
        )
        
        # Test batch lookup
        batch_results, batch_time = test_batch_lookup(
            client, resolver, test_snapshots
        )
        
        # Calculate improvement
        if individual_time > 0:
            improvement = ((individual_time - batch_time) / individual_time) * 100
            logger.info(f"Performance improvement: {improvement:.1f}%")
            logger.info(f"Speedup: {individual_time/batch_time:.1f}x faster")
        
        # Verify results match
        individual_orphaned = sum(1 for _, orphaned in individual_results if orphaned)
        batch_orphaned = sum(1 for _, orphaned in batch_results.values() if orphaned)
        
        logger.info(f"Individual lookup orphaned count: {individual_orphaned}")
        logger.info(f"Batch lookup orphaned count: {batch_orphaned}")
        
        if individual_orphaned == batch_orphaned:
            logger.info("✅ Results match between individual and batch lookup")
        else:
            logger.warning("⚠️  Results differ between individual and batch lookup")
            
    except Exception as e:
        logger.error(f"Performance test failed: {e}")

if __name__ == '__main__':
    main()
