"""
Firefly API Client - Thin client bound strictly to documented endpoints.
Handles auth headers, pagination, retries, and timeouts.
"""

import logging
import requests
from typing import Dict, List, Optional, Any, Iterator
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from urllib.parse import urljoin

logger = logging.getLogger(__name__)


class FireflyAPIError(Exception):
    """Custom exception for Firefly API errors"""
    pass


class FireflyClient:
    """
    Firefly API client that strictly follows documented endpoints and schemas.
    """
    
    def __init__(self, base_url: str, access_key: str, secret_key: str, timeout: int = 30):
        self.base_url = base_url.rstrip('/')
        self.access_key = access_key
        self.secret_key = secret_key
        self.timeout = timeout
        self.session = requests.Session()
        self.access_token = None
        
        # Authenticate on initialization
        self._authenticate()
    
    def _authenticate(self):
        """
        Authenticate with Firefly API using access key and secret key.
        Based on: .firefly-api/externalAPI.json
        """
        login_url = f"{self.base_url}/api/v1.0/login"
        payload = {
            "accessKey": self.access_key,
            "secretKey": self.secret_key
        }
        
        try:
            response = self.session.post(
                login_url,
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            auth_data = response.json()
            self.access_token = auth_data.get('accessToken')
            
            if not self.access_token:
                raise FireflyAPIError("No access token received from authentication endpoint")
            
            # Update session headers with the access token
            self.session.headers.update({
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            })
            
            logger.info("Successfully authenticated with Firefly API")
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Authentication failed: {e}")
            raise FireflyAPIError(f"Failed to authenticate with Firefly API: {e}")
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make HTTP request with proper error handling"""
        # No token validation - just use the token from initial authentication
        url = urljoin(self.base_url, endpoint)
        kwargs.setdefault('timeout', self.timeout)
        
        logger.debug(f"Making {method} request to {url}")
        
        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {e}")
            raise FireflyAPIError(f"API request failed: {e}")
    
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        retry=retry_if_exception_type((requests.exceptions.HTTPError, requests.exceptions.ConnectionError))
    )
    def _request_with_retry(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make request with exponential backoff retry for 429, 502, 503, 504"""
        response = self._make_request(method, endpoint, **kwargs)
        
        if response.status_code in [429, 502, 503, 504]:
            logger.warning(f"Received {response.status_code}, retrying...")
            raise requests.exceptions.HTTPError(f"Retryable status: {response.status_code}")
        
        return response
    
    def list_ebs_snapshots(self, account_id: Optional[str] = None, 
                           region: Optional[str] = None,
                           since: Optional[str] = None) -> Iterator[Dict[str, Any]]:
        """
        List EBS snapshots using Firefly API inventory endpoint.
        Based on: .firefly-api/externalAPI.json
        """
        endpoint = "/api/v1.0/inventory"
        
        # Build query payload based on Firefly API specification
        payload = {
            "assetTypes": ["aws_ebs_snapshot"],  # Filter by EBS snapshot asset type
            "size": 10000  # Maximum page size
        }
        
        # Add account filter if specified
        if account_id:
            payload["providerIds"] = [account_id]
        
        # Add date filter if specified
        if since:
            try:
                # Convert ISO date to epoch timestamp
                from datetime import datetime
                dt = datetime.fromisoformat(since.replace('Z', '+00:00'))
                payload["dayRangeEpoch"] = int(dt.timestamp())
            except ValueError:
                logger.warning(f"Invalid date format: {since}. Skipping date filter.")
        
        # Add region filter if specified (this would need to be implemented based on actual API behavior)
        # Note: The API spec doesn't show region filtering, so this might need adjustment
        
        logger.info(f"Using endpoint: {endpoint} for EBS snapshots")
        logger.info(f"Query payload: {payload}")
        
        # Implement pagination based on Firefly API specification
        after_key = None
        
        while True:
            if after_key:
                payload["afterKey"] = after_key
            
            response = self._request_with_retry('POST', endpoint, json=payload)
            data = response.json()
            
            # Extract snapshots from response
            snapshots = data.get('responseObjects', [])
            for snapshot in snapshots:
                yield snapshot
            
            # Check if there are more pages
            if not data.get('responseObjects') or len(data.get('responseObjects', [])) < payload.get('size', 10000):
                break
            
            # Get next page key
            after_key = data.get('afterKey')
            if not after_key:
                break
            
            logger.debug(f"Fetching next page with afterKey: {after_key}")
    
    def list_db_snapshots(self, account_id: Optional[str] = None,
                          region: Optional[str] = None,
                          since: Optional[str] = None) -> Iterator[Dict[str, Any]]:
        """
        List DB/RDS snapshots using Firefly API inventory endpoint.
        Based on: .firefly-api/externalAPI.json
        """
        endpoint = "/api/v1.0/inventory"
        
        # Build query payload based on Firefly API specification
        payload = {
            "assetTypes": ["aws_db_snapshot"],  # Filter by DB snapshot asset type
            "size": 10000  # Maximum page size
        }
        
        # Add account filter if specified
        if account_id:
            payload["providerIds"] = [account_id]
        
        # Add date filter if specified
        if since:
            try:
                # Convert ISO date to epoch timestamp
                from datetime import datetime
                dt = datetime.fromisoformat(since.replace('Z', '+00:00'))
                payload["dayRangeEpoch"] = int(dt.timestamp())
            except ValueError:
                logger.warning(f"Invalid date format: {since}. Skipping date filter.")
        
        logger.info(f"Using endpoint: {endpoint} for DB snapshots")
        logger.info(f"Query payload: {payload}")
        
        # Implement pagination based on Firefly API specification
        after_key = None
        
        while True:
            if after_key:
                payload["afterKey"] = after_key
            
            response = self._request_with_retry('POST', endpoint, json=payload)
            data = response.json()
            
            # Extract snapshots from response
            snapshots = data.get('responseObjects', [])
            for snapshot in snapshots:
                yield snapshot
            
            # Check if there are more pages
            if not data.get('responseObjects') or len(data.get('responseObjects', [])) < payload.get('size', 10000):
                break
            
            # Get next page key
            after_key = data.get('afterKey')
            if not after_key:
                break
            
            logger.debug(f"Fetching next page with afterKey: {after_key}")
    
    def list_ec2_instances(self, account_id: Optional[str] = None, region: Optional[str] = None, since: Optional[str] = None) -> Iterator[Dict[str, Any]]:
        """
        List EC2 instances using Firefly API inventory endpoint.
        Based on: .firefly-api/externalAPI.json
        """
        endpoint = "/api/v1.0/inventory"
        
        # Build query payload
        payload = {
            "assetTypes": ["aws_instance"],
            "size": 10000
        }
        
        # Add account filter if specified
        if account_id:
            payload["providerIds"] = [account_id]
        
        # Add date filter if specified
        if since:
            from datetime import datetime
            dt = datetime.fromisoformat(since.replace('Z', '+00:00'))
            payload["dayRangeEpoch"] = int(dt.timestamp())
        
        # Handle pagination
        after_key = None
        while True:
            if after_key:
                payload["afterKey"] = after_key
            
            try:
                response = self._request_with_retry('POST', endpoint, json=payload)
                data = response.json()
                
                instances = data.get('responseObjects', [])
                for instance in instances:
                    yield instance
                
                # Check if we need to continue pagination
                if not data.get('responseObjects') or len(data.get('responseObjects', [])) < payload.get('size', 10000):
                    break
                
                after_key = data.get('afterKey')
                if not after_key:
                    break
                    
            except FireflyAPIError as e:
                logger.error(f"Error listing EC2 instances: {e}")
                break

    def get_ec2_instance(self, instance_id: str, account_id: Optional[str] = None,
                         region: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get EC2 instance details using Firefly API inventory endpoint.
        Based on: .firefly-api/externalAPI.json
        """
        endpoint = "/api/v1.0/inventory"
        
        # Build query payload to find the specific EC2 instance
        payload = {
            "assetTypes": ["aws_instance"],  # Filter by EC2 instance asset type
            "names": [instance_id],  # Search by name/ID
            "size": 1000
        }
        
        # Add account filter if specified
        if account_id:
            payload["providerIds"] = [account_id]
        
        try:
            response = self._request_with_retry('POST', endpoint, json=payload)
            data = response.json()
            
            # Return the first matching instance
            instances = data.get('responseObjects', [])
            if instances:
                return instances[0]
            else:
                logger.debug(f"Could not resolve EC2 instance {instance_id} (instance_id) (this is normal for deleted instances)")
                return None
                
        except FireflyAPIError:
            logger.debug(f"Could not resolve EC2 instance {instance_id} (this is normal for deleted instances)")
            return None
    
    def get_db_instance(self, instance_id: str, account_id: Optional[str] = None,
                        region: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get DB instance details using Firefly API inventory endpoint.
        Based on: .firefly-api/externalAPI.json
        """
        endpoint = "/api/v1.0/inventory"
        
        # Build query payload to find the specific DB instance
        payload = {
            "assetTypes": ["aws_db_instance"],  # Filter by DB instance asset type
            "names": [instance_id],  # Search by name/ID
            "size": 1000
        }
        
        # Add account filter if specified
        if account_id:
            payload["providerIds"] = [account_id]
        
        try:
            response = self._request_with_retry('POST', endpoint, json=payload)
            data = response.json()
            
            # Return the first matching instance
            instances = data.get('responseObjects', [])
            if instances:
                return instances[0]
            else:
                logger.debug(f"Could not resolve DB instance {instance_id} (this is normal for deleted instances)")
                return None
                
        except FireflyAPIError:
            logger.debug(f"Could not resolve DB instance {instance_id} (this is normal for deleted instances)")
            return None
    
    def list_ebs_volumes(self, account_id: Optional[str] = None, region: Optional[str] = None, since: Optional[str] = None) -> Iterator[Dict[str, Any]]:
        """
        List EBS volumes using Firefly API inventory endpoint.
        Based on: .firefly-api/externalAPI.json
        """
        endpoint = "/api/v1.0/inventory"
        
        # Build query payload
        payload = {
            "assetTypes": ["aws_ebs_volume"],
            "size": 10000
        }
        
        # Add account filter if specified
        if account_id:
            payload["providerIds"] = [account_id]
        
        # Add date filter if specified
        if since:
            from datetime import datetime
            dt = datetime.fromisoformat(since.replace('Z', '+00:00'))
            payload["dayRangeEpoch"] = int(dt.timestamp())
        
        # Handle pagination
        after_key = None
        while True:
            if after_key:
                payload["afterKey"] = after_key
            
            try:
                response = self._request_with_retry('POST', endpoint, json=payload)
                data = response.json()
                
                volumes = data.get('responseObjects', [])
                for volume in volumes:
                    yield volume
                
                # Check if we need to continue pagination
                if not data.get('responseObjects') or len(data.get('responseObjects', [])) < payload.get('size', 10000):
                    break
                
                after_key = data.get('afterKey')
                if not after_key:
                    break
                    
            except FireflyAPIError as e:
                logger.error(f"Error listing EBS volumes: {e}")
                break
    
    def get_volumes_batch(self, volume_ids: List[str], account_id: Optional[str] = None,
                          region: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """
        Batch fetch multiple volumes in a single API call.
        This dramatically reduces API calls when processing many snapshots.
        """
        if not volume_ids:
            return {}
        
        endpoint = "/api/v1.0/inventory"
        
        # Build query payload for multiple volumes
        payload = {
            "assetTypes": ["aws_ebs_volume"],
            "size": 10000,  # Large size to get all volumes
            "filters": {
                "resourceId": {"$in": volume_ids}
            }
        }
        
        if account_id:
            payload["providerIds"] = [account_id]
        
        try:
            response = self._request_with_retry('POST', endpoint, json=payload)
            data = response.json()
            
            volumes = data.get('responseObjects', [])
            volume_map = {vol.get('resourceId'): vol for vol in volumes}
            
            logger.debug(f"Batch fetched {len(volume_map)} volumes out of {len(volume_ids)} requested")
            return volume_map
            
        except Exception as e:
            logger.error(f"Error batch fetching volumes: {e}")
            return {}
    
    def get_ec2_instance_details(self, instance_id: str, account_id: Optional[str] = None,
                                region: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get EC2 instance details by ID using Firefly API inventory endpoint.
        """
        endpoint = "/api/v1.0/inventory"
        
        payload = {
            "assetTypes": ["aws_ec2_instance"],
            "size": 1000,
            "filters": {
                "resourceId": instance_id
            }
        }
        
        if account_id:
            payload["providerIds"] = [account_id]
        
        try:
            response = self._request_with_retry('POST', endpoint, json=payload)
            data = response.json()
            
            instances = data.get('responseObjects', [])
            if instances:
                instance = instances[0]
                return instance
            
            return None
            
        except Exception as e:
            logger.error(f"Error fetching instance {instance_id}: {e}")
            return None
    
    def get_ec2_instances_batch(self, account_id: Optional[str] = None,
                                region: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Fetch all EC2 instances in a single call.
        This eliminates the need to call list_ec2_instances multiple times.
        """
        endpoint = "/api/v1.0/inventory"
        
        payload = {
            "assetTypes": ["aws_ec2_instance"],
            "size": 10000
        }
        
        if account_id:
            payload["providerIds"] = [account_id]
        
        try:
            response = self._request_with_retry('POST', endpoint, json=payload)
            data = response.json()
            
            instances = data.get('responseObjects', [])
            
            return instances
            
        except Exception as e:
            logger.error(f"Error batch fetching EC2 instances: {e}")
            return []

    def get_volume_details(self, volume_id: str, account_id: Optional[str] = None,
                           region: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get EBS volume details to resolve parent EC2 instance.
        Based on: .firefly-api/externalAPI.json
        """
        endpoint = "/api/v1.0/inventory"
        
        # Build query payload to find the specific EBS volume
        payload = {
            "assetTypes": ["aws_ebs_volume"],  # Filter by EBS volume asset type
            "names": [volume_id],  # Search by name/ID
            "size": 1000
        }
        
        # Add account filter if specified
        if account_id:
            payload["providerIds"] = [account_id]
        
        try:
            response = self._request_with_retry('POST', endpoint, json=payload)
            data = response.json()
            
            # Return the first matching volume
            volumes = data.get('responseObjects', [])
            if volumes:
                return volumes[0]
            else:
                logger.debug(f"Could not resolve volume {volume_id} (this is normal for unattached or deleted volumes)")
                return None
                
        except FireflyAPIError:
            logger.debug(f"Could not resolve volume {volume_id} (this is normal for unattached or deleted volumes)")
            return None
