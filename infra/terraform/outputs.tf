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
