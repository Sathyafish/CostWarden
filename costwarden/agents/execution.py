import shutil
import subprocess

from costwarden.accounts import Account


def run_plan(account: Account) -> dict:
    """Run `terraform plan` for the account's directory if possible. Never applies."""
    tf = shutil.which("terraform")
    if not tf or not account.tf_path:
        return {"ok": True, "ran": False, "summary": "terraform not available here; plan skipped. "
                "Run the plan in your CI/CD pipeline after merge."}
    try:
        init = subprocess.run([tf, f"-chdir={account.tf_path}", "init", "-input=false", "-backend=false"],
                              capture_output=True, text=True, timeout=300)
        if init.returncode:
            return {"ok": False, "ran": True, "summary": init.stderr[-500:]}
        plan = subprocess.run([tf, f"-chdir={account.tf_path}", "plan", "-input=false", "-lock=false"],
                              capture_output=True, text=True, timeout=600)
        tail = (plan.stdout or plan.stderr).strip().splitlines()[-3:]
        return {"ok": plan.returncode == 0, "ran": True, "summary": " ".join(tail)}
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"ok": False, "ran": True, "summary": str(e)}
