import re

import hcl2

RESIZE_ATTR = {
    "aws_instance": "instance_type",
    "aws_db_instance": "instance_class",
    "aws_ebs_volume": "type",
}


def resource_addresses(text: str) -> set[str]:
    """Addresses (type.name) of resource blocks in the text, parsed with python-hcl2."""
    data = hcl2.loads(text)
    out = set()
    for block in data.get("resource", []):
        for rtype, named in block.items():
            for name in named:
                out.add(f"{rtype.strip(chr(34))}.{name.strip(chr(34))}")
    return out


def parses(text: str) -> bool:
    try:
        hcl2.loads(text)
        return True
    except Exception:  # noqa: BLE001
        return False


def find_block(text: str, address: str) -> tuple[int, int] | None:
    """Return (start, end) offsets of the resource block, end exclusive."""
    rtype, name = address.split(".", 1)
    m = re.search(rf'^resource\s+"{re.escape(rtype)}"\s+"{re.escape(name)}"\s*\{{', text, re.M)
    if not m:
        return None
    depth, i = 1, m.end()
    while i < len(text) and depth:
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        i += 1
    return (m.start(), i) if depth == 0 else None


def set_attribute(block: str, attr: str, value) -> str | None:
    """Set a top-level attribute inside a resource block; insert it if it is `count`."""
    lines = block.split("\n")
    body = next((l for l in lines[1:] if l.strip() and not l.strip().startswith("}")), "")
    indent = body[: len(body) - len(body.lstrip())] or "  "
    rendered = value if isinstance(value, int) else f'"{value}"'
    pat = re.compile(rf"^{re.escape(indent)}{re.escape(attr)}\s*=")
    for i, line in enumerate(lines):
        if pat.match(line):
            key = line.split("=")[0].rstrip()
            lines[i] = f"{key} = {rendered}"
            return "\n".join(lines)
    if attr == "count":
        lines.insert(1, f"{indent}count = {rendered}")
        return "\n".join(lines)
    return None


def get_attribute(block: str, attr: str) -> str | None:
    m = re.search(rf'^\s+{re.escape(attr)}\s*=\s*"?([^"\n]+)"?', block, re.M)
    return m.group(1).strip() if m else None
