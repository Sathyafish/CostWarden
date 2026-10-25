from datetime import datetime, timedelta, timezone

import boto3

from costwarden.models import Finding

PRICING = {
    "ebs_gb_month": {"gp2": 0.10, "gp3": 0.08, "io1": 0.125, "st1": 0.045, "sc1": 0.015, "standard": 0.05},
    "snapshot_gb_month": 0.05,
    "eip_month": 3.65,
    "nat_month": 32.85,
}
IDLE_NAT_BYTES = 1_000_000_000  # under 1 GB out in 7 days counts as idle


def _arn(session: boto3.Session, account_id: str, kind: str, rid: str) -> str:
    return f"arn:aws:ec2:{session.region_name}:{account_id}:{kind}/{rid}"


def check_unattached_ebs(session: boto3.Session, account_id: str) -> list[Finding]:
    ec2 = session.client("ec2")
    out = []
    for page in ec2.get_paginator("describe_volumes").paginate(
        Filters=[{"Name": "status", "Values": ["available"]}]
    ):
        for v in page["Volumes"]:
            price = PRICING["ebs_gb_month"].get(v.get("VolumeType", "gp2"), 0.10)
            out.append(
                Finding(
                    account_id=account_id,
                    resource_type="EbsVolume",
                    resource_id=v["VolumeId"],
                    arn=_arn(session, account_id, "volume", v["VolumeId"]),
                    reason=f"Unattached {v.get('VolumeType')} volume of {v['Size']} GB",
                    monthly_savings_usd=round(v["Size"] * price, 2),
                    severity="low",
                )
            )
    return out


def check_unassociated_eips(session: boto3.Session, account_id: str) -> list[Finding]:
    ec2 = session.client("ec2")
    out = []
    for a in ec2.describe_addresses()["Addresses"]:
        if not (a.get("AssociationId") or a.get("InstanceId") or a.get("NetworkInterfaceId")):
            rid = a.get("AllocationId", a.get("PublicIp"))
            out.append(
                Finding(
                    account_id=account_id,
                    resource_type="ElasticIp",
                    resource_id=rid,
                    arn=_arn(session, account_id, "elastic-ip", rid),
                    reason="Elastic IP is not associated with any resource",
                    monthly_savings_usd=PRICING["eip_month"],
                    severity="low",
                )
            )
    return out


def check_idle_nat_gateways(session: boto3.Session, account_id: str) -> list[Finding]:
    ec2 = session.client("ec2")
    cw = session.client("cloudwatch")
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=7)
    out = []
    for nat in ec2.describe_nat_gateways(Filter=[{"Name": "state", "Values": ["available"]}])["NatGateways"]:
        nid = nat["NatGatewayId"]
        stats = cw.get_metric_statistics(
            Namespace="AWS/NATGateway",
            MetricName="BytesOutToDestination",
            Dimensions=[{"Name": "NatGatewayId", "Value": nid}],
            StartTime=start,
            EndTime=end,
            Period=86400,
            Statistics=["Sum"],
        )
        total = sum(p["Sum"] for p in stats["Datapoints"])
        if total < IDLE_NAT_BYTES:
            out.append(
                Finding(
                    account_id=account_id,
                    resource_type="NatGateway",
                    resource_id=nid,
                    arn=_arn(session, account_id, "natgateway", nid),
                    reason=f"NAT gateway moved {total / 1e6:.0f} MB in 7 days",
                    monthly_savings_usd=PRICING["nat_month"],
                    severity="medium",
                )
            )
    return out


def check_old_snapshots(session: boto3.Session, account_id: str, min_age_days: int = 90) -> list[Finding]:
    ec2 = session.client("ec2")
    cutoff = datetime.now(timezone.utc) - timedelta(days=min_age_days)
    out = []
    for page in ec2.get_paginator("describe_snapshots").paginate(OwnerIds=["self"]):
        for s in page["Snapshots"]:
            if s["StartTime"] <= cutoff:
                out.append(
                    Finding(
                        account_id=account_id,
                        resource_type="EbsSnapshot",
                        resource_id=s["SnapshotId"],
                        arn=_arn(session, account_id, "snapshot", s["SnapshotId"]),
                        reason=f"Snapshot of {s['VolumeSize']} GB older than {min_age_days} days",
                        monthly_savings_usd=round(s["VolumeSize"] * PRICING["snapshot_gb_month"], 2),
                        severity="medium",
                    )
                )
    return out
