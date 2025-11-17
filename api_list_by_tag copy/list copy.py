#!/usr/bin/env python3
"""
Script to list all assets with the governance filter "IAM Role Allows All Principals To Assume"
"""

import requests
from typing import Optional, List, Union

# Firefly API configuration
FIREFLY_BASE_URL = 'https://api.firefly.ai'
FIREFLY_ACCESS_KEY = "INFLHUEQXXZTNCCRNMRD"
FIREFLY_SECRET_KEY = "MBBbddjkvcbL424Y31PzcSD960PO9LFTYKQZQe8j4SUiZrl0ihHyCGV80ltNsYwi"
GOVERNANCE_FILTER_ID = "67db0b0e1e658a9f6bff13c8"

def authenticate(access_key: str, secret_key: str) -> Optional[str]:
    """
    Authenticate with Firefly API and return access token.
    
    Args:
        access_key: Firefly API access key
        secret_key: Firefly API secret key
    
    Returns:
        Access token if successful, None otherwise
    """
    try:
        response = requests.post(
            f'{FIREFLY_BASE_URL}/v2/login',
            json={
                'accessKey': access_key,
                'secretKey': secret_key
            }
        )
        response.raise_for_status()
        data = response.json()
        return data.get('accessToken')
    except requests.exceptions.RequestException as e:
        print(f'❌ Authentication error: {e}')
        if hasattr(e, 'response') and e.response is not None:
            print(f'   Response: {e.response.text}')
        return None

def get_policy_by_id(access_token: str, policy_id: str) -> Optional[dict]:
    """
    Get governance policy details by ID.
    
    Args:
        access_token: Firefly API access token
        policy_id: The governance policy ID
    
    Returns:
        Policy object with name and other details, or None if not found
    """
    try:
        response = requests.post(
            f'{FIREFLY_BASE_URL}/v2/governance/insights',
            json={
                'id': [policy_id],
                'onlyMatchingAssets': True
            },
            headers={
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
        )
        response.raise_for_status()
        data = response.json()
        
        # The response should have a 'hits' or 'data' field with the policies
        policies = data.get('hits', []) or data.get('data', [])
        if policies and len(policies) > 0:
            return policies[0]
        return None
    except requests.exceptions.RequestException as e:
        print(f'❌ Error fetching policy: {e}')
        if hasattr(e, 'response') and e.response is not None:
            print(f'   Response: {e.response.text}')
        return None

def _fetch_arns_for_state(
    access_token: str,
    policy_name: str,
    policy_type: Optional[List[str]],
    asset_state: str
) -> List[str]:
    """
    Helper function to fetch ARNs for a single asset state with pagination.
    
    Args:
        access_token: Firefly API access token
        policy_name: The governance policy name
        policy_type: The asset types to filter by
        asset_state: Single asset state to fetch
    
    Returns:
        List of ARNs for the specified asset state
    """
    all_arns = []
    after_key = None
    page_count = 0
    
    print(f'   🔍 Fetching assets with state: "{asset_state}"')
    
    while True:
        page_count += 1
        print(f'      📄 Fetching page {page_count}...', end=' ')
        
        # Prepare request body - use policy name and type
        request_body = {
            'governance': policy_name,
            'assetState': asset_state
        }
        
        # Add asset type filter if available (policy_type is already an array)
        if policy_type:
            request_body['assetTypes'] = policy_type
        
        if after_key:
            request_body['afterKey'] = after_key
        
        try:
            response = requests.post(
                f'{FIREFLY_BASE_URL}/api/v1.0/inventory',
                json=request_body,
                headers={
                    'Authorization': f'Bearer {access_token}',
                    'Content-Type': 'application/json'
                }
            )
            response.raise_for_status()
            data = response.json()
            
            # Extract assets from response
            response_objects = data.get('responseObjects', [])
            if response_objects:
                # Extract ARNs from assets
                for asset in response_objects:
                    arn = asset.get('arn') or asset.get('resourceId') or asset.get('assetId')
                    if arn:
                        all_arns.append(arn)
                print(f'✓ Found {len(response_objects)} assets (Total ARNs: {len(all_arns)})')
            else:
                print('✓ No more assets')
            
            # Check for next page
            after_key = data.get('afterKey')
            if not after_key:
                print(f'      ✅ State "{asset_state}" complete. Found {len(all_arns)} ARNs\n')
                break
                
        except requests.exceptions.RequestException as e:
            print(f'\n      ❌ Error fetching assets for state "{asset_state}": {e}')
            if hasattr(e, 'response') and e.response is not None:
                print(f'         Response: {e.response.text}')
            break
    
    return all_arns

def get_asset_arns_with_governance_filter(
    access_token: str,
    governance_filter_id: str,
    asset_state: Union[str, List[str]] = ["managed", "unmanaged", "ghost", "modified"]
) -> List[str]:
    """
    Fetch all asset ARNs matching a specific governance filter ID.
    First gets the policy name from the ID, then uses it to filter inventory.
    
    Args:
        access_token: Firefly API access token
        governance_filter_id: The governance policy ID to filter by
        asset_state: Asset state filter(s). Can be a single string or a list of strings.
                    Valid values: "managed", "unmanaged", "ghost", "modified"
                    Default: "managed"
    
    Returns:
        List of ARNs for assets matching the governance filter (deduplicated)
    """
    # First, get the policy details by ID to get the policy name
    print(f'🔍 Getting policy details for ID: "{governance_filter_id}"')
    policy = get_policy_by_id(access_token, governance_filter_id)
    
    if not policy:
        print('❌ Policy not found')
        return []
    
    policy_name = policy.get('name')
    policy_type = policy.get('type')
    total_assets = policy.get('total_assets', 0)
    
    print(f'✅ Found policy: "{policy_name}"')
    print(f'   Type: {policy_type}')
    print(f'   Expected assets: {total_assets}\n')
    
    # Normalize asset_state to a list
    if isinstance(asset_state, str):
        asset_states = [asset_state]
    else:
        asset_states = asset_state
    
    print(f'🔍 Fetching assets with governance filter: "{policy_name}"')
    print(f'   Asset states to fetch: {", ".join(asset_states)}\n')
    
    # Fetch ARNs for each state and combine
    all_arns_set = set()  # Use set to avoid duplicates
    for state in asset_states:
        arns = _fetch_arns_for_state(access_token, policy_name, policy_type, state)
        all_arns_set.update(arns)
    
    # Convert back to list and return
    all_arns = list(all_arns_set)
    print(f'✅ All states complete. Total unique ARNs: {len(all_arns)}')
    
    return all_arns

def print_arns(arns: List[str]):
    """
    Print all ARNs.
    
    Args:
        arns: List of ARN strings
    """
    if not arns:
        print('\n📭 No assets found matching the governance filter.')
        return
    
    print(f'\n📊 Found {len(arns)} asset ARNs:\n')
    for arn in arns:
        print(arn)

def main():
    """Main function to list asset ARNs with governance filter."""
    # Authenticate using hardcoded credentials
    print('🔐 Authenticating with Firefly API...')
    access_token = authenticate(FIREFLY_ACCESS_KEY, FIREFLY_SECRET_KEY)
    
    if not access_token:
        print('❌ Authentication failed')
        return
    
    print('✅ Authentication successful\n')
    
    # Get asset ARNs with hardcoded governance filter ID
    arns = get_asset_arns_with_governance_filter(access_token, GOVERNANCE_FILTER_ID)
    
    # Print all ARNs
    print_arns(arns)
    
    # Save ARNs to a text file
    if arns:
        output_file = 'asset_arns.txt'
        with open(output_file, 'w') as f:
            for arn in arns:
                f.write(f'{arn}\n')
        print(f'\n💾 ARNs saved to: {output_file}')

if __name__ == '__main__':
    main()

