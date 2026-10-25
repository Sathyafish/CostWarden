import json

from costwarden.models import Finding


def _tf_address(tags) -> str | None:
    if isinstance(tags, dict):
        return tags.get("tf_address")
    for t in tags or []:
        if t.get("Key") == "tf_address":
            vals = t.get("Values") or []
            return vals[0] if vals else None
    return None


def _severity(action: str, restart: bool, effort: str, rollback: bool) -> str:
    if action == "resize" and (restart or effort in ("High", "VeryHigh")):
        return "high" if effort in ("High", "VeryHigh") else "medium"
    if action == "resize" or not rollback or effort == "Medium":
        return "medium"
    return "low"


def load_findings(path: str, account_id: str) -> list[Finding]:
    """Map a Cost Explorer / Cost Optimization Hub style export to findings for one account."""
    with open(path) as f:
        data = json.load(f)
    out: list[Finding] = []

    for r in data.get("rightsizing", {}).get("RightsizingRecommendations", []):
        if r.get("AccountId") != account_id:
            continue
        cur = r["CurrentInstance"]
        ec2d = cur["ResourceDetails"]["EC2ResourceDetails"]
        rid = cur["ResourceId"]
        arn = f"arn:aws:ec2:{ec2d['Region']}:{account_id}:instance/{rid}"
        cpu = cur["ResourceUtilization"]["EC2ResourceUtilization"]["MaxCpuUtilizationPercentage"]
        if r["RightsizingType"] == "TERMINATE":
            sav = float(r["TerminateRecommendationDetail"]["EstimatedMonthlySavings"])
            out.append(Finding(account_id, "EC2Instance", rid, arn,
                               f"{cur.get('InstanceName')} idle: max CPU {cpu}% over lookback",
                               sav, "medium", "release", ec2d["InstanceType"], None, _tf_address(cur.get("Tags"))))
        else:
            tgt = r["ModifyRecommendationDetail"]["TargetInstances"][0]
            sav = float(tgt["EstimatedMonthlySavings"])
            out.append(Finding(account_id, "EC2Instance", rid, arn,
                               f"{cur.get('InstanceName')} over-provisioned: max CPU {cpu}%",
                               sav, "medium", "resize", ec2d["InstanceType"],
                               tgt["ResourceDetails"]["EC2ResourceDetails"]["InstanceType"],
                               _tf_address(cur.get("Tags"))))

    for h in data.get("optimizationHub", {}).get("items", []):
        if h.get("accountId") != account_id:
            continue
        action = "release" if h["actionType"] == "Delete" else "resize"
        rec = h["recommendedResourceSummary"].split()[0] if action == "resize" else None
        cur_summary = h["currentResourceSummary"]
        out.append(Finding(account_id, h["currentResourceType"], h["resourceId"], h["resourceArn"],
                           cur_summary, float(h["estimatedMonthlySavings"]),
                           _severity(action, h.get("restartNeeded", False), h.get("implementationEffort", "Low"),
                                     h.get("rollbackPossible", True)),
                           action, cur_summary.split(",")[0].split()[0], rec, _tf_address(h.get("tags"))))
    return out
