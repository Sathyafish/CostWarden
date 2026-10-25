from costwarden.accounts import Account, get_session
from costwarden.models import Finding
from costwarden.resilience import with_retry
from costwarden.tools import aws_checks, cost_explorer


def discover(account: Account) -> list[Finding]:
    findings: list[Finding] = []
    if "aws" in account.sources:
        def run_aws():
            session = get_session(account)
            out: list[Finding] = []
            out += aws_checks.check_unattached_ebs(session, account.id)
            out += aws_checks.check_unassociated_eips(session, account.id)
            out += aws_checks.check_idle_nat_gateways(session, account.id)
            out += aws_checks.check_old_snapshots(session, account.id)
            return out

        findings += with_retry(run_aws)
    if "cost_explorer" in account.sources:
        if not account.data_file:
            raise ValueError(f"Account {account.id} uses cost_explorer but has no data_file")
        findings += cost_explorer.load_findings(account.data_file, account.id)
    return findings
