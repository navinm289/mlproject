"""Official exam domain catalogs for common AWS certifications."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Domain:
    id: str
    name: str
    weight: float
    topics: tuple[str, ...]


@dataclass(frozen=True)
class Exam:
    code: str
    name: str
    pass_score: int
    domains: tuple[Domain, ...]


EXAMS: dict[str, Exam] = {
    "SAA-C03": Exam(
        code="SAA-C03",
        name="AWS Certified Solutions Architect – Associate",
        pass_score=720,
        domains=(
            Domain(
                id="secure",
                name="Design Secure Architectures",
                weight=0.30,
                topics=(
                    "IAM users/roles/policies",
                    "Encryption at rest and in transit",
                    "Network security (SGs, NACLs, VPC endpoints)",
                    "WAF / Shield / GuardDuty",
                    "Organizations and SCPs",
                ),
            ),
            Domain(
                id="resilient",
                name="Design Resilient Architectures",
                weight=0.26,
                topics=(
                    "Multi-AZ and high availability",
                    "Decoupling with SQS/SNS/EventBridge",
                    "Backup and disaster recovery (RTO/RPO)",
                    "Auto Scaling and Elastic Load Balancing",
                    "Multi-Region strategies",
                ),
            ),
            Domain(
                id="performance",
                name="Design High-Performing Architectures",
                weight=0.24,
                topics=(
                    "Compute selection (EC2, Lambda, containers)",
                    "Storage performance (EBS, S3, EFS)",
                    "Database selection and tuning",
                    "Caching (CloudFront, ElastiCache, DAX)",
                    "Networking performance",
                ),
            ),
            Domain(
                id="cost",
                name="Design Cost-Optimized Architectures",
                weight=0.20,
                topics=(
                    "Pricing models (On-Demand, RI, SP, Spot)",
                    "Right-sizing and Compute Optimizer",
                    "S3 storage classes and lifecycle",
                    "Data transfer cost control",
                    "Serverless for idle-capacity avoidance",
                ),
            ),
        ),
    ),
    "CLF-C02": Exam(
        code="CLF-C02",
        name="AWS Certified Cloud Practitioner",
        pass_score=700,
        domains=(
            Domain(
                id="cloud-concepts",
                name="Cloud Concepts",
                weight=0.24,
                topics=(
                    "AWS Cloud value proposition",
                    "Cloud economics",
                    "Cloud architecture design principles",
                ),
            ),
            Domain(
                id="security",
                name="Security and Compliance",
                weight=0.30,
                topics=(
                    "Shared Responsibility Model",
                    "IAM and access management",
                    "Compliance and governance concepts",
                ),
            ),
            Domain(
                id="technology",
                name="Cloud Technology and Services",
                weight=0.34,
                topics=(
                    "Compute, storage, database, networking",
                    "Global infrastructure",
                    "Deployment and operations tools",
                ),
            ),
            Domain(
                id="billing",
                name="Billing, Pricing, and Support",
                weight=0.12,
                topics=(
                    "Pricing models",
                    "Billing and cost management tools",
                    "AWS Support plans",
                ),
            ),
        ),
    ),
    "DVA-C02": Exam(
        code="DVA-C02",
        name="AWS Certified Developer – Associate",
        pass_score=720,
        domains=(
            Domain(
                id="development",
                name="Development with AWS Services",
                weight=0.32,
                topics=(
                    "Writing code for AWS services",
                    "AWS SDKs and CLIs",
                    "Data stores in application code",
                ),
            ),
            Domain(
                id="security",
                name="Security",
                weight=0.26,
                topics=(
                    "Authentication and authorization",
                    "Encryption",
                    "Sensitive data handling",
                ),
            ),
            Domain(
                id="deployment",
                name="Deployment",
                weight=0.24,
                topics=(
                    "CI/CD pipelines on AWS",
                    "Application deployment strategies",
                    "Infrastructure as code basics",
                ),
            ),
            Domain(
                id="troubleshooting",
                name="Troubleshooting and Optimization",
                weight=0.18,
                topics=(
                    "Debugging application code",
                    "Observability (logs, metrics, traces)",
                    "Performance optimization",
                ),
            ),
        ),
    ),
}


DEFAULT_EXAM = "SAA-C03"


def get_exam(code: str) -> Exam:
    key = code.strip().upper()
    if key not in EXAMS:
        known = ", ".join(sorted(EXAMS))
        raise ValueError(f"Unknown exam '{code}'. Supported: {known}")
    return EXAMS[key]


def resolve_domain(exam: Exam, domain_ref: str) -> Domain:
    ref = domain_ref.strip().lower()
    for domain in exam.domains:
        if domain.id == ref or domain.name.lower() == ref:
            return domain
        if ref in domain.name.lower():
            return domain
    ids = ", ".join(d.id for d in exam.domains)
    raise ValueError(f"Unknown domain '{domain_ref}' for {exam.code}. Use one of: {ids}")
