# Per-team, per-environment IRSA roles for JupyterHub.
# Creates:
#   - jhub-<team>-singleuser : role assumed by notebook pods (SA jhub-<team>/jupyterhub-singleuser)
#   - jhub-<team>-hub        : role for the hub pod (SA jhub-<team>/hub)
#
# Data isolation: singleuser role can READ curated/<team> + warehouse and
# WRITE only scratch/<team>/*. A team cannot touch another team's prefixes.

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

variable "team" { type = string }
variable "environment" { type = string }
variable "lake_bucket" { type = string }
variable "eks_oidc_provider_arn" { type = string }
variable "eks_oidc_provider_url" {
  type        = string
  description = "OIDC provider URL without https:// (e.g. oidc.eks.us-east-1.amazonaws.com/id/ABC123)"
}

locals {
  namespace       = "jhub-${var.team}"
  singleuser_sa   = "system:serviceaccount:${local.namespace}:jupyterhub-singleuser"
  hub_sa          = "system:serviceaccount:${local.namespace}:hub"
  singleuser_role = "jhub-${var.team}-singleuser"
  hub_role        = "jhub-${var.team}-hub"
}

# ---------- single-user (notebook pod) role ----------
data "aws_iam_policy_document" "singleuser_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    effect  = "Allow"
    principals {
      type        = "Federated"
      identifiers = [var.eks_oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${var.eks_oidc_provider_url}:sub"
      values   = [local.singleuser_sa]
    }
    condition {
      test     = "StringEquals"
      variable = "${var.eks_oidc_provider_url}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "singleuser_s3" {
  statement {
    sid     = "ListLakeBucketScoped"
    effect  = "Allow"
    actions = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = ["arn:aws:s3:::${var.lake_bucket}"]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        "warehouse/*",
        "curated/${var.team}/*",
        "scratch/${var.team}/*",
      ]
    }
  }
  statement {
    sid    = "ReadCuratedAndWarehouse"
    effect = "Allow"
    actions = ["s3:GetObject"]
    resources = [
      "arn:aws:s3:::${var.lake_bucket}/warehouse/*",
      "arn:aws:s3:::${var.lake_bucket}/curated/${var.team}/*",
    ]
  }
  statement {
    sid    = "WriteTeamScratchOnly"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
    ]
    resources = [
      "arn:aws:s3:::${var.lake_bucket}/scratch/${var.team}/*",
    ]
  }
}

resource "aws_iam_role" "singleuser" {
  name               = local.singleuser_role
  assume_role_policy = data.aws_iam_policy_document.singleuser_trust.json
  tags = {
    team        = var.team
    environment = var.environment
    component   = "jupyterhub-singleuser"
  }
}

resource "aws_iam_role_policy" "singleuser_s3" {
  name   = "${local.singleuser_role}-s3"
  role   = aws_iam_role.singleuser.id
  policy = data.aws_iam_policy_document.singleuser_s3.json
}

# ---------- hub role (minimal; no S3 data access) ----------
data "aws_iam_policy_document" "hub_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    effect  = "Allow"
    principals {
      type        = "Federated"
      identifiers = [var.eks_oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${var.eks_oidc_provider_url}:sub"
      values   = [local.hub_sa]
    }
    condition {
      test     = "StringEquals"
      variable = "${var.eks_oidc_provider_url}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "hub" {
  name               = local.hub_role
  assume_role_policy = data.aws_iam_policy_document.hub_trust.json
  tags = {
    team        = var.team
    environment = var.environment
    component   = "jupyterhub-hub"
  }
}

output "singleuser_role_arn" {
  value = aws_iam_role.singleuser.arn
}

output "hub_role_arn" {
  value = aws_iam_role.hub.arn
}
