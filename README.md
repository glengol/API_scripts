# Scripts
General scripts for customers

## Available Tools

### AWS Snapshot Tool
A high-performance CLI tool that correlates EBS and RDS/DB snapshots to their parent resources using the Firefly API. This tool generates comprehensive CSV and HTML reports showing the relationship between snapshots and their parent EC2 instances or database instances, with cost analysis and performance optimizations.

**Key Features:**
- EBS and DB snapshot correlation to parent resources
- Comprehensive CSV and HTML reporting
- Cost analysis with AWS pricing data
- Orphan detection for cleanup opportunities
- Environment tagging and resource state tracking
- Performance optimized with batch processing

**Quick Start:**
```bash
cd aws-snapshot-tool
pip install -r requirements.txt
python3 main.py --format both
```

For detailed documentation, installation instructions, and usage examples, see: [aws-snapshot-tool/README.md](./aws-snapshot-tool/README.md)
