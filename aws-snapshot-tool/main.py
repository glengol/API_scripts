#!/usr/bin/env python3
"""
Volume Snapshot Tool - CLI for correlating EBS and RDS/DB snapshots to parent resources.
Uses only Firefly API as documented.
"""

import os
import sys
import logging
from pathlib import Path
from typing import List, Optional
import click
from tqdm import tqdm
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from firefly_client import FireflyClient
from resolver import ParentResolver
from normalize import DataNormalizer
from export import CSVExporter


def setup_logging(verbose: bool):
    """Setup logging configuration"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )


def get_credentials(access_key: Optional[str], secret_key: Optional[str]) -> tuple[str, str]:
    """Get Firefly API credentials from parameters or environment variables"""
    # Get access key
    if access_key:
        api_access_key = access_key
    else:
        api_access_key = os.environ.get('FIREFLY_ACCESS_KEY')
        if not api_access_key:
            raise click.ClickException(
                "Access key required. Set FIREFLY_ACCESS_KEY environment variable or use --firefly-access-key"
            )
    
    # Get secret key
    if secret_key:
        api_secret_key = secret_key
    else:
        api_secret_key = os.environ.get('FIREFLY_SECRET_KEY')
        if not api_secret_key:
            raise click.ClickException(
                "Secret key required. Set FIREFLY_SECRET_KEY environment variable or use --firefly-secret-key"
            )
    
    return api_access_key, api_secret_key


def collect_snapshots_parallel(client: FireflyClient, account_ids: List[str], regions: List[str] = None, since: Optional[str] = None):
    """
    Collect EBS and DB snapshots in parallel for better performance.
    """
    all_snapshots = []
    logger = logging.getLogger(__name__)
    
    def collect_ebs_snapshots(account_id, region):
        """Collect EBS snapshots for a specific account/region"""
        snapshots = []
        try:
            for snapshot in client.list_ebs_snapshots(account_id, region, since):
                snapshots.append(('ebs', snapshot, account_id, region))
        except Exception as e:
            logger.error(f"Error collecting EBS snapshots for account {account_id}, region {region}: {e}")
        return snapshots
    
    def collect_db_snapshots(account_id, region):
        """Collect DB snapshots for a specific account/region"""
        snapshots = []
        try:
            for snapshot in client.list_db_snapshots(account_id, region, since):
                snapshots.append(('db', snapshot, account_id, region))
        except Exception as e:
            logger.error(f"Error collecting DB snapshots for account {account_id}, region {region}: {e}")
        return snapshots
    
    # Create tasks for parallel execution
    tasks = []
    for account_id in account_ids or [None]:
        for region in regions or [None]:
            tasks.append((collect_ebs_snapshots, account_id, region))
            tasks.append((collect_db_snapshots, account_id, region))
    
    # Execute tasks in parallel with progress bar
    with ThreadPoolExecutor(max_workers=min(8, len(tasks))) as executor:
        # Submit all tasks
        future_to_task = {
            executor.submit(func, account_id, region): (func.__name__, account_id, region)
            for func, account_id, region in tasks
        }
        
        # Process results with progress bar
        with tqdm(total=len(tasks), desc="Collecting snapshots", unit="task") as pbar:
            for future in as_completed(future_to_task):
                task_name, account_id, region = future_to_task[future]
                try:
                    snapshots = future.result()
                    all_snapshots.extend(snapshots)
                    pbar.set_postfix({
                        'account': account_id or 'all',
                        'region': region or 'all',
                        'type': 'EBS' if 'ebs' in task_name else 'DB',
                        'count': len(snapshots)
                    })
                except Exception as e:
                    logger.error(f"Task {task_name} failed for account {account_id}, region {region}: {e}")
                finally:
                    pbar.update(1)
    
    return all_snapshots


def process_snapshots(client: FireflyClient, resolver: ParentResolver, normalizer: DataNormalizer,
                     account_ids: List[str], regions: List[str] = None, since: Optional[str] = None, orphaned_only: bool = False, parent_only: bool = False):
    """
    Process snapshots with optimized batch processing and progress bars.
    """
    logger = logging.getLogger(__name__)
    
    # Collect all snapshots with progress bar
    logger.info("Starting snapshot collection...")
    all_snapshots = collect_snapshots_parallel(client, account_ids, regions, since)
    logger.info(f"Collected {len(all_snapshots)} total snapshots for processing")
    
    if not all_snapshots:
        logger.warning("No snapshots found to process")
        return
    
    # Group snapshots by type for batch processing
    ebs_snapshots = [(s, a, r) for t, s, a, r in all_snapshots if t == 'ebs']
    db_snapshots = [(s, a, r) for t, s, a, r in all_snapshots if t == 'db']
    
    # Batch resolve EBS parents with progress bar
    ebs_parents = {}
    if ebs_snapshots:
        logger.info(f"Batch resolving parents for {len(ebs_snapshots)} EBS snapshots...")
        # Group by account/region for batch processing
        ebs_by_account_region = {}
        for snapshot, account_id, region in ebs_snapshots:
            key = (account_id, region)
            if key not in ebs_by_account_region:
                ebs_by_account_region[key] = []
            ebs_by_account_region[key].append(snapshot)
        
        # Batch resolve for each account/region combination with progress bar
        with tqdm(total=len(ebs_by_account_region), desc="Resolving EBS parents", unit="batch") as pbar:
            for (account_id, region), snapshots in ebs_by_account_region.items():
                try:
                    batch_results = resolver.resolve_ebs_parents_batch(snapshots, account_id, region)
                    ebs_parents.update(batch_results)
                    pbar.set_postfix({
                        'account': account_id or 'all',
                        'region': region or 'all',
                        'snapshots': len(snapshots)
                    })
                except Exception as e:
                    logger.error(f"Error batch resolving EBS parents for account {account_id}, region {region}: {e}")
                finally:
                    pbar.update(1)
    
    # Process and yield snapshots with progress bar
    processed_count = 0
    with tqdm(total=len(all_snapshots), desc="Processing snapshots", unit="snapshot") as pbar:
        for snapshot_type, snapshot, account_id, region in all_snapshots:
            try:
                # Resolve parent based on type
                if snapshot_type == 'ebs':
                    parent, orphaned = ebs_parents.get(snapshot.get('resourceId'), (None, True))
                else:  # db
                    parent, orphaned = resolver.resolve_db_parent(snapshot, account_id, region)
                
                # Apply filters if specified
                if orphaned_only and not orphaned:
                    pbar.update(1)
                    continue  # Skip non-orphaned snapshots
                if parent_only and orphaned:
                    pbar.update(1)
                    continue  # Skip orphaned snapshots
                
                # Normalize data
                normalized = normalizer.normalize_snapshot_data(
                    snapshot, snapshot_type, parent, orphaned
                )
                
                processed_count += 1
                pbar.set_postfix({
                    'processed': processed_count,
                    'type': snapshot_type.upper(),
                    'orphaned': 'yes' if orphaned else 'no'
                })
                
                yield normalized
                
            except Exception as e:
                logger.error(f"Error processing {snapshot_type} snapshot {snapshot.get('resourceId', 'unknown')}: {e}")
            finally:
                pbar.update(1)


@click.command()
@click.option('--firefly-base-url', 
              default='https://api.firefly.ai',
              help='Firefly API base URL (default: https://api.firefly.ai)')
@click.option('--firefly-access-key', 
              help='Firefly API access key (or set FIREFLY_ACCESS_KEY env var)')
@click.option('--firefly-secret-key', 
              help='Firefly API secret key (or set FIREFLY_SECRET_KEY env var)')
@click.option('--account-id', multiple=True, 
              help='Account ID filter (can be specified multiple times)')
@click.option('--out', 
              help='Output file path (default: reports/snapshot-report-{YYYYMMDD-HHMMSS}.csv)')
@click.option('--orphaned-only', is_flag=True,
              help='Show only orphaned snapshots (no parent resource found)')
@click.option('--parent-only', is_flag=True,
              help='Show only snapshots with parent resources (exclude orphaned)')
@click.option('--verbose', is_flag=True,
              help='Enable verbose logging')
@click.option('--format', 'output_format', 
              type=click.Choice(['csv', 'html', 'both']), 
              default='csv',
              help='Output format: csv, html, or both (default: csv)')
def main(firefly_base_url: str, firefly_access_key: Optional[str],
         firefly_secret_key: Optional[str], account_id: List[str],
         out: str, orphaned_only: bool, parent_only: bool, verbose: bool, output_format: str):
    """
    Volume Snapshot Tool - Correlate EBS and RDS/DB snapshots to parent resources.
    
    This tool uses only the Firefly API as documented to generate a CSV report
    correlating snapshots to their parent resources.
    """
    # Setup logging
    setup_logging(verbose)
    logger = logging.getLogger(__name__)
    
    # Set default output path if not provided
    if not out:
        from datetime import datetime
        now = datetime.now().strftime('%Y%m%d-%H%M%S')
        out = f"reports/snapshot-report-{now}.csv"
        logger.info(f"No output path specified, using default: {out}")
    
    logger.info("Starting Volume Snapshot Tool")
    logger.info(f"Firefly API URL: {firefly_base_url}")
    logger.info(f"Output file: {out}")
    if account_id:
        logger.info(f"Account IDs: {', '.join(account_id)}")
    
    # Validate filter options
    if orphaned_only and parent_only:
        raise click.ClickException("Cannot use both --orphaned-only and --parent-only at the same time")
    
    if orphaned_only:
        logger.info("Filtering: Orphaned snapshots only")
    elif parent_only:
        logger.info("Filtering: Snapshots with parent resources only")
    else:
        logger.info("Filtering: All snapshots")
    
    try:
        # Get Firefly API credentials
        access_key, secret_key = get_credentials(firefly_access_key, firefly_secret_key)
        
        # Initialize components
        client = FireflyClient(firefly_base_url, access_key, secret_key)
        resolver = ParentResolver(client)
        
        # Initialize pricing fetcher for cost calculations
        from aws_pricing import AWSPricingFetcher
        pricing_fetcher = AWSPricingFetcher()
        logger.info("Cost calculations enabled - using snapshot-prices.json")
        
        normalizer = DataNormalizer(pricing_fetcher=pricing_fetcher)
        
        # Initialize exporters based on format
        csv_exporter = None
        html_generator = None
        
        if output_format in ['csv', 'both']:
            csv_exporter = CSVExporter(out)
            logger.info(f"CSV export enabled: {out}")
        
        if output_format in ['html', 'both']:
            from html_report import HTMLReportGenerator
            # Ensure the output directory exists
            output_dir = Path(out).parent
            output_dir.mkdir(parents=True, exist_ok=True)
            html_generator = HTMLReportGenerator(output_dir)
            logger.info(f"HTML report generation enabled")
        
        # Process snapshots with timing
        import time
        start_time = time.time()
        
        logger.info("Starting snapshot processing...")
        snapshots = process_snapshots(client, resolver, normalizer, account_id, None, None, orphaned_only, parent_only)
        
        processing_time = time.time() - start_time
        logger.info(f"Snapshot processing completed in {processing_time:.2f} seconds")
        
        # Export based on format with progress bars
        if csv_exporter and html_generator:
            # Both formats needed - convert to list first to avoid consuming iterator
            logger.info("Converting snapshots to list for dual export...")
            snapshots_list = list(tqdm(snapshots, desc="Converting to list", unit="snapshot"))
            
            # CSV export
            csv_start = time.time()
            logger.info("Starting CSV export...")
            csv_exporter.export_snapshots(snapshots_list)
            csv_time = time.time() - csv_start
            logger.info(f"CSV export completed in {csv_time:.2f} seconds")
            
            # HTML export
            html_start = time.time()
            logger.info("Starting HTML report generation...")
            html_filename = Path(out).stem + ".html"
            html_generator.generate_report(snapshots_list, html_filename)
            html_time = time.time() - html_start
            logger.info(f"HTML report generation completed in {html_time:.2f} seconds")
            
        elif csv_exporter:
            # CSV only
            csv_start = time.time()
            logger.info("Starting CSV export...")
            csv_exporter.export_snapshots(snapshots)
            csv_time = time.time() - csv_start
            logger.info(f"CSV export completed in {csv_time:.2f} seconds")
            
        elif html_generator:
            # HTML only
            html_start = time.time()
            logger.info("Converting snapshots to list for HTML export...")
            snapshots_list = list(tqdm(snapshots, desc="Converting to list", unit="snapshot"))
            logger.info("Starting HTML report generation...")
            html_filename = Path(out).stem + ".html"
            html_generator.generate_report(snapshots_list, html_filename)
            html_time = time.time() - html_start
            logger.info(f"HTML report generation completed in {html_time:.2f} seconds")
        
        total_time = time.time() - start_time
        logger.info(f"Volume Snapshot Tool completed successfully in {total_time:.2f} seconds")
        
    except Exception as e:
        logger.error(f"Tool failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
