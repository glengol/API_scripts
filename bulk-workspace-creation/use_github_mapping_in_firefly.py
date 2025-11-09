#!/usr/bin/env python3
"""
Script to create Firefly workflows from GitHub directory mapping.
Reads the GitHub directory mapping JSON and creates a Firefly workspace for each subdirectory.
"""

import json
import sys
from typing import Dict, Any, List

try:
    import requests
except ImportError:
    print("Error: 'requests' library is required. Install it with: pip install requests")
    sys.exit(1)

# ============================================================================
# Firefly API Configuration - Hardcoded values (modify as needed)
# ============================================================================

# Firefly API Authentication
FIREFLY_API_BASE_URL = "https://api.firefly.ai"
ACCESS_KEY = "ACCESS_KEY"  # Replace with your actual Firefly access key
SECRET_KEY = "SECRET_KEY"  # Replace with your actual Firefly secret key

# VCS Configuration
VCS_ID = "VCS_ID"  # Replace with your VCS integration ID
# VCS Type options: "github", "gitlab", "bitbucket", "codecommit", "azuredevops"
VCS_TYPE = "github"
DEFAULT_BRANCH = "main"  # Default branch for repositories

RUNNER_TYPE = "firefly" # Runner Type options: "github-actions", "gitlab-pipelines", "bitbucket-pipelines", "azure-pipelines", "jenkins", "semaphore", "atlantis", "env0", "firefly", "unrecognized"
IAC_TYPE = "terraform"  # Infrastructure as Code type
TERRAFORM_VERSION = "1.5.7"  # Terraform version to use

# Execution Configuration
EXECUTION_TRIGGERS = ["merge"]  # Options: ["merge", "push", "pull_request"]
APPLY_RULE = "manual"  # Options: "manual", "auto"

# Workspace Variables (can be empty array if not needed)
WORKSPACE_VARIABLES = [
    # Example:
    # {
    #     "key": "ENV",
    #     "value": "production",
    #     "sensitivity": "string",  # Options: "string", "secret"
    #     "destination": "env"  # Options: "env", "iac"
    # }
]

# Optional Configuration
PROJECT_ID = None  # Project ID or None for global access
CONSUMED_VARIABLE_SETS = []  # Array of variable set IDs

# Input/Output Files
MAPPING_JSON_FILE = "github_directory_mapping.json"
OUTPUT_LOG_FILE = "firefly_workflows_created.json"


# ============================================================================
# Helper Functions
# ============================================================================

def login_to_firefly() -> str:
    """
    Authenticate with Firefly API using access key and secret key.
    
    Returns:
        Access token string
    
    Raises:
        ValueError: If authentication fails
    """
    login_url = f"{FIREFLY_API_BASE_URL}/api/v1.0/login"
    
    headers = {
        "Content-Type": "application/json"
    }
    
    body = {
        "accessKey": ACCESS_KEY,
        "secretKey": SECRET_KEY
    }
    
    try:
        response = requests.post(login_url, json=body, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        access_token = data.get("accessToken")
        
        if not access_token:
            raise ValueError("No accessToken received from login response")
        
        return access_token
    except requests.exceptions.RequestException as e:
        raise ValueError(f"Failed to authenticate with Firefly API: {e}")


def get_all_subdirectories(directory_structure: Dict[str, Any], base_path: str = "") -> List[str]:
    """
    Recursively extract only leaf directory paths (end directories with no subdirectories).
    
    Args:
        directory_structure: Nested dictionary representing directory structure
        base_path: Current base path (for recursion)
    
    Returns:
        List of only leaf directory paths (directories with no subdirectories)
    
    Example:
        Input: {
            "aws": {
                "something": {
                    "more": {
                        "nested": {"directories": {}},
                        "123": {}
                    }
                }
            }
        }
        Output: ["aws/something/more/nested/directories", "aws/something/more/123"]
    """
    paths = []
    
    for dir_name, subdirs in directory_structure.items():
        # Build the full path for this directory
        current_path = f"{base_path}/{dir_name}" if base_path else dir_name
        
        # If this directory has no subdirectories (is a leaf), add it
        if not subdirs or subdirs == {}:
            paths.append(current_path)
        else:
            # If this directory has subdirectories, recurse to find leaf directories
            paths.extend(get_all_subdirectories(subdirs, current_path))
    
    return paths


def create_firefly_workspace(
    repo: str,
    work_dir: str,
    workspace_name: str,
    access_token: str,
    description: str = None
) -> Dict[str, Any]:
    """
    Create a Firefly workspace using the Firefly API.
    
    Args:
        repo: Repository name in owner/repo format
        work_dir: Working directory path (subdirectory path with leading slash)
        workspace_name: Unique workspace name (full path format: owner/repo/subdir)
        access_token: Firefly API access token from login
        description: Optional workspace description
    
    Returns:
        API response dictionary
    """
    url = f"{FIREFLY_API_BASE_URL}/v2/runners/workspaces"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    # Build request body according to Firefly API documentation
    request_body = {
        "runnerType": RUNNER_TYPE,
        "iacType": IAC_TYPE,
        "workspaceName": workspace_name,
        "vcsId": VCS_ID,
        "repo": repo,
        "defaultBranch": DEFAULT_BRANCH,
        "vcsType": VCS_TYPE,
        "workDir": work_dir,
        "variables": WORKSPACE_VARIABLES,
        "execution": {
            "triggers": EXECUTION_TRIGGERS,
            "applyRule": APPLY_RULE,
            "terraformVersion": TERRAFORM_VERSION
        }
    }
    
    # Add optional fields if provided
    if description:
        request_body["description"] = description
    
    if PROJECT_ID is not None:
        request_body["project"] = PROJECT_ID
    
    if CONSUMED_VARIABLE_SETS:
        request_body["consumedVariableSets"] = CONSUMED_VARIABLE_SETS
    
    try:
        response = requests.post(url, json=request_body, headers=headers)
        response.raise_for_status()
        return {
            "success": True,
            "status_code": response.status_code,
            "data": response.json()
        }
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "error": str(e),
            "status_code": getattr(e.response, 'status_code', None) if hasattr(e, 'response') else None,
            "response_text": getattr(e.response, 'text', None) if hasattr(e, 'response') else None
        }


def generate_workspace_name(repo: str, work_dir: str) -> str:
    """
    Generate a unique workspace name from repository and work directory.
    Format: owner/repo/subdir (e.g., "Firefly-SE/lior/aws")
    
    Args:
        repo: Repository name in owner/repo format
        work_dir: Working directory path (e.g., "/aws" or "aws")
    
    Returns:
        Generated workspace name in format: owner/repo/subdir
    """
    # Remove leading slash from work_dir if present
    clean_work_dir = work_dir.lstrip('/')
    
    # Combine: owner/repo/subdir
    workspace_name = f"{repo}/{clean_work_dir}"
    
    return workspace_name


def format_work_dir(work_dir: str) -> str:
    """
    Format work directory path with leading slash.
    Format: /subdir (e.g., "/aws")
    
    Args:
        work_dir: Working directory path (e.g., "aws" or "/aws")
    
    Returns:
        Formatted work directory path with leading slash
    """
    # Ensure leading slash
    if not work_dir.startswith('/'):
        return f"/{work_dir}"
    return work_dir


# ============================================================================
# Main Function
# ============================================================================

def main():
    """Main function to process GitHub mapping and create Firefly workflows."""
    
    # Validate configuration
    if ACCESS_KEY == "YOUR_ACCESS_KEY":
        print("ERROR: Please set ACCESS_KEY in the script!")
        return 1
    
    if SECRET_KEY == "YOUR_SECRET_KEY":
        print("ERROR: Please set SECRET_KEY in the script!")
        return 1
    
    if VCS_ID == "YOUR_VCS_INTEGRATION_ID":
        print("ERROR: Please set VCS_ID in the script!")
        return 1
    
    # Authenticate with Firefly API
    print("Authenticating with Firefly API...")
    try:
        access_token = login_to_firefly()
        print("✓ Authentication successful")
    except ValueError as e:
        print(f"ERROR: {e}")
        return 1
    
    # Load GitHub directory mapping
    try:
        with open(MAPPING_JSON_FILE, 'r', encoding='utf-8') as f:
            mapping_data = json.load(f)
    except FileNotFoundError:
        print(f"ERROR: Mapping file '{MAPPING_JSON_FILE}' not found!")
        print("Please run get_github_mapping.py first to generate the mapping.")
        return 1
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in '{MAPPING_JSON_FILE}': {e}")
        return 1
    
    print("="*70)
    print("Creating Firefly Workflows from GitHub Directory Mapping")
    print("="*70)
    print(f"\nConfiguration:")
    print(f"  API Base URL: {FIREFLY_API_BASE_URL}")
    print(f"  VCS Type: {VCS_TYPE}")
    print(f"  Runner Type: {RUNNER_TYPE}")
    print(f"  IAC Type: {IAC_TYPE}")
    print(f"  Terraform Version: {TERRAFORM_VERSION}")
    print(f"  Default Branch: {DEFAULT_BRANCH}")
    print(f"  Apply Rule: {APPLY_RULE}")
    print(f"  Triggers: {', '.join(EXECUTION_TRIGGERS)}")
    print()
    
    # Process each repository
    results = {
        "total_repos": len(mapping_data),
        "total_workflows_created": 0,
        "total_workflows_failed": 0,
        "workflows": []
    }
    
    for repo, directory_structure in mapping_data.items():
        print(f"\n{'='*70}")
        print(f"Processing Repository: {repo}")
        print(f"{'='*70}")
        
        # Get all subdirectories for this repo
        subdirectories = get_all_subdirectories(directory_structure)
        
        if not subdirectories:
            print(f"  No subdirectories found in {repo}")
            continue
        
        print(f"  Found {len(subdirectories)} subdirectories")
        
        # Create workflow for each subdirectory
        for work_dir in subdirectories:
            # Format work directory with leading slash
            formatted_work_dir = format_work_dir(work_dir)
            
            # Generate workspace name: owner/repo/subdir
            workspace_name = generate_workspace_name(repo, work_dir)
            description = f"Workflow for {repo}{formatted_work_dir}"
            
            print(f"\n  Creating workspace: {workspace_name}")
            print(f"    Repository: {repo}")
            print(f"    Work Directory: {formatted_work_dir}")
            
            # Create the workspace
            result = create_firefly_workspace(
                repo=repo,
                work_dir=formatted_work_dir,
                workspace_name=workspace_name,
                access_token=access_token,
                description=description
            )
            
            workflow_info = {
                "repo": repo,
                "work_dir": formatted_work_dir,
                "workspace_name": workspace_name,
                "description": description,
                "success": result["success"]
            }
            
            if result["success"]:
                print(f"    ✓ Successfully created workspace")
                workflow_info["workspace_id"] = result["data"].get("id")
                workflow_info["status_code"] = result["status_code"]
                results["total_workflows_created"] += 1
            else:
                print(f"    ✗ Failed to create workspace")
                print(f"      Error: {result.get('error', 'Unknown error')}")
                if result.get("status_code"):
                    print(f"      Status Code: {result['status_code']}")
                if result.get("response_text"):
                    print(f"      Response: {result['response_text'][:200]}")
                workflow_info["error"] = result.get("error")
                workflow_info["status_code"] = result.get("status_code")
                results["total_workflows_failed"] += 1
            
            results["workflows"].append(workflow_info)
    
    # Save results to file
    try:
        with open(OUTPUT_LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\n{'='*70}")
        print("Summary")
        print(f"{'='*70}")
        print(f"Total repositories processed: {results['total_repos']}")
        print(f"Total workflows created: {results['total_workflows_created']}")
        print(f"Total workflows failed: {results['total_workflows_failed']}")
        print(f"\nResults saved to: {OUTPUT_LOG_FILE}")
    except Exception as e:
        print(f"\nWarning: Could not save results to file: {e}")
    
    return 0 if results["total_workflows_failed"] == 0 else 1


if __name__ == '__main__':
    exit(main())