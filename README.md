<img src="docs/logo.svg" alt="CostWarden logo" width="72" align="left">

# CostWarden

*Guard the cloud. Keep the savings.*

Proactive, continuous guarding against cloud waste.

CostWarden is a multi-agent system built with LangGraph and LangChain. A supervisor agent routes work between specialized agents, validates state transitions and enforces guardrails, such as mandatory human approval, before any infrastructure change.

> **Status:** the agents, supervisor graph, history store, FastAPI backend, React app, Lambda handlers and Terraform are built. Tests: 110 backend (pytest, with moto and a fake LLM) and 22 frontend (Vitest); the React flow was also walked by hand against the live local API. Not yet verified: a live run against Ollama, a real GitHub PR, `terraform validate` or `apply` of the AWS stack, and the hosted CloudFront site. See the [spec](docs/superpowers/specs/2026-10-24-costwarden-multi-account-design.md) and the [plan](docs/superpowers/plans/2026-10-24-costwarden-multi-account.md).

## One-liner

My agent helps a cloud or FinOps engineer remove idle AWS waste in a web app, replacing the manual hunt through Trusted Advisor and Terraform that takes hours each month. It discovers waste, edits the Terraform and opens a PR on its own using 5 tools, hands off to a human for approval before anything is applied, and I'll know it works when a draft PR with a savings estimate is ready in under 5 minutes on 4 of 5 seeded cases.

## Architecture

![CostWarden AWS architecture](docs/architecture.svg)

| Component | Role |
|---|---|
| React app (`frontend/`) | Overview dashboard (cost avoided per account), Ask prompt (questions about past cleanups) and the run and approval screens. See [Frontend and API](#frontend-and-api). |
| FastAPI backend (`costwarden/api/`) | The HTTP API the React app calls. Runs locally with `uvicorn`, or as the `costwarden-api` Lambda behind a function URL. |
| Supervisor "Zeve" | LangGraph state machine. Discovers all accounts in parallel, then works through accounts one at a time and pauses at human approval gates. Checkpoints go to DynamoDB so a pause survives across Lambda calls. |
| Discovery, Refactoring, VCS and PR, Execution agents | The four worker agents (roles below). Each runs in-process locally or as its own Lambda (`costwarden-discover`, `-refactor`, `-open_pr`, `-execute`), with the supervisor Lambda `costwarden-supervisor` in front. |
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

## Frontend and API

**React app** (`frontend/`, React, TypeScript and Vite, charts with recharts). Dark navy and teal identity with a shield-and-eye logo:

- **Overview:** KPI cards that count up (avoided per month, per year and to date, cleanups, open PRs), a run-rate trend, avoided-by-resource-type, an accounts table, cleanups by status and recent cleanups with PR links. Filter by account.
- **Ask:** a chat prompt with example questions. Each answer shows the query tool it came from.
- **Runs and approvals:** start a run, review the risk summary and Terraform diff, exclude individual resources, approve or reject, confirm the merge, and retry or skip when a step fails.
- **Settings** (top right): API URL and API key, stored in the browser.

**API** (`costwarden/api/app.py`, FastAPI):

| Route | Purpose |
|---|---|
| `GET /api/health`, `GET /api/info` | Open. Health and runtime info (no secrets). |
| `GET /api/accounts` | Account ids, names and regions only. |
| `GET /api/dashboard?account_id=` | KPIs, status counts, savings by type, trend and per-account rows. |
| `GET /api/cleanups?account_id=&limit=` | Recent cleanup records. |
| `POST /api/ask` | Ask prompt: `{question}`. |
| `POST /api/runs`, `GET /api/runs/{id}`, `POST /api/runs/{id}/resume` | Start, inspect and continue a run. |
| `POST /api/demo/seed` | Insert demo history. Off unless `ALLOW_DEMO_SEED=true`. |

If `API_KEY` is set, every route except health and info needs an `x-api-key` header. That is demo-level protection for a public function URL, not user authentication. In AWS the API is one Lambda behind a function URL rather than API Gateway, so a long run is not cut off at 30 seconds; CORS is handled by the app.

## Quick start (local, no AWS needed)

```bash
python3.13 -m venv .venv
.venv/bin/pip install -e ".[api,dev]"
.venv/bin/python -m pytest
```

Run the API and the React app in two terminals:

```bash
LLM_PROVIDER=fake STORE_BACKEND=memory ALLOW_DEMO_SEED=true .venv/bin/uvicorn --factory costwarden.api.app:create_app --port 8000
```

```bash
cd frontend && npm install && npm run dev
```

Open http://localhost:5173 (the dev server proxies `/api` to port 8000). On the Overview, click **Load demo history**, try the Ask tab, then **Start cleanup run** (it works on the bundled dummy Cost Explorer data in `data/dummy_cost_explorer.json` and the sample Terraform in `sample_terraform/`). Frontend tests: `cd frontend && npm test`.

For real Ollama, set `LLM_PROVIDER=ollama` in `.env` (see `.env.example`); the server must be reachable from your network. Memory mode loses data when the API restarts.

## Deploy the AWS resources

[infra/terraform](infra/terraform) creates everything: the history and checkpoint DynamoDB tables, IAM, an S3 bucket for the package, the four agent Lambdas, the supervisor Lambda, the API Lambda with its function URL and, optionally, seeded demo waste and CloudFront hosting for the React app.

```bash
scripts/build_lambda.sh
cd infra/terraform
terraform init
terraform apply -var api_key=$(openssl rand -hex 16) -var nebius_api_key=... -var github_token=... -var github_repo=owner/costwarden-sandbox
```

- `build_lambda.sh` writes `build/lambda.zip` (Linux x86_64, Python 3.12). Run it before `terraform apply`.
- `api_key` is required (16 or more characters). Keep the value: you enter it in the app's Settings.
- Leave `github_repo` empty to use a fake GitHub client. The Lambdas then bundle the sample Terraform and open no real PRs.
- The Lambdas are not in a VPC, so they cannot reach the private Ollama server. They default to `lambda_llm_provider=nebius`; use `fake` for an offline demo.
- `github_token`, `nebius_api_key` and `api_key` are stored as Lambda environment variables. Use a narrowly scoped token on a sandbox repository.
- Add `-var create_demo_waste=true` for an unattached EBS volume and an unassociated Elastic IP (about $3.70 per month), and `-var allow_demo_seed=true` to let the app's **Load demo history** button write to the real table.

Use the deployed API from the local React app: run `npm run dev`, open **Settings**, paste the `api_url` output and your API key.

To host the React app on CloudFront too (private S3 bucket, HTTPS, no public bucket):

```bash
(cd frontend && npm run build)
terraform apply -var enable_frontend_hosting=true ...  # same variables as above
```

The `frontend_url` output is the site; Terraform writes the API URL into its `config.js`, and users enter the API key once in Settings. Destroy everything with `terraform destroy`.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | `ollama`, `nebius` or `fake` (tests and offline demo). |
| `OLLAMA_BASE_URL` | `http://10.135.128.9:11434` | Ollama endpoint. |
| `LLM_MODEL` | `llama3.1` | Model name. |
| `DYNAMODB_TABLE` | `costwarden-cleanups` | History table. |
| `STORE_BACKEND` | `dynamo` | `dynamo` or `memory`. |
| `CHECKPOINT_BACKEND` | `memory` | `memory` locally, `dynamo` on Lambda. |
| `AGENT_RUNTIME` | `local` | `local` runs agents in-process; `lambda` calls the deployed functions. |
| `TF_SOURCE` | `local` | `local` reads `tf_path` from disk; `github` reads it from the sandbox repo. |
| `GITHUB_TOKEN`, `GITHUB_REPO` | empty | Real draft PRs on a sandbox repo; empty uses a fake client. |
| `API_KEY` | empty | If set, the API requires this as the `x-api-key` header. |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Browser origins allowed to call the API. |
| `ALLOW_DEMO_SEED` | `false` | Enables `POST /api/demo/seed`. |

## Repository layout

```
costwarden/            application code (agents, supervisor graph, store, API, Lambda handlers)
frontend/              React app (Vite, TypeScript)
config/accounts.yaml   account registry (two demo accounts)
data/                  dummy Cost Explorer export
sample_terraform/      Terraform the Refactoring agent edits
infra/terraform/       tables, IAM, Lambdas, API function URL, optional hosting and demo waste
scripts/               build_lambda.sh, seed_demo_data.py
tests/                 pytest suite
docs/                  architecture diagram, specs, plans
```

## Limits of the prototype

- The `x-api-key` is one shared secret, not per-user sign-in. The function URL is public, so use a long random key and rotate it after demos.
- The built React bundle is about 580 kB (recharts); it is not code-split.
- The agents never apply Terraform. The Execution agent runs `terraform plan` only when the binary is present (not in Lambda); applying stays with your CI/CD pipeline.
- Accounts are processed one at a time after discovery, so approvals are sequential per account.
- A resize or release changes only the Terraform on a branch. Cost avoided is counted when a human confirms the merge, not from the actual AWS bill.
- Terraform edits are text patches validated by parsing with python-hcl2; `terraform validate` is not run.
- Checkpoints are stored as one compressed item per run and unpickled on read, so the checkpoint table must only be writable by the CostWarden role.
- The Ollama server is reachable only from the right network, so tests and the offline demo use a fake LLM.
