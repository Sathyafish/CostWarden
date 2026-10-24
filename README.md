# CostWarden
Suggests proactive, continuous guarding against cloud waste.

Architecting a multi-agent automated infrastructure lifecycle system using LangGraph and LangChain provides a solid, deterministic state machine pattern for this workflow.

By structuring this around a Supervisor Architecture, a central supervisor agent routes tasks, validates state transitions, and enforces guardrails (like mandatory human PR approval) before executing infrastructure mutations.

1. System Architecture & Agent Boundaries
                 [ Scheduled Trigger (Cron / AWS EventBridge) ]
                                      │
                                      ▼
                      ┌───────────────────────────────┐
                      │    Supervisor Agent (Zeve)     │
                      └───────────────┬───────────────┘
                                      │
         ┌────────────────────────────┼────────────────────────────┐
         │                            │                            │
         ▼                            ▼                            ▼
┌─────────────────┐          ┌─────────────────┐          ┌─────────────────┐
│ Discovery Agent │          │ Refactoring     │          │ VCS & PR        │
│ (AWS Advisor)   │          │ Agent           │          │ Agent           │
└─────────────────┘          └─────────────────┘          └─────────────────┘
                                                                   │
                                                                   ▼
                                                         [ Human PR Review ]
                                                                   │
                                                                   ▼
                                                          ┌─────────────────┐
                                                          │ Execution       │
                                                          │ Agent (Apply)   │
                                                          └─────────────────┘
Agent Roles & Responsibilities
Supervisor Agent ("Zeve"):

Manages overall state transitions and routing.

Evaluates sub-agent outputs against acceptance criteria.

Pauses state graph execution for external Human-in-the-Loop (HITL) approval prior to applying code changes.

Discovery Agent (AWS Trusted Advisor / Cost Explorer):

Queries AWS Trusted Advisor, AWS Cost Optimization Hub, and AWS CloudWatch via AWS SDK (boto3).

Filters actionable idle/unattached resources (e.g., unattached EBS volumes, idle NAT Gateways, released Elastic IPs, aged snapshots).

Generates a normalized inventory payload of resource IDs, ARNs, and target Terraform workspaces/files.

Refactoring Agent (Terraform / OpenTofu):

Maps unattached/idle AWS resources to target HCL configuration files in the repository.

Generates declarative edits (e.g., setting count = 0, adding lifecycle hooks, or removing resource blocks) using AST-aware parsing tools (such as python-hcl2) rather than raw string replacement.

Runs local validation (terraform fmt, terraform validate, tflint).

VCS & PR Agent (GitHub / GitLab):

Creates a feature branch (e.g., budget-agent/cleanup-YYYY-MM-DD).

Commits the updated HCL and pushes changes.

Opens a Pull Request with an auto-generated breakdown: estimated monthly savings, targeted resources, and risk severity scores.

Execution Agent (CI/CD & Provisioning):

Triggers after human approval/merge of the PR.

Executes plan/apply actions via CI/CD pipelines (e.g., GitHub Actions, Atlantis, or Terraform Cloud/Spacelift API).

Verifies state convergence and posts execution summaries back to the supervisor state.
