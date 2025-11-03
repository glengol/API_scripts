#!/usr/bin/env python3
"""
HTML Report Generator - Creates interactive HTML reports with charts and metrics.
Uses Jinja2 templates to generate static HTML that can be opened in any browser.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Iterator
from jinja2 import Environment, FileSystemLoader, select_autoescape
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class HTMLReportGenerator:
    def __init__(self, output_dir: str = "./reports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Setup Jinja2 environment
        self.env = Environment(
            loader=FileSystemLoader('templates'),
            autoescape=select_autoescape(['html', 'xml'])
        )
        
        # Ensure templates directory exists
        self.templates_dir = Path('templates')
        self.templates_dir.mkdir(exist_ok=True)
        
        # Create default template if it doesn't exist
        self._create_default_template()
    
    def _create_default_template(self):
        """Create the default HTML template if it doesn't exist."""
        template_file = self.templates_dir / "snapshot_report.html"
        if not template_file.exists():
            self._write_default_template(template_file)
    
    def _write_default_template(self, template_file: Path):
        """Write the default HTML template."""
        template_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AWS Snapshot Report - {{ report_date }}</title>
    
    <!-- Bootstrap CSS -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <!-- DataTables CSS -->
    <link href="https://cdn.datatables.net/1.13.6/css/dataTables.bootstrap5.min.css" rel="stylesheet">
    <!-- Chart.js -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    
    <style>
        .metric-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-radius: 15px;
            padding: 1.5rem;
            margin-bottom: 1rem;
        }
        .cost-savings {
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        }
        .orphaned-resources {
            background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
        }
        .chart-container {
            position: relative;
            height: 400px;
            margin: 2rem 0;
        }
        .table-responsive {
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        .navbar-brand {
            font-weight: bold;
            font-size: 1.5rem;
        }
        .footer {
            background-color: #f8f9fa;
            padding: 2rem 0;
            margin-top: 3rem;
        }
        .snapshot-id-cell {
            max-width: 500px;
            word-break: break-all;
            white-space: normal;
        }
        code {
            font-size: 0.9em;
        }
    </style>
</head>
<body>
    <!-- Navigation -->
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container">
            <span class="navbar-brand">📊 AWS Snapshot Report</span>
            <span class="navbar-text">Generated: {{ report_date }}</span>
        </div>
    </nav>

    <div class="container mt-4">
        <!-- Executive Summary -->
        <div class="row mb-4">
            <div class="col-12">
                <h2 class="mb-3">Executive Summary</h2>
            </div>
        </div>
        
        <!-- Key Metrics -->
        <div class="row mb-4">
            <div class="col-md-3">
                <div class="metric-card text-center">
                    <h3>{{ total_snapshots }}</h3>
                    <p class="mb-0">Total Snapshots</p>
                </div>
            </div>
            <div class="col-md-3">
                <div class="metric-card text-center">
                    <h3>${{ "%.2f"|format(total_monthly_cost) }}</h3>
                    <p class="mb-0">Monthly Cost</p>
                </div>
            </div>
            <div class="col-md-3">
                <div class="metric-card orphaned-resources text-center">
                    <h3>{{ orphaned_count }}</h3>
                    <p class="mb-0">Orphaned Resources</p>
                </div>
            </div>
            <div class="col-md-3">
                <div class="metric-card cost-savings text-center">
                    <h3>${{ "%.2f"|format(orphaned_monthly_cost) }}</h3>
                    <p class="mb-0">Potential Savings</p>
                </div>
            </div>
        </div>

        <!-- Charts Row -->
        <div class="row mb-4">
            <div class="col-md-6">
                <div class="card">
                    <div class="card-header">
                        <h5 class="mb-0">Snapshot Distribution by Type</h5>
                    </div>
                    <div class="card-body">
                        <div class="chart-container">
                            <canvas id="typeChart"></canvas>
                        </div>
                    </div>
                </div>
            </div>
            <div class="col-md-6">
                <div class="card">
                    <div class="card-header">
                        <h5 class="mb-0">Cost Distribution by Region</h5>
                    </div>
                    <div class="card-body">
                        <div class="chart-container">
                            <canvas id="regionChart"></canvas>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Account Distribution Chart -->
        <div class="row mb-4">
            <div class="col-12">
                <div class="card">
                    <div class="card-header">
                        <h5 class="mb-0">Snapshot Distribution by Account (Orphaned vs Parented)</h5>
                    </div>
                    <div class="card-body">
                        <div class="chart-container">
                            <canvas id="accountChart"></canvas>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Age Distribution Chart -->
        <div class="row mb-4">
            <div class="col-12">
                <div class="card">
                    <div class="card-header">
                        <h5 class="mb-0">Snapshot Age Distribution</h5>
                    </div>
                    <div class="card-body">
                        <div class="chart-container">
                            <canvas id="ageChart"></canvas>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Cost Savings Opportunities -->
        <div class="row mb-4">
            <div class="col-12">
                <div class="card">
                    <div class="card-header bg-warning text-dark">
                        <h5 class="mb-0">🚨 Cost Savings Opportunities</h5>
                    </div>
                    <div class="card-body">
                        <p class="text-muted">These orphaned snapshots represent potential cost savings:</p>
                        <div class="table-responsive">
                            <table class="table table-striped table-hover" id="savingsTable">
                                <thead class="table-dark">
                                    <tr>
                                        <th>Snapshot ID</th>
                                        <th>Type</th>
                                        <th>Storage Tier</th>
                                        <th>Size (GB)</th>
                                        <th>Age (Days)</th>
                                        <th>Monthly Cost</th>
                                        <th>Total Cost</th>
                                        <th>Region</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for snapshot in orphaned_snapshots %}
                                    <tr>
                                        <td class="snapshot-id-cell"><code>{{ snapshot.snapshot_id }}</code></td>
                                        <td><span class="badge bg-{{ 'primary' if snapshot.snapshot_type == 'ebs' else 'success' }}">{{ snapshot.snapshot_type.upper() }}</span></td>
                                        <td>{% if snapshot.snapshot_type == 'ebs' and snapshot.storage_tier %}<span class="badge bg-{{ 'info' if snapshot.storage_tier == 'standard' else 'warning' }}">{{ snapshot.storage_tier.upper() }}</span>{% else %}-{% endif %}</td>
                                        <td>{% if snapshot.size_gb %}{{ "%.2f"|format(snapshot.size_gb|float) }}{% else %}N/A{% endif %}</td>
                                        <td>{{ snapshot.age_days }}</td>
                                        <td class="text-danger fw-bold">{{ snapshot.monthly_cost }}</td>
                                        <td class="text-danger">{{ snapshot.cost_since_creation }}</td>
                                        <td><span class="badge bg-secondary">{{ snapshot.region }}</span></td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Detailed Data Table -->
        <div class="row mb-4">
            <div class="col-12">
                <div class="card">
                    <div class="card-header">
                        <h5 class="mb-0">Detailed Snapshot Data</h5>
                    </div>
                    <div class="card-body">
                        <div class="table-responsive">
                            <table class="table table-striped table-hover" id="mainTable">
                                <thead class="table-dark">
                                    <tr>
                                        <th>Snapshot ID</th>
                                        <th>Type</th>
                                        <th>Storage Tier</th>
                                        <th>Creation Date</th>
                                        <th>Size (GB)</th>
                                        <th>Parent Resource</th>
                                        <th>Account</th>
                                        <th>Region</th>
                                        <th>Age (Days)</th>
                                        <th>Monthly Cost</th>
                                        <th>Total Cost</th>
                                        <th>Status</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for snapshot in all_snapshots %}
                                    <tr class="{{ 'table-warning' if snapshot.orphaned else '' }}">
                                        <td class="snapshot-id-cell"><code>{{ snapshot.snapshot_id }}</code></td>
                                        <td><span class="badge bg-{{ 'primary' if snapshot.snapshot_type == 'ebs' else 'success' }}">{{ snapshot.snapshot_type.upper() }}</span></td>
                                        <td>{% if snapshot.snapshot_type == 'ebs' and snapshot.storage_tier %}<span class="badge bg-{{ 'info' if snapshot.storage_tier == 'standard' else 'warning' }}">{{ snapshot.storage_tier.upper() }}</span>{% else %}-{% endif %}</td>
                                        <td>{{ snapshot.creation_date[:10] if snapshot.creation_date else 'N/A' }}</td>
                                        <td>{% if snapshot.size_gb %}{{ "%.2f"|format(snapshot.size_gb|float) }}{% else %}N/A{% endif %}</td>
                                        <td>
                                            {% if snapshot.orphaned %}
                                                <span class="text-danger">Orphaned</span>
                                            {% else %}
                                                <span class="snapshot-id-cell">{{ snapshot.parent_resource_type }}: <code>{{ snapshot.parent_resource_id if snapshot.parent_resource_id else 'N/A' }}</code></span>
                                            {% endif %}
                                        </td>
                                        <td>{{ snapshot.account_id }}</td>
                                        <td><span class="badge bg-secondary">{{ snapshot.region }}</span></td>
                                        <td>{{ snapshot.age_days }}</td>
                                        <td class="fw-bold">{{ snapshot.monthly_cost }}</td>
                                        <td>{{ snapshot.cost_since_creation }}</td>
                                        <td>
                                            {% if snapshot.orphaned %}
                                                <span class="badge bg-danger">Orphaned</span>
                                            {% else %}
                                                <span class="badge bg-success">Active</span>
                                            {% endif %}
                                        </td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Footer -->
    <footer class="footer">
        <div class="container">
            <div class="row">
                <div class="col-md-6">
                    <h6>Report Information</h6>
                    <p class="mb-0">Generated on: {{ report_date }}</p>
                    <p class="mb-0">Total snapshots analyzed: {{ total_snapshots }}</p>
                </div>
                <div class="col-md-6 text-md-end">
                    <h6>Cost Summary</h6>
                    <p class="mb-0">Total monthly cost: ${{ "%.2f"|format(total_monthly_cost) }}</p>
                    <p class="mb-0">Potential savings: ${{ "%.2f"|format(orphaned_monthly_cost) }}</p>
                </div>
            </div>
        </div>
    </footer>

    <!-- Scripts -->
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script src="https://code.jquery.com/jquery-3.7.0.min.js"></script>
    <script src="https://cdn.datatables.net/1.13.6/js/jquery.dataTables.min.js"></script>
    <script src="https://cdn.datatables.net/1.13.6/js/dataTables.bootstrap5.min.js"></script>

    <script>
        // Initialize DataTables
        $(document).ready(function() {
            $('#mainTable').DataTable({
                pageLength: 25,
                order: [[8, 'desc']], // Sort by age descending (column index 8)
                responsive: false,
                scrollX: true,
                autoWidth: false,
                columnDefs: [
                    { width: "250px", targets: 0 }, // Snapshot ID column
                    { width: "300px", targets: 5 }  // Parent Resource column (moved to index 5)
                ]
            });
            
            $('#savingsTable').DataTable({
                pageLength: 10,
                order: [[5, 'desc']], // Sort by monthly cost descending (column index 5)
                responsive: false,
                scrollX: true,
                autoWidth: false,
                columnDefs: [
                    { width: "250px", targets: 0 }  // Snapshot ID column
                ]
            });
        });

        // Chart.js Charts
        const typeData = {{ type_distribution|tojson }};
        const regionData = {{ region_distribution|tojson }};
        const accountData = {{ account_distribution|tojson }};
        const ageData = {{ age_distribution|tojson }};

        // Snapshot Type Distribution Chart
        new Chart(document.getElementById('typeChart'), {
            type: 'doughnut',
            data: {
                labels: typeData.labels,
                datasets: [{
                    data: typeData.data,
                    backgroundColor: ['#007bff', '#28a745', '#ffc107', '#dc3545']
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom'
                    }
                }
            }
        });

        // Region Cost Distribution Chart
        new Chart(document.getElementById('regionChart'), {
            type: 'bar',
            data: {
                labels: regionData.labels,
                datasets: [{
                    label: 'Monthly Cost ($)',
                    data: regionData.data,
                    backgroundColor: '#007bff'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: function(value) {
                                return '$' + value.toFixed(2);
                            }
                        }
                    }
                }
            }
        });

        // Account Distribution Chart (Grouped: Orphaned, Parented, Total)
        new Chart(document.getElementById('accountChart'), {
            type: 'bar',
            data: {
                labels: accountData.labels,
                datasets: [{
                    label: 'Orphaned Snapshots',
                    data: accountData.orphaned_data,
                    backgroundColor: '#dc3545',
                    borderColor: '#c82333',
                    borderWidth: 1
                }, {
                    label: 'Parented Snapshots',
                    data: accountData.parented_data,
                    backgroundColor: '#28a745',
                    borderColor: '#1e7e34',
                    borderWidth: 1
                }, {
                    label: 'Total Snapshots',
                    data: accountData.total_data,
                    backgroundColor: '#6c757d',
                    borderColor: '#545b62',
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        stacked: false
                    },
                    y: {
                        beginAtZero: true,
                        stacked: false,
                        ticks: {
                            stepSize: 1
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: true,
                        position: 'top'
                    },
                    tooltip: {
                        callbacks: {
                            afterLabel: function(context) {
                                const orphaned = accountData.orphaned_data[context.dataIndex];
                                const parented = accountData.parented_data[context.dataIndex];
                                const total = accountData.total_data[context.dataIndex];
                                
                                if (context.datasetIndex === 0) { // Orphaned
                                    return `Total: ${total} | Parented: ${parented}`;
                                } else if (context.datasetIndex === 1) { // Parented
                                    return `Total: ${total} | Orphaned: ${orphaned}`;
                                } else { // Total
                                    return `Orphaned: ${orphaned} | Parented: ${parented}`;
                                }
                            }
                        }
                    }
                }
            }
        });

        // Age Distribution Chart
        new Chart(document.getElementById('ageChart'), {
            type: 'bar',
            data: {
                labels: ageData.labels,
                datasets: [{
                    label: 'Number of Snapshots',
                    data: ageData.data,
                    backgroundColor: '#28a745'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true
                    }
                }
            }
        });
    </script>
</body>
</html>"""
        
        template_file.write_text(template_content)
        logger.info(f"Created default template: {template_file}")
    
    def generate_report(self, snapshots: Iterator[Dict[str, Any]], output_filename: str = "snapshot_report.html"):
        """Generate HTML report from snapshot data."""
        logger.info("Generating HTML report...")
        
        # Convert iterator to list for processing
        snapshots_list = list(snapshots)
        
        if not snapshots_list:
            logger.warning("No snapshots to generate report for")
            return
        
        # Calculate metrics
        metrics = self._calculate_metrics(snapshots_list)
        
        # Prepare data for charts
        chart_data = self._prepare_chart_data(snapshots_list)
        
        # Get template and render
        template = self.env.get_template("snapshot_report.html")
        
        html_content = template.render(
            report_date=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            total_snapshots=metrics['total_snapshots'],
            total_monthly_cost=metrics['total_monthly_cost'],
            orphaned_count=metrics['orphaned_count'],
            orphaned_monthly_cost=metrics['orphaned_monthly_cost'],
            all_snapshots=snapshots_list,
            orphaned_snapshots=[s for s in snapshots_list if s.get('orphaned')],
            type_distribution=chart_data['type_distribution'],
            region_distribution=chart_data['region_distribution'],
            account_distribution=chart_data['account_distribution'],
            age_distribution=chart_data['age_distribution']
        )
        
        # Write HTML file
        output_file = self.output_dir / output_filename
        output_file.write_text(html_content)
        
        logger.info(f"HTML report generated: {output_file}")
        return str(output_file)
    
    def _calculate_metrics(self, snapshots: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate key metrics from snapshot data."""
        total_snapshots = len(snapshots)
        orphaned_snapshots = [s for s in snapshots if s.get('orphaned')]
        orphaned_count = len(orphaned_snapshots)
        
        # Calculate costs
        total_monthly_cost = 0.0
        orphaned_monthly_cost = 0.0
        
        for snapshot in snapshots:
            monthly_cost_str = snapshot.get('monthly_cost', '')
            if monthly_cost_str and monthly_cost_str != 'prices_not_provided':
                try:
                    cost = float(monthly_cost_str.replace('$', ''))
                    total_monthly_cost += cost
                    
                    if snapshot.get('orphaned'):
                        orphaned_monthly_cost += cost
                except ValueError:
                    pass
        
        return {
            'total_snapshots': total_snapshots,
            'total_monthly_cost': total_monthly_cost,
            'orphaned_count': orphaned_count,
            'orphaned_monthly_cost': orphaned_monthly_cost
        }
    
    def _prepare_chart_data(self, snapshots: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Prepare data for Chart.js charts."""
        # Type distribution
        type_counts = {}
        for snapshot in snapshots:
            snapshot_type = snapshot.get('snapshot_type', 'unknown')
            type_counts[snapshot_type] = type_counts.get(snapshot_type, 0) + 1
        
        # Region cost distribution
        region_costs = {}
        for snapshot in snapshots:
            region = snapshot.get('region', 'unknown')
            monthly_cost_str = snapshot.get('monthly_cost', '')
            if monthly_cost_str and monthly_cost_str != 'prices_not_provided':
                try:
                    cost = float(monthly_cost_str.replace('$', ''))
                    region_costs[region] = region_costs.get(region, 0) + cost
                except ValueError:
                    pass
        
        # Account distribution (orphaned vs parented)
        account_orphaned = {}
        account_parented = {}
        for snapshot in snapshots:
            account_id = snapshot.get('account_id', 'unknown')
            is_orphaned = snapshot.get('orphaned', False)
            if is_orphaned:
                account_orphaned[account_id] = account_orphaned.get(account_id, 0) + 1
            else:
                account_parented[account_id] = account_parented.get(account_id, 0) + 1
        
        # Age distribution (grouped by ranges)
        age_ranges = {
            '0-30 days': 0,
            '31-90 days': 0,
            '91-180 days': 0,
            '181-365 days': 0,
            '1+ years': 0
        }
        
        for snapshot in snapshots:
            age_days = snapshot.get('age_days', 0)
            if age_days <= 30:
                age_ranges['0-30 days'] += 1
            elif age_days <= 90:
                age_ranges['31-90 days'] += 1
            elif age_days <= 180:
                age_ranges['91-180 days'] += 1
            elif age_days <= 365:
                age_ranges['181-365 days'] += 1
            else:
                age_ranges['1+ years'] += 1
        
        return {
            'type_distribution': {
                'labels': list(type_counts.keys()),
                'data': list(type_counts.values())
            },
            'region_distribution': {
                'labels': list(region_costs.keys()),
                'data': list(region_costs.values())
            },
            'account_distribution': {
                'labels': list(set(list(account_orphaned.keys()) + list(account_parented.keys()))),
                'orphaned_data': [account_orphaned.get(acc, 0) for acc in list(set(list(account_orphaned.keys()) + list(account_parented.keys())))],
                'parented_data': [account_parented.get(acc, 0) for acc in list(set(list(account_orphaned.keys()) + list(account_parented.keys())))],
                'total_data': [account_orphaned.get(acc, 0) + account_parented.get(acc, 0) for acc in list(set(list(account_orphaned.keys()) + list(account_parented.keys())))]
            },
            'age_distribution': {
                'labels': list(age_ranges.keys()),
                'data': list(age_ranges.values())
            }
        }
