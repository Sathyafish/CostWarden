import json
import re
from dataclasses import dataclass

from costwarden.llm import llm_text
from costwarden.store import Store
from costwarden.tools import store_tools as t

TOOLS = {
    "last_cleanup": "Most recent cleanup. args: account_id (optional)",
    "savings_between": "Total monthly cost avoided by merged cleanups. args: start, end (ISO timestamps, optional), account_id (optional)",
    "cleanups_by_status": "List cleanups with a status. args: status (proposed|merged|rejected|failed)",
    "top_resource_types": "Resource types ranked by cost avoided by merged cleanups. args: n (optional)",
}
PROMPT = """You answer questions about past cloud cost cleanups by choosing ONE tool.
tools:
{tools}
Respond with JSON only: {{"tool": "<name>", "args": {{...}}}}
Question: {question}"""
HELP = ("I can answer questions about past cleanups, for example: what was the last cleanup, how much cost was "
        "avoided in total, which cleanups are open, or which resource types save the most.")


@dataclass
class Answer:
    text: str
    tool: str | None = None
    data: object = None


def _money(x: float) -> str:
    return f"${x:,.2f}"


def _render(tool: str, data, args: dict) -> str:
    if tool == "last_cleanup":
        if not data:
            return "There are no cleanups recorded yet."
        note = "" if data["status"] == "merged" else f" (estimate; status is {data['status']}, not yet merged)"
        pr = f" PR: {data['pr_url']}." if data["pr_url"] else ""
        return (f"The last cleanup was for account {data['account_id']} on {data['timestamp']}, status "
                f"{data['status']}. It {'avoids' if data['status'] == 'merged' else 'would avoid'} "
                f"{_money(data['monthly_savings_usd'])} per month{note}.{pr} Resources: {', '.join(data['resources'])}.")
    if tool == "savings_between":
        scope = f" for account {data['account_id']}" if data["account_id"] else ""
        return (f"Merged cleanups{scope} avoid {_money(data['monthly_savings_usd'])} per month across "
                f"{data['cleanups']} cleanup(s).")
    if tool == "cleanups_by_status":
        if not data:
            return f"No cleanups with status {args.get('status')}."
        return f"{len(data)} cleanup(s) with status {args.get('status')}: " + "; ".join(
            f"{d['account_id']} {_money(d['monthly_savings_usd'])}/mo" + (f" {d['pr_url']}" if d["pr_url"] else "")
            for d in data)
    if tool == "top_resource_types":
        if not data:
            return "No resource data yet."
        return "Top resource types by savings: " + "; ".join(
            f"{d['resource_type']} {_money(d['savings'])}/mo ({d['count']})" for d in data)
    return HELP


def answer(question: str, store: Store, llm) -> Answer:
    try:
        text = llm_text(llm, PROMPT.format(tools="\n".join(f"- {k}: {v}" for k, v in TOOLS.items()), question=question))
        m = re.search(r"\{.*\}", text, re.S)
        call = json.loads(m.group(0))
        tool, args = call["tool"], call.get("args") or {}
        if tool not in TOOLS or not isinstance(args, dict):
            raise ValueError(f"unknown tool {tool}")
    except Exception:  # noqa: BLE001 - unparseable output or LLM down
        return Answer(HELP)
    account = args.get("account_id")
    if account and not store.list_cleanups(account):
        return Answer(f"There are no cleanups recorded for account {account}.", tool, None)
    try:
        if tool == "last_cleanup":
            data = t.last_cleanup(store, account)
        elif tool == "savings_between":
            data = t.savings_between(store, args.get("start"), args.get("end"), account)
        elif tool == "cleanups_by_status":
            data = t.cleanups_by_status(store, str(args.get("status", "")))
        else:
            data = t.top_resource_types(store, int(args.get("n", 3)))
    except (TypeError, ValueError):
        return Answer(HELP)
    return Answer(_render(tool, data, args), tool, data)
