# CostWarden

Proactive, continuous guarding against cloud waste.

CostWarden is a multi-agent system built with LangGraph and LangChain. A supervisor agent routes work between specialized agents, validates state transitions and enforces guardrails, such as mandatory human approval, before any infrastructure change.

> **Status:** design and infrastructure are in place; application code is being built task by task. See the [spec](docs/superpowers/specs/2026-10-24-costwarden-multi-account-design.md) and the [implementation plan](docs/superpowers/plans/2026-10-24-costwarden-multi-account.md).

## One-liner

My agent helps a cloud or FinOps engineer remove idle AWS waste in a Streamlit app, replacing the manual hunt through Trusted Advisor and Terraform that takes hours each month. It discovers waste, edits the Terraform and opens a PR on its own using 5 tools, hands off to a human for approval before anything is applied, and I'll know it works when a draft PR with a savings estimate is ready in under 5 minutes on 4 of 5 seeded cases.

## Architecture

![CostWarden AWS architecture](docs/architecture.svg)

| Component | Role |
|---|---|
| Streamlit frontend | Dashboard (cost avoided per account), Ask prompt (questions about past cleanups) and the run and approval screens. |
| Supervisor "Zeve" | LangGraph state machine with a SQLite checkpointer. Fans out per account, pauses at human approval gates. |
| Discovery, Refactoring, VCS and PR, Execution agents | The four worker agents (roles below). Run locally now; Lambda handlers and a SAM template are planned. |
| DynamoDB `costwarden-cleanups` | History of every cleanup: account, resources, monthly savings, PR URL and status. Feeds the dashboard and the prompt. |
| LLM via `get_llm()` | Ollama (`llama3.1`) by default; Nebius Token Factory as a second provider. |
| Target AWS accounts | Prototype: one account using ambient credentials. Org mode: more entries in `config/accounts.yaml`, each assumed through a read-only `CostWardenReadOnly` role. |

### Multi-account design

Every agent receives an `Account` (id, role ARN, region, Terraform path, repo) from a registry. `get_session(account)` assumes the account's role through STS, or uses the default session when no role is set. Findings carry `account_id` through the whole graph, so scaling from one account to an organization means adding registry entries, not changing agent code.

### Human-in-the-loop

Reads are autonomous. Every write sits behind a LangGraph interrupt:

1. Approve the diff before the branch and draft PR are created.
2. Confirm the merge before the Terraform plan runs.

The agents never apply changes directly and never delete resources through the AWS API.

### Dashboard and prompt

- **Dashboard:** per-account cost avoided (monthly run-rate and cumulative), cleanups by status, open PRs, findings by resource type and a savings trend. Cost avoided counts merged cleanups only.
- **Ask prompt:** questions like "what was the last cleanup and how much did it avoid?" The model chooses one of a few fixed query tools over the history table, and the numbers in the answer come from the table, not from the model.

## Agent roles and responsibilities

### Supervisor agent ("Zeve")

- Manages overall state transitions and routing.
- Evaluates sub-agent outputs against acceptance criteria.
- Pauses graph execution for human-in-the-loop approval before applying code changes.

### Discovery agent (Trusted Advisor, Cost Explorer, CloudWatch)

- Queries AWS through boto3 (the prototype's checks use EC2 and CloudWatch; Trusted Advisor and Cost Optimization Hub are planned extensions).
- Filters actionable idle or unattached resources: unattached EBS volumes, idle NAT gateways, unassociated Elastic IPs and aged snapshots.
- Produces a normalized inventory of resource IDs, ARNs and target Terraform files.

### Refactoring agent (Terraform and OpenTofu)

- Maps idle resources to HCL configuration files in the repository.
- Makes declarative edits, such as setting `count = 0`, located with python-hcl2.
- Runs `terraform fmt` and `terraform validate` when the binary is available.

### VCS and PR agent (GitHub)

- Creates a branch named `costwarden/cleanup-YYYY-MM-DD-<account>`.
- Commits the updated HCL and opens a draft pull request with estimated monthly savings, targeted resources and risk severity.

### Execution agent (CI/CD)

- Runs only after the PR is merged and a human confirms.
- Runs `terraform plan` and posts the summary back to the supervisor state. Applying remains with your CI/CD pipeline.

## Deploy the AWS resources

[infra/terraform](infra/terraform) creates the DynamoDB table, the `costwarden-app` IAM policy, the `costwarden-lambda` execution role and, optionally, seeded demo waste (an unattached EBS volume and an unassociated Elastic IP, about $3.70 per month).

```bash
cd infra/terraform
terraform init
terraform apply -var create_demo_waste=true
```

Then set `DYNAMODB_TABLE` to the `table_name` output and attach the `app_policy_arn` policy to the user or role that runs the agents. Destroy with `terraform destroy` when you finish the demo.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | `ollama`, `nebius` or `fake` (tests and offline demo). |
| `OLLAMA_BASE_URL` | `http://10.135.128.9:11434` | Ollama endpoint. |
| `LLM_MODEL` | `llama3.1` | Model name. |
| `DYNAMODB_TABLE` | `costwarden-cleanups` | History table. |
| `STORE_BACKEND` | `dynamo` | `dynamo` or `memory`. |

## Repository layout

```
docs/                  architecture diagram, specs, plans
infra/terraform/       DynamoDB table, IAM, optional demo waste
costwarden/            application code (in progress, per the plan)
config/accounts.yaml   account registry
```

## Limits of the prototype

- One account; the agents run locally. The Lambda handlers and deploy template are planned but not deployed, and moving the full pipeline to Lambda needs a DynamoDB checkpointer first.
- The Ollama server is reachable only from the right network, so tests and the offline demo use a fake LLM.
