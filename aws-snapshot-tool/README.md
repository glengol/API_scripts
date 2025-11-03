# Volume Snapshot Tool

A high-performance CLI tool that correlates EBS and RDS/DB snapshots to their parent resources using the Firefly API. This tool generates comprehensive CSV and HTML reports showing the relationship between snapshots and their parent EC2 instances or database instances, with cost analysis and performance optimizations.

## ⚠️ Important Note

**This tool exclusively uses the Firefly API as documented. It does not access AWS APIs/SDKs directly or use any external web sources. All endpoints, schemas, and fields must be defined in the Firefly API documentation.**

## 🚀 Features

- **EBS Snapshot Correlation**: Links EBS snapshots to their parent EC2 instances via volume relationships
- **DB Snapshot Correlation**: Links database snapshots to their parent database instances
- **Comprehensive Reporting**: Generates CSV and HTML reports with detailed snapshot and parent resource information
- **Cost Analysis**: Calculates monthly costs and total costs since creation using AWS pricing data
- **Orphan Detection**: Identifies snapshots without resolvable parent resources
- **Environment Tagging**: Extracts environment information from resource tags
- **Performance Optimized**: Uses batch processing for 20x+ performance improvement
- **Multiple Output Formats**: CSV (default), HTML, or both formats
- **Simplified CLI**: Clean interface focused on account-based filtering
- **Robust Error Handling**: Comprehensive logging and retry mechanisms

## 📊 CSV Output Format

The tool generates a CSV with the exact header order:

| Field | Description | Example |
|-------|-------------|---------|
| `snapshot_id` | Unique snapshot identifier | `snap-1234567890abcdef0` |
| `snapshot_type` | Type of snapshot | `ebs` or `db` |
| `creation_date` | ISO 8601 UTC creation timestamp | `2024-01-15T10:30:00Z` |
| `size_gb` | Snapshot size in gigabytes | `100` |
| `parent_resource_type` | Type of parent resource | `ec2_instance` or `db_instance` |
| `parent_resource_id` | Parent resource identifier | `i-1234567890abcdef0` |
| `parent_name` | Parent resource name/tag | `web-server-01` |
| `parent_state` | Current state of parent resource | `running` or `available` |
| `account_id` | AWS account identifier | `123456789012` |
| `environment` | Environment from tags | `prod`, `staging`, `dev` |
| `region` | AWS region | `us-east-1` |
| `orphaned` | Whether parent is resolvable | `true` or `false` |
| `age_days` | Age of snapshot in days | `5` |
| `monthly_cost` | Monthly cost in USD | `2.50` |
| `cost_since_creation` | Total cost since creation | `12.50` |

## 📁 Output File Naming

The tool now uses a timestamp-based naming pattern for unique identification:

- **Default Pattern**: `reports/snapshot-report-{YYYYMMDD-HHMMSS}.csv`
- **Example**: `reports/snapshot-report-20250904-131724.csv`
- **Benefits**: No filename conflicts, chronological sorting, audit trail

## Prerequisites

- Python 3.10 or higher
- Firefly API access and authentication token
- Firefly API documentation for endpoint specifications
- AWS CLI (for pricing updates - optional)

## Quick Start

1. **Clone and install** (If shared via git repository url):
```bash
git clone <repository-url>
cd volume-snapshot-tool
pip install -r requirements.txt
```

2. **Set your credentials**:
```bash
export FIREFLY_ACCESS_KEY="your-access-key"
export FIREFLY_SECRET_KEY="your-secret-key"
```
or send as params 
```bash  
  --firefly-access-key "your-access-key" \
  --firefly-secret-key "your-secret-key" \
```


3. **Run your first report**:
```bash
python3 main.py --format both
```

or 

```bash
python3 main.py --format both \
  --firefly-access-key "your-access-key" \
  --firefly-secret-key "your-secret-key" \
```



## Configuration

### Environment Variables

- `FIREFLY_ACCESS_KEY`: Your Firefly API access key
- `FIREFLY_SECRET_KEY`: Your Firefly API secret key

### AWS Pricing Data

The tool includes cost calculations based on AWS snapshot pricing. To update pricing data:

```bash
# Make the script executable
chmod +x fetch-snapshot-prices.sh

# Run with default AWS profile
./fetch-snapshot-prices.sh

# Or specify a specific AWS profile
./fetch-snapshot-prices.sh --profile production
```

**Requirements for pricing updates:**
- AWS CLI installed and configured
- Appropriate AWS permissions for pricing API access
- Authentication via AWS credentials or profile

**Output**: Creates `./aws/snapshot-prices.json` with current pricing data

The pricing file includes:
- **EBS Standard Tier** (`ebs_snapshot_gb_month`): From `EBS:SnapshotUsage` pricing
- **EBS Archive Tier** (`ebs_snapshot_archive_gb_month`): From `EBS:SnapshotArchiveStorage` pricing
- **RDS Snapshots** (`rds_snapshot_gb_month`): From `:ChargedBackupUsage` pricing

## Usage

### Command Line Options

> **Note**: The CLI interface has been simplified to focus on account-based filtering. Region and date filtering options have been removed to streamline the interface while maintaining full functionality.

| Option | Description | Required | Default |
|--------|-------------|----------|---------|
| `--firefly-base-url` | Firefly API base URL | No | `https://api.firefly.ai` |
| `--firefly-access-key` | API access key (or set env var) | No* | `FIREFLY_ACCESS_KEY` |
| `--firefly-secret-key` | API secret key (or set env var) | No* | `FIREFLY_SECRET_KEY` |
| `--account-id` | Filter by account ID (repeatable) | No | All accounts |
| `--out` | Output file path | No | `reports/snapshot-report-{YYYYMMDD-HHMMSS}.csv` |
| `--format` | Output format: csv, html, or both | No | `csv` |
| `--orphaned-only` | Show only orphaned snapshots | No | All snapshots |
| `--parent-only` | Show only snapshots with parents | No | All snapshots |
| `--verbose` | Enable verbose logging | No | False |

*Required if corresponding environment variables are not set.

### Basic Usage

Generate a complete snapshot report for all accounts:

```bash
python3 main.py
```

### Output Format Options

#### Both CSV and HTML
```bash
python3 main.py --format both --out "reports/snapshot_report"
```

#### CSV Only (Default)
```bash
python3 main.py --format csv --out "snapshot_report.csv"
```

#### HTML Only
```bash
python3 main.py --format html --out "reports/snapshot_report"
```

### Filtering Options

#### Show Only Orphaned Snapshots
Generate a report containing only snapshots without resolvable parent resources:

```bash
python3 main.py --orphaned-only --out "orphaned_snapshots.csv"
```

**Use Case**: Identify snapshots that might be candidates for cleanup or require investigation.

#### Show Only Snapshots with Parent Resources
Generate a report containing only snapshots that have successfully resolved parent resources:

```bash
python3 main.py --parent-only --out "parented_snapshots.csv"
```

**Use Case**: Focus on snapshots with complete relationship data for operational monitoring.

### Advanced Usage

#### Filter by Account
Generate a report for specific AWS accounts:

```bash
python3 main.py \
  --account-id "123456789012" \
  --account-id "098765432109" \
  --out "filtered_report.csv"
```

#### Filter by Orphaned Status
Generate a report showing only orphaned snapshots:

```bash
python3 main.py \
  --account-id "123456789012" \
  --orphaned-only \
  --out "orphaned_snapshots.csv"
```

#### Verbose Logging
Enable detailed logging for debugging and monitoring:

```bash
python3 main.py --verbose --out "detailed_report.csv"
```



### Environment Variables

You can also use environment variables instead of command-line arguments:

```bash
export FIREFLY_ACCESS_KEY="your-access-key"
export FIREFLY_SECRET_KEY="your-secret-key"

python3 main.py --out "snapshot_report.csv"
```

### Common Use Cases

#### Security Audit
```bash
python3 main.py --orphaned-only --out "security_audit_orphaned.csv"
```

#### Cost Optimization
```bash
python3 main.py --orphaned-only --out "cost_optimization_orphaned.csv"
```

#### Compliance Reporting
```bash
python3 main.py --account-id "123456789012" --parent-only --out "compliance_report.csv"
```

#### HTML Report Generation
```bash
python3 main.py --format html --out "reports/quarterly_report"
```

## HTML Report Features

When using `--format html` or `--format both`, the tool generates interactive HTML reports with:

- **Overview Dashboard**: Total snapshots, orphaned count, cost metrics
- **Interactive Tables**: Sortable and filterable data tables using DataTables.js
  - **Cost Savings Opportunities Table**: Shows orphaned snapshots with storage tier information
  - **Detailed Snapshot Data Table**: Complete snapshot information including storage tier for EBS snapshots
- **Storage Tier Display**: Visual badges showing storage tier (Standard/Archive) for EBS snapshots
- **Visual Charts**: Bar charts, pie charts, and histograms using Chart.js
- **Cost Analysis**: Orphaned snapshot cost savings opportunities with tier-appropriate pricing
- **Modern UI**: Bootstrap 5 styling with responsive design

## CSV Output Format

The tool generates a CSV file with the following columns in exact order:

| Column | Description | Example |
|--------|-------------|---------|
| `snapshot_id` | Unique snapshot identifier | `snap-0ec7ddeb6be4ede7a` |
| `snapshot_type` | Type of snapshot | `ebs` or `db` |
| `creation_date` | ISO 8601 UTC timestamp | `2024-09-02T13:26:17+00:00` |
| `size_gb` | Size in gigabytes | `15` |
| `parent_resource_type` | Type of parent resource | `ec2_instance` or `db_instance` |
| `parent_resource_id` | ID of parent resource | `i-03dc6874d9bdf8fd3` |
| `parent_name` | Name/tag of parent resource | `web-server-01` |
| `parent_state` | Current state of parent | `running`, `stopped` |
| `account_id` | AWS account number | `096103536687` |
| `environment` | Environment tag value | `production`, `staging` |
| `region` | AWS region | `eu-west-1` |
| `orphaned` | Whether parent is resolvable | `true` or `false` |
| `age_days` | Days since creation | `365` |
| `monthly_cost` | Monthly cost in USD | `2.50` |
| `cost_since_creation` | Total cost since creation | `12.50` |

### Sample CSV Output

```csv
snapshot_id,snapshot_type,creation_date,size_gb,parent_resource_type,parent_resource_id,parent_name,parent_state,account_id,environment,region,orphaned,age_days,monthly_cost,cost_since_creation
snap-0ec7ddeb6be4ede7a,ebs,2024-09-02T13:26:17+00:00,15,ec2_instance,i-03dc6874d9bdf8fd3,attached-ebs,running,096103536687,,eu-west-1,false,365,2.50,12.50
snap-1234567890abcdef0,db,2024-09-01T10:30:00+00:00,100,db_instance,db-1234567890,production-db,available,096103536687,production,eu-west-1,false,366,16.67,83.35
snap-orphaned123456,ebs,2024-08-15T08:00:00+00:00,20,,,,,,,,eu-west-1,true,384,3.33,16.65
```

## Implementation Notes

### Field Mapping

The tool maps Firefly API response fields to CSV columns. If a required field is not available in the API documentation, the corresponding CSV cell will be blank and a WARN log will be generated.

### Parent Resolution Logic

1. **EBS Snapshots**: 
   - Extract `volume_id` from snapshot
   - Query volume details to find `instance_id`
   - Query EC2 instance details

2. **DB Snapshots**:
   - Extract `db_instance_identifier` from snapshot
   - Query database instance details directly

### Size Calculation Methods

The tool extracts snapshot size (`size_gb`) using different methods depending on the snapshot type and storage tier:

#### EBS Snapshots

Size extraction for EBS snapshots depends on the `storage_tier` field from the Firefly API:

**Standard Tier (`storage_tier == "standard"`)**:
1. Primary method: Uses `full_snapshot_size_in_bytes` from `tfObject`
   - Converts bytes to GB: `size_gb = full_snapshot_size_in_bytes / (1024³)`
2. Fallback method: If `full_snapshot_size_in_bytes` is missing or None, falls back to `volume_size` from `tfObject`

**Archive Tier or Other Tiers** (`storage_tier != "standard"` or missing):
- Always uses `volume_size` from `tfObject`
- This includes archive tier snapshots and any snapshots where `storage_tier` is None or not specified

**Summary**:
- Standard tier: `full_snapshot_size_in_bytes` → `volume_size` (fallback)
- Archive/other tiers: `volume_size` only
- Missing `storage_tier`: Treated as non-standard, uses `volume_size` only

#### DB Snapshots

Size extraction for RDS/DB snapshots:
- Always uses `allocated_storage` from `tfObject`

#### Missing Size Information

If size information cannot be extracted using the above methods:
- The `size_gb` field will be blank (empty string)
- Cost calculations will show `prices_not_provided`
- A WARN log will be generated with detailed information about which fields were checked

### Environment Tag Extraction

The tool searches for environment tags in this priority order (case-insensitive):
1. `environment`
2. `env` 
3. `Environment`

### Orphan Detection

A snapshot is marked as orphaned (`orphaned=true`) when:
- Required parent relationship fields are missing from the API response
- Parent resource cannot be resolved via documented endpoints
- API calls fail to return expected data

### Cost Calculation

Cost calculations require valid size information (see [Size Calculation Methods](#size-calculation-methods) above). If size cannot be determined, costs will show as `prices_not_provided`.

#### Pricing Selection

The tool selects pricing based on snapshot type and storage tier. The following table shows how pricing is determined:

| Snapshot Type | Storage Tier | Pricing Field | AWS Pricing Type | Notes |
|---------------|--------------|---------------|------------------|-------|
| EBS | `standard` or missing | `ebs_snapshot_gb_month` | `EBS:SnapshotUsage` | Standard tier pricing (default) |
| EBS | `archive` | `ebs_snapshot_archive_gb_month` | `EBS:SnapshotArchiveStorage` | Archive tier pricing (typically lower) |
| DB | N/A | `rds_snapshot_gb_month` | `:ChargedBackupUsage` | Storage tier not applicable for DB snapshots |

#### Cost Calculation Process

1. **Extract size**: Uses the size calculation methods based on snapshot type and storage tier
2. **Determine pricing tier**: Identifies storage tier for EBS snapshots (standard vs archive)
3. **Get pricing**: Retrieves region-specific pricing from `./aws/snapshot-prices.json` based on snapshot type and tier
4. **Calculate costs**:
   - **Monthly cost**: `size_gb × price_per_gb_month` (using tier-appropriate pricing)
   - **Total cost**: `monthly_cost × (age_days / 30.44)`

**Cost Calculation Formula**:
- Monthly cost = `size_gb × price_per_gb_month` (tier-specific for EBS)
- Total cost = `monthly_cost × (age_days / 30.44)` (average days per month)

**Note**: Cost calculations depend on:
- Snapshot size in GB (extracted via size calculation methods)
- Snapshot type (EBS vs DB)
- Storage tier for EBS snapshots (standard vs archive)
- AWS region pricing data from `./aws/snapshot-prices.json`
- Snapshot age in days

## Testing

Run the test suite:

```bash
pytest tests/
```

### Test Coverage

- **Data Normalization**: Environment tag extraction, name resolution, date parsing, age calculation
- **Parent Resolution**: Orphan detection, relationship resolution, error handling
- **CSV Export**: Header format, streaming functionality, data integrity
- **Performance**: Batch processing and optimization validation

## Logging

The tool provides comprehensive logging:

- **INFO**: General progress and endpoint usage
- **WARN**: Missing fields or unresolvable relationships
- **ERROR**: API failures or processing errors
- **DEBUG**: Detailed request/response information (with `--verbose`)

## Error Handling

- **Authentication**: Validates API token before processing
- **Rate Limiting**: Exponential backoff retry for 429, 502, 503, 504 responses
- **Network Issues**: Retry logic for connection failures
- **Data Validation**: Graceful handling of missing or malformed API responses

## Performance Considerations

- **Batch Processing**: Dramatically reduces API calls for large datasets
- **Streaming Export**: CSV is written row-by-row to handle large datasets
- **Pagination**: Follows Firefly API pagination mechanisms
- **Memory Usage**: Minimal memory footprint with optimized data structures
- **Caching**: Eliminates duplicate API requests within the same run

## Troubleshooting

### Common Issues

1. **Missing API Credentials**: Ensure `FIREFLY_ACCESS_KEY` and `FIREFLY_SECRET_KEY` are set or use `--firefly-access-key` and `--firefly-secret-key`
2. **Invalid Base URL**: Verify the Firefly API base URL is correct (defaults to `https://api.firefly.ai`)
3. **Authentication Errors**: Check API key permissions and ensure credentials are valid
4. **Missing Fields**: Review WARN logs for fields not available in API responses
5. **Pricing Data Missing**: Run `./fetch-snapshot-prices.sh` to update pricing information

### Debug Mode

Use `--verbose` flag for detailed logging:

```bash
python3 main.py --verbose --out "detailed_report.csv"
```

### Performance Issues

If the tool is running slowly:
1. Check for "Batch resolving parents for X EBS snapshots..." messages
2. Verify batch processing is working correctly
3. Monitor API response times in verbose mode

## Contributing

1. Ensure all changes use only documented Firefly API endpoints
2. Add tests for new functionality
3. Update documentation for any endpoint changes
4. Follow the existing code structure and patterns
5. Test performance impact of changes

## License

[Add your license information here]

## Support

For issues related to:
- **Firefly API**: Contact your Firefly API administrator
- **Tool Functionality**: Check the logs and verify API endpoint availability
- **Data Accuracy**: Verify parent relationships are exposed by the Firefly API
- **Performance**: Review the PERFORMANCE_OPTIMIZATION.md file
- **Pricing Updates**: Ensure AWS CLI is configured and has appropriate permissions