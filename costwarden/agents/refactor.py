import difflib
from dataclasses import dataclass, field

from costwarden.models import Finding
from costwarden.tools import hcl
from costwarden.tools.tf_source import TfSource


@dataclass
class TfTarget:
    file: str
    address: str


def map_to_terraform(finding: Finding, files: dict[str, str]) -> TfTarget | None:
    """Find the Terraform block for a finding: by tf_address, else by resource id in the block."""
    if finding.tf_address:
        for path, text in files.items():
            if hcl.find_block(text, finding.tf_address):
                return TfTarget(path, finding.tf_address)
        return None
    for path, text in files.items():
        for addr in hcl.resource_addresses(text):
            span = hcl.find_block(text, addr)
            if span and finding.resource_id in text[span[0]:span[1]]:
                return TfTarget(path, addr)
    return None


def _edit(finding: Finding, target: TfTarget, files: dict[str, str]) -> str | None:
    """Return the new file text, or None (with the reason in the caller) if it cannot be edited."""
    text = files[target.file]
    start, end = hcl.find_block(text, target.address)
    block = text[start:end]
    if finding.action == "release":
        new_block = hcl.set_attribute(block, "count", 0)
    else:
        attr = hcl.RESIZE_ATTR.get(target.address.split(".")[0])
        if not attr or not finding.recommended:
            return None
        new_block = hcl.set_attribute(block, attr, finding.recommended)
    if new_block is None:
        return None
    return text[:start] + new_block + text[end:]


def refactor(findings: list[Finding], source: TfSource) -> dict:
    """Compute Terraform edits without writing anything. Returns a JSON-friendly result."""
    original = source.files()
    files = dict(original)
    edited: list[dict] = []
    unmapped: list[dict] = []
    for f in findings:
        target = map_to_terraform(f, files)
        if not target:
            unmapped.append({"finding": f.to_dict(), "reason": "No matching Terraform resource block"})
            continue
        new_text = _edit(f, target, files)
        if new_text is None:
            unmapped.append({"finding": f.to_dict(), "reason": f"Cannot edit {target.address} for action {f.action}"})
            continue
        files[target.file] = new_text
        edited.append({**f.to_dict(), "file": target.file, "address": target.address})
    changed = {p: t for p, t in files.items() if t != original[p]}
    diff = "".join(
        "".join(difflib.unified_diff(original[p].splitlines(True), t.splitlines(True), f"a/{p}", f"b/{p}"))
        for p, t in changed.items()
    )
    bad = [p for p, t in changed.items() if not hcl.parses(t)]
    return {
        "files": changed,
        "diff": diff,
        "edited": edited,
        "unmapped": unmapped,
        "validation_ok": not bad,
        "validation_note": f"Does not parse: {bad}" if bad else "Parsed with python-hcl2 (terraform validate not run)",
        "savings_usd": round(sum(e["monthly_savings_usd"] for e in edited), 2),
    }
