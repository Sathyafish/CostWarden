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
