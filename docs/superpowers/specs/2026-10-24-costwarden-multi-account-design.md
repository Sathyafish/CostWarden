# CostWarden: multi-account-ready prototype design

Date: 2026-10-24 · Track: LangChain + LangGraph (Week 3 project, own use case) · Deadline: Oct 25, 2026

## One-liner

My agent helps a cloud or FinOps engineer remove idle AWS waste in a Streamlit app, replacing the manual hunt through Trusted Advisor and Terraform that takes hours each month. It discovers waste, edits the Terraform and opens a PR on its own using 5 tools, hands off to a human for approval before anything is applied, and I'll know it works when a draft PR with a savings estimate is ready in under 5 minutes on 4 of 5 seeded cases.

## Scope and decisions

- **Prototype:** one AWS account; agents run in that account. Code is org-ready: going to many accounts means adding registry entries, not changing agent code.
- **LLM:** `LLM_PROVIDER=ollama`, `OLLAMA_BASE_URL=http://10.135.128.9:11434`, `LLM_MODEL=llama3.1`. `nebius` is a second supported provider (handout requires at least one Nebius Token Factory call; the risk write-up step uses it). One `get_llm()` factory; agents never see the provider.
- **AWS in demo:** moto-mocked, seeded with waste. Real boto3 code paths, no real spend.
- **PR:** real GitHub PR on a throwaway sandbox repo containing sample Terraform.
- **Out of scope:** Organizations auto-discovery, cross-account IAM/StackSet setup, real `terraform apply` (ends at `terraform plan`).

## Architecture

Supervisor ("Jev") is a LangGraph `StateGraph` with a SQLite checkpointer.

1. `load_accounts` reads the registry.
2. Fan-out `discover` per account via `Send`.
3. Group findings per account.
4. `refactor` edits HCL (python-hcl2 for parsing, validated with `terraform fmt/validate`).
5. `open_pr` creates the branch, commit and PR.
6. **interrupt**: human approves or rejects per account PR.
7. `execute` (approved accounts only) runs plan and posts the summary.

### Package layout

```
costwarden/
  config.py            # env loading, get_llm()
  accounts/            # Account model, Registry interface, StaticRegistry (YAML), get_session()
  state.py             # graph state keyed by account_id; errors recorded per account
  agents/              # discovery, refactor, vcs, execution, supervisor
  tools/               # boto3 checks, hcl editing, github client, terraform runner
  ui/app.py            # Streamlit: findings, savings, PR, approve/reject
config/accounts.yaml   # one entry for the prototype
tests/                 # pytest + moto, fake LLM
```

### Account model

`Account(id, name, role_arn | None, region, tf_path, repo)`. `get_session(account)` assumes `role_arn` through STS, or returns the default session when it is empty (prototype). Every finding carries `account_id`.

### Base functions

`load_accounts()`, `get_session(account)`, `discover(account)` (unattached EBS, idle NAT gateways, unassociated Elastic IPs, aged snapshots), `map_to_terraform(finding, account)`, `build_pr(account, findings)`, `run_apply(account)`, `get_llm()`.

## Framework fields

| Field | Decision |
|---|---|
| Agent goal | Turn idle AWS resources into a reviewed Terraform cleanup PR. |
| Where used | Streamlit web app. |
| Steps | Discover, refactor, open PR, human approval, plan/apply, report. |
| Tools | Reads: boto3 checks, HCL parse, terraform validate. Writes: git push and PR creation, terraform apply. |
| Memory | Per-run state in the SQLite checkpointer (findings, plan, approvals); survives restart. No cross-run memory. |
| Never | Apply without an approved PR; touch resources outside registry accounts; delete resources directly via the AWS API. |
| Human in the loop | `interrupt` before every write; reviewer can approve, reject or exclude findings. |
| When something breaks | Retry with backoff (3 tries), then record the error in state and hand off to the human. One account failing never stops the others. LLM unreachable gets the same treatment. |
| Success measure | Correct draft PR and savings estimate in under 5 minutes on 4 of 5 seeded cases. |

## Addendum (2026-10-24): history store, dashboard, prompt, Lambda

**Decisions:** real DynamoDB table for the demo (moto in tests); Lambda scope for this submission is handlers plus a deploy template only, with the demo running locally.

- **Store:** `Store` interface (`record_cleanup`, `list_cleanups(account_id | None, since | None)`, `metrics(account_id | None)`), with `DynamoStore` and `MemoryStore`. Table `costwarden-cleanups`: partition key `account_id` (S), sort key `ts_run` (S, `<ISO timestamp>#<run_id>`). Attributes: `run_id`, `resources` (list of resource id, type, monthly savings), `monthly_savings_usd` (N), `pr_url`, `status` (`proposed` | `merged` | `rejected` | `failed`), `summary`. Metrics are computed from queries or a scan; the table stays small.
- **Recording:** the graph writes a record when the diff is approved or rejected (`proposed`/`rejected`) and updates it on merge confirmation (`merged`) or error (`failed`). Cost avoided counts `merged` records only.
- **Dashboard (Streamlit):** per-account table and tiles: cost avoided (monthly run-rate and cumulative), cleanups by status, open PRs, findings by resource type, savings trend. Account filter doubles as the multi-account demo.
- **Prompt:** a chat box where the LLM chooses among fixed query tools over the store: `last_cleanup(account_id | None)`, `savings_between(start, end, account_id | None)`, `cleanups_by_status(status)`, `top_resource_types(n)`. No free-form queries. The tool result is rendered into the answer, with numbers taken from the tool output, not from the model.
- **Lambda:** thin handlers (`discover`, `refactor`, `open_pr`, `execute`) wrapping the same functions, plus a SAM template (container image with `terraform` and `git`, DynamoDB table). The SQLite checkpointer does not work on Lambda; a DynamoDB checkpointer is future work. Not deployed in this submission.

## Error handling and testing

- Each tool call is wrapped with retry and a typed error recorded in state.
- Demo includes one deliberate failure (stopped Ollama or a bad resource) showing the human handoff.
- Tests use pytest with moto for discovery and registry, and a fake LLM so tests and the demo run without the Ollama server.
- Note: `10.135.128.9:11434` was unreachable from the dev session; the endpoint and `llama3.1` availability are unverified.

## Deliverables mapping

Code on GitHub; Google Doc (overview, prompts used, iterations, learnings); demo video of 5 minutes or less showing the happy path, the approval gate and the failure handoff.
