import os

import boto3
import pytest
from moto import mock_aws

os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")


@pytest.fixture
def aws():
    with mock_aws():
        yield


@pytest.fixture
def seeded_aws(aws):
    ec2 = boto3.client("ec2", region_name="us-east-1")
    ec2.create_volume(AvailabilityZone="us-east-1a", Size=100, VolumeType="gp2")  # unattached
    attached_vol = ec2.create_volume(AvailabilityZone="us-east-1a", Size=10, VolumeType="gp3")["VolumeId"]
    image = ec2.describe_images()["Images"][0]["ImageId"]
    inst = ec2.run_instances(ImageId=image, MinCount=1, MaxCount=1)["Instances"][0]["InstanceId"]
    ec2.attach_volume(VolumeId=attached_vol, InstanceId=inst, Device="/dev/sdh")
    ec2.allocate_address(Domain="vpc")  # unassociated
    vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")["Vpc"]["VpcId"]
    subnet = ec2.create_subnet(VpcId=vpc, CidrBlock="10.0.1.0/24")["Subnet"]["SubnetId"]
    alloc = ec2.allocate_address(Domain="vpc")["AllocationId"]
    ec2.create_nat_gateway(SubnetId=subnet, AllocationId=alloc)
    vol = ec2.create_volume(AvailabilityZone="us-east-1a", Size=50)["VolumeId"]
    ec2.create_snapshot(VolumeId=vol)
    return ec2
