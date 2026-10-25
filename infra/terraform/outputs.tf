output "table_name" {
  description = "Set DYNAMODB_TABLE to this value."
  value       = aws_dynamodb_table.cleanups.name
}

output "table_arn" {
  value = aws_dynamodb_table.cleanups.arn
}

output "app_policy_arn" {
  description = "Attach to the IAM user or role that runs the agents locally."
  value       = aws_iam_policy.app.arn
}

output "lambda_role_arn" {
  description = "Execution role for the Lambda handlers."
  value       = aws_iam_role.lambda.arn
}

output "demo_waste" {
  description = "IDs of the seeded waste resources (empty unless create_demo_waste is true)."
  value = {
    volume_id     = join("", aws_ebs_volume.demo_unattached[*].id)
    allocation_id = join("", aws_eip.demo_unassociated[*].id)
  }
}

output "checkpoint_table_name" {
  value = aws_dynamodb_table.checkpoints.name
}

output "supervisor_function" {
  description = "Set AGENT_RUNTIME=lambda and AGENT_FUNCTION_PREFIX=costwarden to make the Streamlit app call this."
  value       = aws_lambda_function.supervisor.function_name
}

output "agent_functions" {
  value = [for f in aws_lambda_function.agent : f.function_name]
}

output "package_bucket" {
  value = aws_s3_bucket.package.id
}

output "api_url" {
  description = "Paste into the app's Settings (or it is picked up from config.js when hosted)."
  value       = aws_lambda_function_url.api.function_url
}

output "frontend_url" {
  description = "Hosted React app (empty unless enable_frontend_hosting is true)."
  value       = var.enable_frontend_hosting ? "https://${aws_cloudfront_distribution.frontend[0].domain_name}" : ""
}
