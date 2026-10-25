variable "region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "us-east-1"
}

variable "table_name" {
  description = "DynamoDB table that stores cleanup history."
  type        = string
  default     = "costwarden-cleanups"
}

variable "checkpoint_table_name" {
  description = "DynamoDB table holding run checkpoints (approval pauses survive across Lambda calls)."
  type        = string
  default     = "costwarden-checkpoints"
}

variable "lambda_zip_path" {
  description = "Path to the Lambda package built by scripts/build_lambda.sh."
  type        = string
  default     = "../../build/lambda.zip"
}

variable "lambda_llm_provider" {
  description = "LLM provider for the Lambdas: nebius, ollama or fake. Lambdas are not in a VPC, so they cannot reach a private Ollama server unless you add VPC access."
  type        = string
  default     = "nebius"
}

variable "llm_model" {
  type    = string
  default = "llama3.1"
}

variable "ollama_base_url" {
  type    = string
  default = "http://10.135.128.9:11434"
}

variable "nebius_api_key" {
  description = "Nebius Token Factory API key (stored as a Lambda environment variable)."
  type        = string
  default     = ""
  sensitive   = true
}

variable "nebius_model" {
  type    = string
  default = "meta-llama/Llama-3.3-70B-Instruct"
}

variable "github_token" {
  description = "GitHub token with repo access to the sandbox repository (stored as a Lambda environment variable)."
  type        = string
  default     = ""
  sensitive   = true
}

variable "github_repo" {
  description = "Sandbox repository as owner/name. Empty means the Lambdas use a fake client that opens no real PRs."
  type        = string
  default     = ""
}

variable "api_key" {
  description = "Shared secret the React app sends as x-api-key (16+ characters). The API URL is public, so this is the only gate on starting runs; treat it as demo-level protection."
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.api_key) >= 16
    error_message = "api_key must be at least 16 characters."
  }
}

variable "allow_demo_seed" {
  description = "Allow POST /api/demo/seed to insert demo history into the real table. Leave false outside demos."
  type        = bool
  default     = false
}

variable "cors_origins" {
  description = "Origins allowed to call the API from a browser. The CloudFront origin is added automatically when hosting is enabled."
  type        = list(string)
  default     = ["http://localhost:5173", "http://127.0.0.1:5173"]
}

variable "enable_frontend_hosting" {
  description = "Host the built React app (frontend/dist) on S3 behind CloudFront. Run `npm run build` in frontend/ first."
  type        = bool
  default     = false
}

variable "member_role_name" {
  description = "Name of the read-only role the agents assume in other accounts (org mode). Unused in single-account mode."
  type        = string
  default     = "CostWardenReadOnly"
}

variable "create_demo_waste" {
  description = "Create an unattached EBS volume and an unassociated Elastic IP for Discovery to find. Small ongoing cost (about $3.70 per month); destroy when done."
  type        = bool
  default     = false
}

variable "tags" {
  description = "Tags applied to every resource."
  type        = map(string)
  default = {
    Project = "CostWarden"
  }
}
