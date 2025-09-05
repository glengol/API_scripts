#!/usr/bin/env python3
"""
Debug script to test the specific volume resolution case
"""

import os
from firefly_client import FireflyClient

def debug_specific_case():
    """Debug the specific volume resolution case step by step"""
    
    # Get credentials from environment
    access_key = os.getenv('FIREFLY_ACCESS_KEY')
    secret_key = os.getenv('FIREFLY_SECRET_KEY')
    
    if not access_key or not secret_key:
        print("❌ Please set FIREFLY_ACCESS_KEY and FIREFLY_SECRET_KEY environment variables")
        return
    
    # Initialize client
    client = FireflyClient(
        base_url="https://api.firefly.ai",
        access_key=access_key,
        secret_key=secret_key
    )
    
    print("🔍 Debugging Specific Volume Resolution Case")
    print("=" * 60)
    
    # The problematic snapshot
    volume_id = "vol-0b27fa2fe4949f42b"
    account_id = "096103536687"
    
    print(f"\n📸 **Target Volume:** {volume_id}")
    print(f"📸 **Account:** {account_id}")
    
    # Step 1: Get the volume details
    print(f"\n🔍 **Step 1: Getting Volume Details**")
    print("-" * 40)
    
    try:
        volume = client.get_volume_details(volume_id, account_id, None)
        if volume:
            print(f"✅ Found volume {volume_id}")
            print(f"  - assetId: {volume.get('assetId')}")
            print(f"  - resourceId: {volume.get('resourceId')}")
            print(f"  - providerId: {volume.get('providerId')}")
            print(f"  - attachments: {volume.get('attachments', [])}")
            print(f"  - tfObject.attachments: {volume.get('tfObject', {}).get('attachments', [])}")
        else:
            print(f"❌ Volume {volume_id} not found")
            return
    except Exception as e:
        print(f"❌ Error getting volume: {e}")
        return
    
    # Step 2: Search for instances in the same account
    print(f"\n🔍 **Step 2: Searching for Instances in Account {account_id}**")
    print("-" * 40)
    
    try:
        instances = list(client.list_ec2_instances(account_id, None, None))
        print(f"✅ Found {len(instances)} instances in account {account_id}")
        
        # Look for instances that reference this volume
        matching_instances = []
        for instance in instances:
            ebs_devices = instance.get('tfObject', {}).get('ebs_block_device', [])
            for device in ebs_devices:
                if device.get('volume_id') == volume_id:
                    matching_instances.append({
                        'instance_id': instance.get('resourceId'),
                        'device_name': device.get('device_name'),
                        'volume_size': device.get('volume_size')
                    })
        
        if matching_instances:
            print(f"✅ Found {len(matching_instances)} instances referencing volume {volume_id}:")
            for match in matching_instances:
                print(f"  - Instance: {match['instance_id']}")
                print(f"    Device: {match['device_name']}")
                print(f"    Volume Size: {match['volume_size']}GB")
        else:
            print(f"❌ No instances found referencing volume {volume_id}")
            
            # Show some sample instances and their EBS devices
            print(f"\n🔍 **Sample Instances and EBS Devices:**")
            for i, instance in enumerate(instances[:3]):
                print(f"  Instance {i+1}: {instance.get('resourceId')}")
                ebs_devices = instance.get('tfObject', {}).get('ebs_block_device', [])
                if ebs_devices:
                    for device in ebs_devices:
                        print(f"    - {device.get('device_name')} -> {device.get('volume_id')} ({device.get('volume_size')}GB)")
                else:
                    print(f"    - No EBS devices")
        
    except Exception as e:
        print(f"❌ Error searching instances: {e}")
        return
    
    print(f"\n" + "=" * 60)
    print(f"🔍 **Analysis Complete**")

if __name__ == "__main__":
    debug_specific_case()
