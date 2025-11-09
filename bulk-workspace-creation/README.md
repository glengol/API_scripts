# GitHub Repository Directory Mapping Script

A Python script that creates a comprehensive mapping of all directories and nested subdirectories from a GitHub repository. The script uses the GitHub API to fetch repository structure and generates a nested dictionary that can be displayed in the console or saved to a JSON file.

## How It Works

The script uses the GitHub API to fetch the repository tree structure and builds a nested dictionary representing the entire directory hierarchy. It:
- Only maps directories (files are ignored)
- Skips hidden directories (starting with `.`)
- Fetches data directly from GitHub (no local clone needed)
- Uses GitHub's recursive tree API for efficient fetching
- Provides a tree-view display in the console
- Can export the mapping to a JSON file

## Requirements

- Python 3.6 or higher
- `requests` library (install with `pip install requests`)

## Installation

1. Ensure you have Python 3.6+ installed:
```bash
python3 --version
```

2. Install the required dependency:
```bash
pip install requests
```

## GitHub Authentication

### Why You Need a Token

- **Public repositories**: Works without authentication (limited to 60 requests/hour)
- **Private repositories**: Requires authentication
- **Higher rate limits**: Authenticated requests allow 5,000 requests/hour

### How to Create a GitHub API Token

> **Quick Link**: [Create Token Directly](https://github.com/settings/tokens/new)

Follow these detailed steps to create your GitHub Personal Access Token:

#### Step-by-Step Instructions

1. **Log in to GitHub**
   - Go to [github.com](https://github.com) and sign in to your account

2. **Navigate to Settings**
   - Click on your profile picture (top right corner)
   - Click on **Settings** from the dropdown menu

3. **Access Developer Settings**
   - Scroll down in the left sidebar
   - Click on **Developer settings** (near the bottom)

4. **Go to Personal Access Tokens**
   - Click on **Personal access tokens** in the left sidebar
   - Click on **Tokens (classic)** (or use Fine-grained tokens if preferred)

5. **Generate New Token**
   - Click the **Generate new token** button
   - Select **Generate new token (classic)**

6. **Configure Your Token**
   - **Note**: Give your token a descriptive name (e.g., "Directory Mapping Script")
   - **Expiration**: Choose an expiration period (30 days, 90 days, or no expiration)
   - **Scopes**: Select the scopes you need:
     - **For public repos only**: No scopes needed
     - **For private repos**: Check the `repo` scope (this grants full access to repositories)
     - **For read-only access to private repos**: Use Fine-grained tokens instead

7. **Generate and Copy Token**
   - Scroll down and click **Generate token**
   - **IMPORTANT**: Copy the token immediately - you won't be able to see it again!
   - The token will start with `ghp_` (for classic tokens)

8. **Save Your Token Securely**
   - Store it in a password manager or secure location
   - Never commit tokens to version control!

### Setting Up Your Token and Repositories

**Hardcode in Script (Quick Start)**

Edit the `get_github_mapping.py` file and set your configuration:

1. **Set your GitHub token** (line 20):
```python
GITHUB_TOKEN = "ghp_your_actual_token_here"
```

2. **Set repositories to map** (lines 27-30):
```python
REPOS_TO_MAP = [
    "owner/repo",
    "owner"
]
```

⚠️ **Warning**: Only use this for local development. Never commit tokens to version control!

**Examples:**
```python
# Map specific repositories
REPOS_TO_MAP = [
    "Firefly-SE/firefly",
    "Firefly-SE/k8s_clusteres_tf"
]

# Map entire organization
REPOS_TO_MAP = [
    "Firefly-SE"  # Maps all repositories in the organization
]

# Mix of individual repos and organizations
REPOS_TO_MAP = [
    "Firefly-SE/firefly",  # Individual repo
    "Firefly-SE"        # Entire organization
]
```

## Usage

### Basic Usage

1. **Edit the script** to set your repositories:
   - Open `get_github_mapping.py`
   - Set `GITHUB_TOKEN` (line 20)
   - Set `REPOS_TO_MAP` list (lines 27-30)

2. **Run the script**:
```bash
python get_github_mapping.py
```

The script will:
- Process all repositories/organizations in `REPOS_TO_MAP`
- Map all directories for each repository
- Save results to `github_directory_mapping.json`

### Repository Format Options

You can specify repositories in several formats:

- **Individual repository**: `"owner/repo"`
- **Organization**: `"owner"` (maps all repos in the organization)
- **Full GitHub URL**: `"https://github.com/owner/repo"`
- **Organization URL**: `"https://github.com/owner"`

### Examples

**Example 1: Map specific repositories**
```python
REPOS_TO_MAP = [
    "Firefly-SE/firefly",
    "Firefly-SE/k8s_clusteres_tf"
]
```

**Example 2: Map entire organization**
```python
REPOS_TO_MAP = [
    "Firefly-SE"  # Maps all repositories in the organization
]
```

**Example 3: Mix of repos and organizations**
```python
REPOS_TO_MAP = [
    "Firefly-SE/firefly",     # Individual repo
    "Firefly-SE",          # Entire organization
    "https://github.com/microsoft/vscode"  # Full URL
]
```

**Example Output:**
```
============================================================
Fetching directory mapping for: Firefly-SE/firefly
============================================================
Total directories mapped: 4

============================================================
Processing organization: Firefly-SE
============================================================
Found 11 repositories in organization

Fetching directory mapping for: Firefly-SE/k8s_clusteres_tf
  ✓ Mapped 16 directories
...
```

## Output Format

### Console Output
The console output displays a tree structure showing the directory hierarchy with indentation and tree branches (├──).

### JSON Output
When saved to a JSON file, the mapping is a nested dictionary structure:

```json
{
  "src": {
    "components": {},
    "utils": {},
    "tests": {}
  },
  "docs": {
    "api": {},
    "guides": {}
  },
  "config": {}
}
```

Empty objects `{}` represent directories with no subdirectories. Nested objects represent directories containing other directories.

## Credentials and Authentication

### Public Repositories
- **No credentials required** for public repositories
- Limited to 60 API requests per hour (unauthenticated)
- Perfect for quick exploration of public repos

### Private Repositories
- **GitHub token required** for private repositories
- Set via `GITHUB_TOKEN` environment variable or `--token` flag
- Token needs `repo` scope for private repos

### Rate Limits
- **Unauthenticated**: 60 requests/hour
- **Authenticated**: 5,000 requests/hour

If you hit rate limits, wait an hour or use authentication for higher limits.

## Error Handling

The script handles common errors gracefully:
- **Repository Not Found**: If the repository doesn't exist or you don't have access, displays an error message
- **Branch Not Found**: If the specified branch doesn't exist, shows an error
- **Rate Limit Exceeded**: If you exceed GitHub's rate limits, displays an error with guidance
- **Network Errors**: Handles connection issues and API errors with informative messages

## Notes

- Hidden directories (starting with `.`) are automatically skipped
- Files are not included in the mapping (only directories)
- The script fetches the entire repository tree in one API call using GitHub's recursive tree endpoint
- Works with both public and private repositories (private repos require authentication)
- No need to clone the repository locally - everything is fetched via API

# Firefly Workflow Creation Script

A Python script that automatically creates Firefly workflows from GitHub directory mappings. It reads the directory mapping JSON file and creates a Firefly workspace for each leaf directory (end directories with no subdirectories).

## Overview

This script (`use_github_mapping_in_firefly.py`) automates the creation of Firefly workflows by:
1. Reading the GitHub directory mapping JSON file
2. Extracting all leaf directories (end directories with no subdirectories)
3. Creating a Firefly workspace for each leaf directory using the Firefly API

## Prerequisites

Before running the Firefly workflow creation script, you need:

1. **Python 3.6+** installed
2. **`requests` library** installed (`pip install requests`)
3. **GitHub directory mapping JSON file** (`github_directory_mapping.json`) - generated by running `get_github_mapping.py`
4. **Firefly account** with API access
5. **Firefly Access Key and Secret Key** (see authentication section below)
6. **VCS Integration ID** from your Firefly account

## Complete Workflow: Step-by-Step Guide

### Step 1: Generate GitHub Directory Mapping

First, generate the directory mapping JSON file:

```bash
# Edit get_github_mapping.py and set REPOS_TO_MAP
python get_github_mapping.py
```

This creates `github_directory_mapping.json` with all repository directory structures.

### Step 2: Get Firefly Access and Secret Keys

#### How to Create Firefly Key Pair

1. **Log in to Firefly**
   - Go to your Firefly dashboard and sign in

2. **Navigate to Settings**
   - Click on **Settings** in the navigation menu

3. **Go to Users Section**
   - Click on **Users** in the settings menu

4. **Create Key Pair**
   - Click on **Create Key Pair**
   - Save both the **Access Key** and **Secret Key** immediately
   - ⚠️ **IMPORTANT**: You won't be able to see the secret key again!

5. **Generate Access Token** (Optional but Recommended)
   - Using the key pair, generate an access token
   - The access token is valid for **24 hours**
   - Note: The script automatically generates a token from your keys, so you can use the keys directly

### Step 3: Get VCS Integration ID

**Note**: Currently, the only way to get the VCS Integration ID is by using the browser's developer tools.

1. **Open Firefly Dashboard**
   - Go to your Firefly dashboard and navigate to **Integrations** or **Settings** → **Integrations**

2. **Open Developer Tools**
   - Press **F12** (or right-click → **Inspect**) to open developer tools
   - Click on the **Network** tab

3. **Find the VCS Integration ID**
   - In the Firefly dashboard, interact with your VCS integration (view, edit, or refresh the integrations page)
   - Look for API requests in the Network tab
   - Look in the **Response** or **Request** payload for a field like `integrationId`, or `vcsId`
   - The VCS Integration ID is typically a long alphanumeric string (e.g., `68f101a4ee25a38bc1b8a59b`)

**Example**: Look for responses like:
```json
{
  "id": "68f101a4ee25a38bc1b8a59b",
  "name": "GitHub Integration",
  "type": "github",
  ...
}
```

Copy the `id` value - this is your `VCS_ID`.

### Step 4: Configure the Script

Edit `use_github_mapping_in_firefly.py` and set the following hardcoded values:

```python
# Firefly API Authentication
ACCESS_KEY = "your-access-key-here"
SECRET_KEY = "your-secret-key-here"
# VCS Configuration
VCS_ID = "your-vcs-integration-id-here"
# VCS Type options: "github", "gitlab", "bitbucket", "codecommit", "azuredevops"
VCS_TYPE = "github"
DEFAULT_BRANCH = "main"
# Workspace Configuration
# Runner Type options: "github-actions", "gitlab-pipelines", "bitbucket-pipelines",
#                      "azure-pipelines", "jenkins", "semaphore", "atlantis",
#                      "env0", "firefly", "unrecognized"
RUNNER_TYPE = "firefly"
IAC_TYPE = "terraform"
TERRAFORM_VERSION = "1.5.7"
# Execution Configuration
EXECUTION_TRIGGERS = ["merge"]  # Options: ["merge", "push", "pull_request"]
APPLY_RULE = "manual"  # Options: "manual", "auto"
```

### Step 5: Run the Script

```bash
python use_github_mapping_in_firefly.py
```

The script will:
1. Authenticate with Firefly API using your access/secret keys
2. Load the GitHub directory mapping JSON
3. Extract all leaf directories from each repository
4. Create a Firefly workspace for each leaf directory
5. Save results to `firefly_workflows_created.json`

## How It Works

### Directory Selection Logic

The script only creates workspaces for **leaf directories** (end directories with no subdirectories).

**Example:**
```
Firefly-SE/firefly/
  └── aws/
      └── something/
          └── more/
              ├── nested/
              │   └── directories/  ← Leaf directory (creates workspace)
              └── 123/               ← Leaf directory (creates workspace)
```

**Workspaces Created:**
- `Firefly-SE/firefly/aws/something/more/nested/directories`
- `Firefly-SE/firefly/aws/something/more/123`

**NOT Created:**
- `aws` (has subdirectories)
- `aws/something` (has subdirectories)
- `aws/something/more` (has subdirectories)
- `aws/something/more/nested` (has subdirectories)

### Workspace Naming Convention

Each workspace is created with:
- **workspaceName**: `owner/repo/subdir` (e.g., `Firefly-SE/firefly/aws`)
- **repo**: `owner/repo` (e.g., `Firefly-SE/firefly`)
- **workDir**: `/subdir` (e.g., `/aws`)

## Configuration Options

All configuration is hardcoded at the top of `use_github_mapping_in_firefly.py`:

### Required Configuration

- `ACCESS_KEY`: Your Firefly access key
- `SECRET_KEY`: Your Firefly secret key
- `VCS_ID`: Your VCS integration ID

### Optional Configuration

- `VCS_TYPE`: VCS type (default: `"github"`)
  - **Valid options**: `"github"`, `"gitlab"`, `"bitbucket"`, `"codecommit"`, `"azuredevops"`
- `DEFAULT_BRANCH`: Default branch name (default: `"main"`)
- `RUNNER_TYPE`: Runner type (default: `"firefly"`)
  - **Valid options**: `"github-actions"`, `"gitlab-pipelines"`, `"bitbucket-pipelines"`, `"azure-pipelines"`, `"jenkins"`, `"semaphore"`, `"atlantis"`, `"env0"`, `"firefly"`, `"unrecognized"`
- `IAC_TYPE`: Infrastructure as Code type (default: `"terraform"`)
- `TERRAFORM_VERSION`: Terraform version (default: `"1.5.7"`)
- `EXECUTION_TRIGGERS`: When to trigger runs (default: `["merge"]`)
  - **Valid options**: `["merge"]`, `["push"]`, `["pull_request"]`, or combinations
- `APPLY_RULE`: Apply rule (default: `"manual"`)
  - **Valid options**: `"manual"`, `"auto"`
- `WORKSPACE_VARIABLES`: Array of workspace variables (default: `[]`)
  - Each variable object can have:
    - `key`: Variable name (string)
    - `value`: Variable value (string)
    - `sensitivity`: **Valid options**: `"string"`, `"secret"`
    - `destination`: **Valid options**: `"env"`, `"iac"`
- `PROJECT_ID`: Project ID or `None` for global access (default: `None`)

## Authentication Details

### Access Token Generation

The script automatically:
1. Uses your `ACCESS_KEY` and `SECRET_KEY` to authenticate
2. Calls `POST https://api.firefly.ai/api/v1.0/login`
3. Receives an `accessToken` (valid for 24 hours)
4. Uses the token for all subsequent API calls

### Token Validity

- Access tokens generated from key pairs are valid for **24 hours**
- The script generates a fresh token each time it runs
- If authentication fails, check that your keys are correct and not expired

## Troubleshooting

**Q: What are the valid runner types?**
A: Valid runner types are:
- `"github-actions"` - For GitHub Actions
- `"gitlab-pipelines"` - For GitLab CI/CD
- `"bitbucket-pipelines"` - For Bitbucket Pipelines
- `"azure-pipelines"` - For Azure DevOps Pipelines
- `"jenkins"` - For Jenkins
- `"semaphore"` - For Semaphore CI
- `"atlantis"` - For Atlantis
- `"env0"` - For Env0
- `"firefly"` - For Firefly runners
- `"unrecognized"` - For unrecognized CI/CD systems

**Q: What are the valid VCS types?**
A: Valid VCS types are:
- `"github"` - GitHub
- `"gitlab"` - GitLab
- `"bitbucket"` - Bitbucket
- `"codecommit"` - AWS CodeCommit
- `"azuredevops"` - Azure DevOps

**Q: What are the valid variable sensitivity options?**
A: Valid sensitivity options for workspace variables:
- `"string"` - Regular string variable
- `"secret"` - Secret/sensitive variable (will be masked)

**Q: What are the valid variable destination options?**
A: Valid destination options for workspace variables:
- `"env"` - Environment variable
- `"iac"` - Infrastructure as Code variable


## Complete Example Workflow

```bash
# Step 1: Generate GitHub mapping
python get_github_mapping.py
# Output: github_directory_mapping.json

# Step 2: Configure Firefly script (edit use_github_mapping_in_firefly.py)
# Set ACCESS_KEY, SECRET_KEY, VCS_ID, etc.

# Step 3: Create Firefly workflows
python use_github_mapping_in_firefly.py
# Output: firefly_workflows_created.json

# Step 4: Verify in Firefly dashboard
# Check that all workspaces were created successfully
```

## License

This script is provided as-is for Firefly workflow automation purposes.