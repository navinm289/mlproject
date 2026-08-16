# Root wiring for per-team IRSA in ONE environment (one EKS cluster).
# Apply this in each environment (dev/uat/prod) with that env's tfvars, since
# each environment is a separate cluster/account with its own OIDC provider.

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "environment" {
  type        = string
  description = "dev | uat | prod"
}

variable "lake_bucket" {
  type        = string
  description = "S3 lakehouse bucket for this environment"
}

variable "eks_oidc_provider_arn" { type = string }
variable "eks_oidc_provider_url" {
  type        = string
  description = "OIDC provider URL without https://"
}

variable "teams" {
  type        = list(string)
  description = "Teams to provision Hubs/IRSA for in this environment"
  default     = ["retail-cards", "brands"]
}

module "team_irsa" {
  for_each = toset(var.teams)
  source   = "./modules/team-irsa"

  team                  = each.value
  environment           = var.environment
  lake_bucket           = var.lake_bucket
  eks_oidc_provider_arn = var.eks_oidc_provider_arn
  eks_oidc_provider_url = var.eks_oidc_provider_url
}

output "singleuser_role_arns" {
  value = { for t, m in module.team_irsa : t => m.singleuser_role_arn }
}

output "hub_role_arns" {
  value = { for t, m in module.team_irsa : t => m.hub_role_arn }
}
