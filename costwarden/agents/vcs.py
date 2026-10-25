from datetime import datetime, timezone

from costwarden.accounts import Account
from costwarden.tools.github_client import GitHubClient


def branch_name(account: Account, today: str | None = None) -> str:
    today = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"costwarden/cleanup-{today}-{account.id}"


def build_pr_body(account: Account, result: dict, summary: str) -> str:
    lines = [
        f"## CostWarden cleanup for {account.name} ({account.id})",
        "",
        f"**Estimated monthly savings: ${result['savings_usd']:,.2f}**",
        "",
        "| Resource | Action | Change | Savings/mo | Risk |",
        "|---|---|---|---|---|",
    ]
    for e in result["edited"]:
        change = f"{e.get('current')} → {e['recommended']}" if e["action"] == "resize" else "count = 0"
        lines.append(f"| `{e['resource_id']}` ({e['address']}) | {e['action']} | {change} | "
                     f"${e['monthly_savings_usd']:,.2f} | {e['severity']} |")
    if result["unmapped"]:
        lines += ["", "### Not changed (no matching Terraform)"]
        lines += [f"- `{u['finding']['resource_id']}`: {u['reason']}" for u in result["unmapped"]]
    lines += ["", "### Risk summary", summary or "_not generated_", "",
              "Opened as a draft by CostWarden after human approval of the diff. Merge to continue."]
    return "\n".join(lines)


def open_pull_request(account: Account, result: dict, summary: str, client: GitHubClient,
                      today: str | None = None) -> str:
    branch = branch_name(account, today)
    client.create_branch(branch)
    prefix = account.tf_path.rstrip("/") + "/" if account.tf_path else ""
    files = {prefix + p: t for p, t in result["files"].items()}  # repo-relative paths
    client.commit_files(branch, files, f"CostWarden: cleanup for {account.name}")
    title = f"CostWarden: cleanup for {account.name} (${result['savings_usd']:,.0f}/mo)"
    return client.open_pr(branch, title, build_pr_body(account, result, summary), draft=True)
