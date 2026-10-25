# CostWarden multi-account-ready prototype implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A LangGraph supervisor that discovers idle AWS waste, edits Terraform, opens a PR, pauses for human approval and reports a plan, built so adding accounts is a config change.

**Architecture:** Supervisor `StateGraph` with a SQLite checkpointer. Per-account `AccountContext` (registry plus `get_session`) flows through every agent. Findings carry `account_id`. Tasks 1–8 deliver the single-account happy path end to end; Tasks 9–12 add robustness, the Nebius step, the multi-account demo and submission material.

**Tech stack:** Python 3.11 (venv), langgraph, langgraph-checkpoint-sqlite, langchain-ollama, langchain-openai (Nebius, OpenAI-compatible), boto3, moto, python-hcl2, PyGithub, Streamlit, pytest, PyYAML.

**Spec:** `docs/superpowers/specs/2026-10-24-costwarden-multi-account-design.md`

## Global constraints

- `LLM_PROVIDER=ollama`, `OLLAMA_BASE_URL=http://10.135.128.9:11434`, `LLM_MODEL=llama3.1`; `nebius` is the second provider. Agents only call `get_llm()`.
- Demo AWS is moto-mocked; real boto3 code paths. Empty `role_arn` means the default session.
- Every write (git push, PR creation, terraform apply) is behind a LangGraph `interrupt`. Never apply without an approved PR; never touch accounts outside the registry; never delete via the AWS API.
- Tool failures: retry 3 times with backoff, then record in state and hand off to the human. One account failing never stops the others.
- Success measure: correct draft PR and savings estimate in under 5 minutes on 4 of 5 seeded cases.
- Spec clarification: the spec lists one interrupt after `open_pr`, but the write rule requires approval before the push. This plan uses two interrupts: approve the diff before `open_pr`, confirm the PR is merged before `execute`.
- Tests never need the Ollama server (fake LLM) or real AWS or GitHub (moto, fake GitHub client).

## Review focus

- Account whose STS assume-role fails: error recorded, other accounts still processed (Task 9).
- Zero findings for an account: no PR, no interrupt, run ends cleanly (Task 4).
- Finding with no matching HCL resource block: reported as unmapped, no file edited (Task 5).
- Reviewer rejects the diff: nothing is pushed or applied (Task 7).
- Ollama unreachable or invalid LLM output: retry, then human handoff, no crash (Task 9).
- Process restart mid-run: resuming the same `thread_id` continues from the checkpoint (Task 7).

---

### Task 1: Scaffold, config and `get_llm()`

**Files:**
- Create: `pyproject.toml`, `.env.example`, `.gitignore`, `costwarden/__init__.py`, `costwarden/config.py`, `costwarden/llm.py`, `tests/test_llm.py`

**Interfaces:**
- Produces: `Settings` dataclass (`llm_provider`, `ollama_base_url`, `llm_model`, `nebius_api_key`, `nebius_base_url`, `github_token`, `github_repo`, `checkpoint_db`); `load_settings() -> Settings` (reads env/.env); `get_llm(settings: Settings | None = None, provider: str | None = None) -> BaseChatModel`; `FakeLLM(responses: list[str])` in `costwarden/llm.py` for tests and the offline demo (`LLM_PROVIDER=fake`).

- [ ] **Step 1: Write failing tests** in `tests/test_llm.py`: `test_ollama_default` (env as in spec gives `ChatOllama` with `base_url == "http://10.135.128.9:11434"` and `model == "llama3.1"`), `test_nebius_provider` (returns a `ChatOpenAI` whose base URL is the Nebius one), `test_fake_provider` (`get_llm(provider="fake").invoke("x").content` is the first canned response), `test_unknown_provider_raises` (`ValueError`).
- [ ] **Step 2: Run** `pytest tests/test_llm.py -v`. Expected: FAIL (import error).
- [ ] **Step 3: Implement** the files above. Create the venv (`python3.11 -m venv .venv`, fall back to the newest installed 3.10+), pin dependencies in `pyproject.toml`, ignore `.venv`, `.env`, `*.db`. `.env.example` holds the three spec values plus placeholders for the Nebius and GitHub settings.
- [ ] **Step 4: Run** `pytest tests/test_llm.py -v`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: scaffold project and llm factory`.

### Task 2: Accounts, registry and `get_session`

**Files:**
- Create: `costwarden/accounts/__init__.py`, `costwarden/accounts/models.py`, `costwarden/accounts/registry.py`, `costwarden/accounts/session.py`, `config/accounts.yaml`, `tests/test_accounts.py`

**Interfaces:**
- Produces: `Account(id: str, name: str, role_arn: str | None, region: str, tf_path: str, repo: str)` (frozen dataclass); `Registry` (Protocol with `list_accounts() -> list[Account]`); `StaticRegistry(path: str)`; `load_accounts(path: str = "config/accounts.yaml") -> list[Account]`; `get_session(account: Account) -> boto3.Session`.

- [ ] **Step 1: Write failing tests**: `test_load_accounts_single` (the prototype YAML yields one account with `role_arn is None`), `test_load_accounts_many` (YAML with two entries returns both, order preserved), `test_duplicate_ids_rejected`, `test_get_session_default_when_no_role` (region matches the account), `test_get_session_assumes_role` (under moto STS, the session's credentials differ from the default and `sts.get_caller_identity` shows the assumed role).
- [ ] **Step 2: Run** `pytest tests/test_accounts.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.** `get_session` calls STS `assume_role` when `role_arn` is set (session name `costwarden`) and returns a session built from the temporary credentials; otherwise `boto3.Session(region_name=...)`.
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat: account registry and session factory`.

### Task 3: Discovery tools and `discover(account)`

**Files:**
- Create: `costwarden/models.py`, `costwarden/tools/aws_checks.py`, `costwarden/agents/discovery.py`, `tests/conftest.py`, `tests/test_discovery.py`

**Interfaces:**
- Consumes: `Account`, `get_session`.
- Produces: `Finding(account_id: str, resource_type: str, resource_id: str, arn: str, reason: str, monthly_savings_usd: float, severity: str)` in `costwarden/models.py`; `check_unattached_ebs(session) -> list[Finding]`, `check_unassociated_eips(session)`, `check_idle_nat_gateways(session)`, `check_old_snapshots(session, min_age_days: int = 90)` (all take the account id via `session`-adjacent argument `account_id: str`); `discover(account: Account) -> list[Finding]`. A `seeded_aws` fixture in `conftest.py` creates under moto one unattached volume, one unassociated EIP, one NAT gateway and one 120-day-old snapshot.

- [ ] **Step 1: Write failing tests**: one per check against `seeded_aws` (asserting `resource_id`, `resource_type`, positive `monthly_savings_usd`), `test_discover_aggregates_all_four`, `test_attached_volume_not_flagged`, `test_findings_carry_account_id`.
- [ ] **Step 2: Run** `pytest tests/test_discovery.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** the checks with boto3 EC2 calls; use fixed per-GB and per-hour price constants for savings (documented in one `PRICING` dict). Idle NAT detection uses CloudWatch `BytesOutToDestination` over 7 days (moto returns no data, so the NAT counts as idle).
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat: discovery agent with four idle-resource checks`.

### Task 4: State and supervisor graph (discovery only)

**Files:**
- Create: `costwarden/state.py`, `costwarden/agents/supervisor.py`, `tests/test_supervisor.py`

**Interfaces:**
- Consumes: `load_accounts`, `discover`.
- Produces: `RunState` TypedDict (`accounts: list[Account]`, `findings: dict[str, list[Finding]]`, `errors: dict[str, str]`, `diffs`, `pr_urls`, `approvals`, `plan_summaries`); `build_graph(checkpointer=None, registry_path: str = "config/accounts.yaml") -> CompiledGraph` with nodes `load_accounts`, `discover` (fanned out per account with `Send`), `group`; `run_id` is the checkpointer `thread_id`.

- [ ] **Step 1: Write failing tests** with `seeded_aws`: `test_graph_collects_findings_per_account` (state keys equal account ids, four findings), `test_zero_findings_ends_cleanly` (empty AWS gives empty findings and a finished graph with no pending interrupt).
- [ ] **Step 2: Run** `pytest tests/test_supervisor.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** the graph; reducers merge per-account dict updates from parallel `discover` branches.
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat: supervisor graph with per-account discovery fan-out`.

### Task 5: Refactoring agent (Terraform edits)

**Files:**
- Create: `costwarden/tools/hcl.py`, `costwarden/agents/refactor.py`, `tests/fixtures/sample_tf/main.tf`, `tests/test_refactor.py`

**Interfaces:**
- Consumes: `Finding`, `Account.tf_path`.
- Produces: `map_to_terraform(finding: Finding, tf_path: str) -> TfTarget | None` (`TfTarget(file: str, resource_address: str)`); `apply_edit(target: TfTarget, finding: Finding) -> None` (sets `count = 0` on the matching block; edits in place); `refactor(account: Account, findings: list[Finding]) -> RefactorResult` (`RefactorResult(diff: str, edited: list[Finding], unmapped: list[Finding], validation_ok: bool)`).

- [ ] **Step 1: Write failing tests** against a copy of the sample Terraform (an `aws_ebs_volume` and an `aws_eip` block tagged or ID-matched to seeded findings): `test_maps_ebs_finding_to_block`, `test_unmapped_finding_returned_not_edited` (file bytes unchanged), `test_edit_sets_count_zero`, `test_refactor_produces_unified_diff`, `test_validation_skipped_when_terraform_missing` (`validation_ok` is `False` with a note rather than an exception).
- [ ] **Step 2: Run** `pytest tests/test_refactor.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.** Parse with python-hcl2 to locate blocks, then make the edit as a minimal textual patch on the located block's line range (hcl2 does not round-trip). Run `terraform fmt -check` and `validate` through `subprocess` when the binary exists.
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat: refactoring agent maps findings to terraform and edits`.

### Task 6: VCS and PR agent

**Files:**
- Create: `costwarden/tools/github_client.py`, `costwarden/agents/vcs.py`, `tests/test_vcs.py`

**Interfaces:**
- Consumes: `RefactorResult`, `Finding`.
- Produces: `GitHubClient` (Protocol: `create_branch(name: str) -> None`, `commit_files(branch: str, files: dict[str, str], message: str) -> None`, `open_pr(branch: str, title: str, body: str, draft: bool = True) -> str`); `PyGithubClient(token, repo)`; `FakeGitHubClient` (records calls); `build_pr_body(account: Account, result: RefactorResult, summary: str) -> str`; `open_pull_request(account, result, summary, client) -> str` (branch `costwarden/cleanup-YYYY-MM-DD-<account.id>`, returns the PR URL).

- [ ] **Step 1: Write failing tests** with the fake client: `test_branch_name_includes_date_and_account`, `test_pr_is_draft_with_savings_and_resources_in_body`, `test_open_pull_request_returns_url`.
- [ ] **Step 2: Run** `pytest tests/test_vcs.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.** Total savings is the sum over `result.edited`; the body lists resources and severity.
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat: vcs agent opens draft PRs per account`.

### Task 7: Human-in-the-loop gates, execution and checkpointing

**Files:**
- Create: `costwarden/agents/execution.py`, `tests/test_hitl.py`
- Modify: `costwarden/agents/supervisor.py`, `costwarden/state.py`

**Interfaces:**
- Consumes: `refactor`, `open_pull_request`, `build_graph`.
- Produces: graph nodes `refactor`, `approve_diff` (interrupt payload `{account_id, diff, savings}`; resume value `{"approved": bool, "exclude": list[str]}`), `open_pr`, `confirm_merge` (interrupt; resume `{"merged": bool}`), `execute`; `run_plan(account: Account) -> PlanSummary` (`terraform plan` output summary; no apply in the prototype); `build_graph(..., github_client=None, llm=None)` gains injectable collaborators; checkpointer `SqliteSaver` at `Settings.checkpoint_db`.

- [ ] **Step 1: Write failing tests**: `test_graph_pauses_before_pr` (invoke stops with an interrupt, fake client has no calls), `test_approve_opens_pr_then_pauses_for_merge`, `test_reject_pushes_nothing_and_never_executes`, `test_exclude_removes_finding_from_pr`, `test_resume_after_restart` (build a new graph on the same SQLite file and `thread_id`, resume, and the run completes).
- [ ] **Step 2: Run** `pytest tests/test_hitl.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** with `langgraph.types.interrupt` and `Command(resume=...)`. `execute` runs only for accounts with `merged is True`.
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat: approval gates, execution step and sqlite checkpointing`.

### Task 8: Streamlit UI (happy path demo)

**Files:**
- Create: `costwarden/ui/app.py`, `costwarden/ui/runner.py`, `tests/test_runner.py`

**Interfaces:**
- Consumes: `build_graph`.
- Produces: `start_run(graph) -> str` (returns `thread_id`), `get_pending(graph, thread_id) -> dict | None` (the interrupt payload), `resume(graph, thread_id, value: dict) -> None`, `get_status(graph, thread_id) -> dict` (findings, errors, PR URLs, plan summaries). The Streamlit page only calls these.

- [ ] **Step 1: Write failing tests** for the runner functions on the fake-collaborator graph: `test_start_then_pending_returns_diff`, `test_resume_advances_to_merge_prompt`, `test_status_lists_errors`.
- [ ] **Step 2: Run** `pytest tests/test_runner.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** the runner, then the page: findings table with savings, diff viewer, per-finding exclude checkboxes, Approve/Reject buttons, PR link, merge confirmation and the plan summary. Run `streamlit run costwarden/ui/app.py` against the seeded moto environment (`LLM_PROVIDER=fake`) and walk the happy path once by hand.
- [ ] **Step 4: Run** `pytest tests/test_runner.py -v`. Expected: PASS; the manual walk-through completes.
- [ ] **Step 5: Commit** `feat: streamlit approval UI`.

**Milestone: after Task 8 the happy path works end to end. Record a backup demo clip here.**

### Task 8A: Cleanup history store (DynamoDB)

**Files:**
- Create: `costwarden/store/__init__.py`, `costwarden/store/models.py`, `costwarden/store/memory.py`, `costwarden/store/dynamo.py`, `infra/dynamodb-table.yaml`, `tests/test_store.py`
- Modify: `costwarden/agents/supervisor.py`, `costwarden/config.py` (`DYNAMODB_TABLE`, `STORE_BACKEND=dynamo|memory`)

**Interfaces:**
- Produces: `CleanupRecord(account_id: str, run_id: str, timestamp: str, resources: list[dict], monthly_savings_usd: float, pr_url: str | None, status: str, summary: str)`; `Store` Protocol: `record_cleanup(rec: CleanupRecord) -> None` (upsert on `account_id` + `ts_run`), `update_status(account_id: str, run_id: str, status: str) -> None`, `list_cleanups(account_id: str | None = None, since: str | None = None) -> list[CleanupRecord]` (newest first), `metrics(account_id: str | None = None) -> Metrics` (`cost_avoided_monthly`, `cost_avoided_cumulative`, `counts_by_status`, `by_resource_type`, `open_prs`); `MemoryStore`, `DynamoStore(table_name, session)`; `get_store(settings) -> Store`. The same test suite runs against both backends.

- [ ] **Step 1: Write failing tests** (parametrized over `MemoryStore` and `DynamoStore` under moto): `test_record_and_list_newest_first`, `test_filter_by_account_and_since`, `test_update_status`, `test_cost_avoided_counts_merged_only`, `test_metrics_across_accounts`, `test_empty_store_metrics_are_zero`, `test_graph_records_proposed_then_merged` (fake collaborators: approving writes `proposed`, merge confirmation flips to `merged`), `test_reject_records_rejected`.
- [ ] **Step 2: Run** `pytest tests/test_store.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** the models and both backends; wire `record_cleanup`/`update_status` into the `open_pr`, `confirm_merge` and `handle_error` paths. `infra/dynamodb-table.yaml` is a CloudFormation template (on-demand billing, keys as in the spec). Give the user the `aws cloudformation deploy` command to create the real table.
- [ ] **Step 4: Run** `pytest -v`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: dynamodb-backed cleanup history store`.

### Task 8B: Dashboard

**Files:**
- Create: `costwarden/ui/dashboard.py`, `costwarden/ui/view_models.py`, `tests/test_view_models.py`
- Modify: `costwarden/ui/app.py` (tabs: Dashboard, Ask, Run)

**Interfaces:**
- Consumes: `Store`, `Metrics`.
- Produces: `account_rows(store: Store) -> list[dict]` (per account: `account_id`, `cleanups`, `cost_avoided_monthly`, `cost_avoided_cumulative`, `open_prs`, `last_cleanup`); `savings_trend(store: Store, account_id: str | None) -> list[tuple[str, float]]` (cumulative by date); `dashboard.render(store)` only formats these.

- [ ] **Step 1: Write failing tests** on a seeded `MemoryStore`: `test_account_rows_totals`, `test_account_without_cleanups_shows_zeros`, `test_trend_is_cumulative_and_date_ordered`.
- [ ] **Step 2: Run** `pytest tests/test_view_models.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** the view models, then the page: account selector (All plus each account), metric tiles, accounts table, findings-by-type bar chart, savings trend line. Add `scripts/seed_demo_data.py` to insert a few historical records so the dashboard is not empty. Check it by hand against the real table.
- [ ] **Step 4: Run** `pytest tests/test_view_models.py -v`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: dashboard with per-account cost avoidance`.

### Task 8C: Ask prompt (store-backed Q&A)

**Files:**
- Create: `costwarden/agents/qa.py`, `costwarden/tools/store_tools.py`, `tests/test_qa.py`
- Modify: `costwarden/ui/app.py` (Ask tab with chat input and history)

**Interfaces:**
- Consumes: `Store`, `get_llm`.
- Produces: `last_cleanup(store, account_id=None) -> dict | None`, `savings_between(store, start: str, end: str, account_id=None) -> dict`, `cleanups_by_status(store, status: str) -> list[dict]`, `top_resource_types(store, n: int = 3) -> list[dict]`; `answer(question: str, store: Store, llm) -> Answer` (`Answer(text: str, tool: str | None, data: dict | None)`). The LLM selects one tool and arguments (JSON); the code runs it and renders `text` from `data`.

- [ ] **Step 1: Write failing tests** with `FakeLLM` returning canned tool calls: `test_last_cleanup_question_uses_last_cleanup_tool` (the answer text contains the seeded PR URL and the exact savings figure), `test_savings_between_sums_merged_only`, `test_no_cleanups_says_so_without_inventing_numbers`, `test_unparseable_llm_output_returns_help_message_not_exception`, `test_unknown_tool_name_rejected`, `test_unknown_account_returns_clear_message`.
- [ ] **Step 2: Run** `pytest tests/test_qa.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** the four tools and `answer`. Validate the tool name and arguments against a whitelist; wrap the LLM call with `with_retry` once Task 9 exists. Suggested example questions appear as buttons in the UI.
- [ ] **Step 4: Run** `pytest -v`. Expected: PASS; ask "what was the last cleanup and how much did it avoid?" in the UI against the seeded real table.
- [ ] **Step 5: Commit** `feat: store-backed question answering prompt`.

**Milestone: after Task 8C the demo has history, a dashboard and the prompt.**

### Task 9: Retry, error recording and human handoff

**Files:**
- Create: `costwarden/resilience.py`, `tests/test_resilience.py`
- Modify: `costwarden/agents/discovery.py`, `costwarden/agents/supervisor.py`, `costwarden/accounts/session.py`

**Interfaces:**
- Produces: `with_retry(fn, *, attempts: int = 3, base_delay: float = 0.5, sleep=time.sleep)` (exponential backoff, re-raises the last exception); `ToolError(account_id: str, step: str, message: str)`; supervisor nodes catch exceptions and write `errors[account_id]`; the UI shows each error with a Retry/Skip choice, driven by a third interrupt `handle_error` (resume `{"action": "retry" | "skip"}`).

- [ ] **Step 1: Write failing tests**: `test_with_retry_succeeds_after_transient_failure`, `test_with_retry_raises_after_attempts`, `test_one_account_sts_failure_does_not_stop_others` (two accounts, one bad role ARN under moto; the other still has findings and `errors` has one key), `test_llm_unreachable_hands_off_to_human` (LLM stub raising `ConnectionError` leads to a pending `handle_error` interrupt), `test_skip_ends_account_cleanly`.
- [ ] **Step 2: Run** `pytest tests/test_resilience.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** and wrap boto3 calls, `get_session`, the GitHub client and LLM calls with `with_retry`.
- [ ] **Step 4: Run** the full suite `pytest -v`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: retries, per-account error isolation and human handoff`.

### Task 10: LLM steps (summary and risk write-up, Nebius)

**Files:**
- Create: `costwarden/agents/narrative.py`, `tests/test_narrative.py`
- Modify: `costwarden/agents/supervisor.py`, `costwarden/agents/refactor.py`

**Interfaces:**
- Consumes: `get_llm`.
- Produces: `rank_findings(llm, findings: list[Finding]) -> list[Finding]` (LLM orders by risk and savings; unknown IDs from the model are ignored and missing ones are appended in the original order); `write_risk_summary(llm, account: Account, result: RefactorResult) -> str` (runs on the provider named by `RISK_SUMMARY_PROVIDER`, default `nebius`, falling back to the main provider if no key is set, with a log line).

- [ ] **Step 1: Write failing tests** with `FakeLLM`: `test_rank_preserves_all_findings_when_llm_returns_garbage`, `test_rank_applies_valid_order`, `test_summary_included_in_pr_body`, `test_summary_falls_back_when_no_nebius_key`.
- [ ] **Step 2: Run** `pytest tests/test_narrative.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement**; prompts live as module constants. Do one live call to Ollama and one to Nebius when reachable and note the results for the write-up.
- [ ] **Step 4: Run** `pytest -v`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: llm ranking and risk summary with nebius`.

### Task 11: Multi-account demo

**Files:**
- Create: `config/accounts.demo-multi.yaml`, `tests/test_multi_account.py`
- Modify: `costwarden/ui/app.py` (account selector and per-account tabs)

**Interfaces:**
- Consumes: the whole graph.
- Produces: a two-account registry config (second account has its own `tf_path` and `role_arn`); the UI groups findings, diffs, PRs and approvals per account.

- [ ] **Step 1: Write failing test** `test_two_accounts_get_separate_prs_and_approvals` (two moto-backed accounts, approve one and reject the other; one PR exists, one account has no push).
- [ ] **Step 2: Run** `pytest tests/test_multi_account.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** the config and UI grouping; no agent code changes are needed. If any agent needs editing to pass, that is a design bug to fix in the agent, not in the test.
- [ ] **Step 4: Run** `pytest -v`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: multi-account demo config and per-account UI`.

### Task 11A: Lambda handlers and deploy template (not deployed)

**Files:**
- Create: `costwarden/lambda_handlers.py`, `infra/template.yaml`, `Dockerfile.lambda`, `tests/test_lambda_handlers.py`

**Interfaces:**
- Produces: `discover_handler(event: dict, context) -> dict` (event `{"account_id": str}`; returns findings as JSON and writes nothing), `refactor_handler(event, context) -> dict`, `open_pr_handler(event, context) -> dict`, `execute_handler(event, context) -> dict`; each wraps the same function the local graph uses and returns `{"ok": bool, "data": ..., "error": str | None}`.

- [ ] **Step 1: Write failing tests**: `test_discover_handler_returns_findings_json` (moto), `test_handler_returns_error_payload_not_exception`, `test_unknown_account_id_returns_error`.
- [ ] **Step 2: Run** `pytest tests/test_lambda_handlers.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** the handlers; `infra/template.yaml` (SAM) defines the container-image functions with a 15-minute timeout and an execution role limited to read-only EC2/CloudWatch plus the DynamoDB table; `Dockerfile.lambda` installs `terraform` and `git`. Note in the README that the human-in-the-loop checkpointer needs a DynamoDB backend before the full pipeline moves to Lambda.
- [ ] **Step 4: Run** `pytest -v`. Expected: PASS. Run `sam validate` if SAM is installed.
- [ ] **Step 5: Commit** `feat: lambda handlers and deploy template`.

### Task 12: Docs, sandbox repo and submission material

**Files:**
- Create: `docs/submission/project-doc.md`, `docs/submission/demo-script.md`
- Modify: `README.md`

- [ ] **Step 1:** Update `README.md` with a quick start (venv, `.env`, `pytest`, `streamlit run`), the architecture diagram, the one-liner and the framework table from the spec.
- [ ] **Step 2:** Create the sandbox GitHub repo with the sample Terraform, set `GITHUB_TOKEN` and `GITHUB_REPO` in `.env`, and run one real PR end to end. Record the PR URL.
- [ ] **Step 3:** Write `project-doc.md` in the handout's structure (overview, data used, prompts used while vibe coding, iterations, learnings, which step used Nebius).
- [ ] **Step 4:** Write `demo-script.md` as a timed script of 5 minutes or less: happy path, the approval gate, the failure handoff (stop Ollama or break one account's role ARN), the multi-account tab.
- [ ] **Step 5: Run** the five seeded cases and record how many produced a correct draft PR and savings estimate (target 4 of 5); put the number in the doc. Commit `docs: submission material`.

---

## Self-review notes

- **Spec coverage:** account registry and session (Task 2), four discovery checks (3), fan-out supervisor (4), HCL refactor with validation (5), PR agent (6), interrupts, checkpointer and plan-only execution (7), Streamlit (8), retry and handoff (9), Ollama and Nebius (1, 10), multi-account demo (11), deliverables (12).
- **Deviation from spec, flagged above:** two interrupts instead of one.
- **Addendum coverage (store, dashboard, prompt, Lambda):** Tasks 8A, 8B, 8C and 11A. Real DynamoDB table `costwarden-cleanups` for the demo; moto in tests. Lambda is handlers plus template only, not deployed; the checkpointer stays SQLite locally.
- **Cut line if time runs out:** Tasks 1–8 are the minimum submission; then 8A–8C (the history, dashboard and prompt you asked for), then Task 9 (the handout says the build isn't finished until it survives a tool failure), then 10, 12 and 11A. Task 12's demo script and doc must not be dropped.
