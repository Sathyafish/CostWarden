# Agent Lambdas, supervisor Lambda, checkpoint table and package bucket.
# Build the package first: scripts/build_lambda.sh (writes build/lambda.zip).

locals {
  cors_origins = concat(
    var.cors_origins,
    var.enable_frontend_hosting ? ["https://${aws_cloudfront_distribution.frontend[0].domain_name}"] : [],
  )

  agents = {
    discover = { handler = "costwarden.lambda_handlers.discover_handler", timeout = 300 }
    refactor = { handler = "costwarden.lambda_handlers.refactor_handler", timeout = 300 }
    open_pr  = { handler = "costwarden.lambda_handlers.open_pr_handler", timeout = 300 }
    execute  = { handler = "costwarden.lambda_handlers.execute_handler", timeout = 300 }
  }

  common_env = {
    AWS_REGION            = var.region
    LLM_PROVIDER          = var.lambda_llm_provider
    LLM_MODEL             = var.llm_model
    OLLAMA_BASE_URL       = var.ollama_base_url
    NEBIUS_API_KEY        = var.nebius_api_key
    NEBIUS_MODEL          = var.nebius_model
    RISK_SUMMARY_PROVIDER = var.lambda_llm_provider
    GITHUB_TOKEN          = var.github_token
    GITHUB_REPO           = var.github_repo
    TF_SOURCE             = "github"
    ACCOUNTS_FILE         = "/var/task/config/accounts.yaml"
    STORE_BACKEND         = "dynamo"
    DYNAMODB_TABLE        = var.table_name
  }
}

resource "aws_dynamodb_table" "checkpoints" {
  name         = var.checkpoint_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "thread_id"

  attribute {
    name = "thread_id"
    type = "S"
  }

  server_side_encryption {
    enabled = true
  }
}

resource "aws_s3_bucket" "package" {
  bucket_prefix = "costwarden-lambda-"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "package" {
  bucket                  = aws_s3_bucket.package.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_object" "package" {
  bucket = aws_s3_bucket.package.id
  key    = "lambda-${filemd5(var.lambda_zip_path)}.zip"
  source = var.lambda_zip_path
  etag   = filemd5(var.lambda_zip_path)
}

resource "aws_cloudwatch_log_group" "fn" {
  for_each          = toset(concat([for k, _ in local.agents : "costwarden-${k}"], ["costwarden-supervisor", "costwarden-api"]))
  name              = "/aws/lambda/${each.key}"
  retention_in_days = 14
}

resource "aws_lambda_function" "agent" {
  for_each = local.agents

  function_name = "costwarden-${each.key}"
  role          = aws_iam_role.lambda.arn
  runtime       = "python3.12"
  architectures = ["x86_64"]
  handler       = each.value.handler
  timeout       = each.value.timeout
  memory_size   = 1024

  s3_bucket        = aws_s3_bucket.package.id
  s3_key           = aws_s3_object.package.key
  source_code_hash = filebase64sha256(var.lambda_zip_path)

  environment {
    variables = local.common_env
  }

  depends_on = [aws_cloudwatch_log_group.fn, aws_iam_role_policy_attachment.lambda_logs]
}

resource "aws_lambda_function" "supervisor" {
  function_name = "costwarden-supervisor"
  role          = aws_iam_role.lambda.arn
  runtime       = "python3.12"
  architectures = ["x86_64"]
  handler       = "costwarden.lambda_handlers.supervisor_handler"
  timeout       = 900
  memory_size   = 1024

  s3_bucket        = aws_s3_bucket.package.id
  s3_key           = aws_s3_object.package.key
  source_code_hash = filebase64sha256(var.lambda_zip_path)

  environment {
    variables = merge(local.common_env, {
      AGENT_RUNTIME         = "lambda"
      AGENT_FUNCTION_PREFIX = "costwarden"
      CHECKPOINT_BACKEND    = "dynamo"
      CHECKPOINT_TABLE      = aws_dynamodb_table.checkpoints.name
    })
  }

  depends_on = [aws_cloudwatch_log_group.fn, aws_iam_role_policy_attachment.lambda_logs]
}

# HTTP API for the React app: one Lambda (FastAPI via Mangum) behind a function URL.
# Function URLs have no 30 second limit, so a run that scans several accounts is not cut off.
# Authentication is the shared x-api-key checked inside the app; CORS is handled by the app too,
# so the URL itself sets no CORS headers.
resource "aws_lambda_function" "api" {
  function_name = "costwarden-api"
  role          = aws_iam_role.lambda.arn
  runtime       = "python3.12"
  architectures = ["x86_64"]
  handler       = "costwarden.api.lambda_api.handler"
  timeout       = 900
  memory_size   = 1024

  s3_bucket        = aws_s3_bucket.package.id
  s3_key           = aws_s3_object.package.key
  source_code_hash = filebase64sha256(var.lambda_zip_path)

  environment {
    variables = merge(local.common_env, {
      AGENT_RUNTIME         = "lambda"
      AGENT_FUNCTION_PREFIX = "costwarden"
      API_KEY               = var.api_key
      CORS_ORIGINS          = join(",", local.cors_origins)
      ALLOW_DEMO_SEED       = tostring(var.allow_demo_seed)
    })
  }

  depends_on = [aws_cloudwatch_log_group.fn, aws_iam_role_policy_attachment.lambda_logs]
}

resource "aws_lambda_function_url" "api" {
  function_name      = aws_lambda_function.api.function_name
  authorization_type = "NONE"
}

resource "aws_lambda_permission" "api_url" {
  statement_id           = "AllowPublicFunctionUrl"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.api.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

resource "aws_lambda_permission" "api_url_invoke" {
  statement_id             = "AllowPublicInvokeViaUrl"
  action                   = "lambda:InvokeFunction"
  function_name            = aws_lambda_function.api.function_name
  principal                = "*"
  invoked_via_function_url = true
}
