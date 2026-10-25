import json
import logging
import re

from costwarden.llm import llm_text
from costwarden.models import Finding

log = logging.getLogger(__name__)

RANK_PROMPT = """You rank cloud cost findings for review: highest savings and lowest risk first.
Findings:
{items}
Respond with a JSON list of resource ids, most important first. No other text."""

SUMMARY_PROMPT = """You are a cloud cost reviewer. Write 3 to 4 sentences of risk summary for a pull request
that makes these changes in AWS account {account}. Mention restarts, reversibility and anything to verify.
Changes:
{changes}"""


def rank_findings(llm, findings: list[Finding]) -> list[Finding]:
    """Order findings with the LLM; ignore unknown ids and keep any the model omitted."""
    if len(findings) < 2:
        return list(findings)
    items = "\n".join(f"- {f.resource_id} {f.action} ${f.monthly_savings_usd:.2f}/mo risk={f.severity}: {f.reason}"
                      for f in findings)
    try:
        text = llm_text(llm, RANK_PROMPT.format(items=items))
        m = re.search(r"\[.*\]", text, re.S)
        order = json.loads(m.group(0)) if m else []
    except Exception as e:  # noqa: BLE001 - ranking is best effort
        log.warning("ranking failed: %s", e)
        return list(findings)
    by_id = {f.resource_id: f for f in findings}
    ranked = [by_id[i] for i in order if isinstance(i, str) and i in by_id]
    seen = {f.resource_id for f in ranked}
    return ranked + [f for f in findings if f.resource_id not in seen]


def write_risk_summary(llm, account_name: str, result: dict) -> str:
    changes = "\n".join(
        f"- {e['resource_id']} ({e['address']}): {e['action']}"
        + (f" {e.get('current')} -> {e['recommended']}" if e["action"] == "resize" else "")
        + f", saves ${e['monthly_savings_usd']:.2f}/mo, risk {e['severity']}"
        for e in result["edited"]
    )
    return llm_text(llm, SUMMARY_PROMPT.format(account=account_name, changes=changes)).strip()
