data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_caller_identity" "current" {}

# Cleanup history: one item per cleanup run per account.
resource "aws_dynamodb_table" "cleanups" {
  name         = var.table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "account_id"
  range_key    = "ts_run"

  attribute {
    name = "account_id"
    type = "S"
  }

  attribute {
    name = "ts_run"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }
}

# Least-privilege permissions for the agents (local run or Lambda).
# Reads are broad; the only write is to the history table.
data "aws_iam_policy_document" "app" {
  statement {
    sid = "HistoryTable"
    actions = [
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:GetItem",
      "dynamodb:Query",
      "dynamodb:Scan",
    ]
    resources = [aws_dynamodb_table.cleanups.arn]
  }

  statement {
    sid = "CheckpointTable"
    actions = [
      "dynamodb:PutItem",
      "dynamodb:GetItem",
    ]
    resources = [aws_dynamodb_table.checkpoints.arn]
  }

  statement {
    sid       = "InvokeCostWardenFunctions"
    actions   = ["lambda:InvokeFunction"]
    resources = ["arn:aws:lambda:${var.region}:${data.aws_caller_identity.current.account_id}:function:costwarden-*"]
  }

  statement {
    sid = "DiscoveryReadOnly"
    actions = [
      "ec2:DescribeVolumes",
      "ec2:DescribeAddresses",
      "ec2:DescribeNatGateways",
      "ec2:DescribeSnapshots",
      "ec2:DescribeInstances",
      "cloudwatch:GetMetricStatistics",
      "cloudwatch:GetMetricData",
      "cloudwatch:ListMetrics",
    ]
    resources = ["*"]
  }

  # Org mode: allow assuming the read-only role in member accounts.
  statement {
    sid       = "AssumeMemberRoles"
    actions   = ["sts:AssumeRole"]
    resources = ["arn:aws:iam::*:role/${var.member_role_name}"]
  }
}

resource "aws_iam_policy" "app" {
  name   = "costwarden-app"
  policy = data.aws_iam_policy_document.app.json
}

# Execution role for the Lambda handlers (functions are deployed separately).
data "aws_iam_policy_document" "lambda_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "costwarden-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

resource "aws_iam_role_policy_attachment" "lambda_app" {
  role       = aws_iam_role.lambda.name
  policy_arn = aws_iam_policy.app.arn
}

resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Optional seeded waste so Discovery has something real to find.
resource "aws_ebs_volume" "demo_unattached" {
  count             = var.create_demo_waste ? 1 : 0
  availability_zone = data.aws_availability_zones.available.names[0]
  size              = 1
  type              = "gp3"

  tags = {
    Name       = "costwarden-demo-unattached"
    CostWarden = "demo-waste"
  }
}

resource "aws_eip" "demo_unassociated" {
  count  = var.create_demo_waste ? 1 : 0
  domain = "vpc"

  tags = {
    Name       = "costwarden-demo-unassociated"
    CostWarden = "demo-waste"
  }
}
