"""Progress reporting and study planning helpers."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from aws_cert_agent.catalog import get_exam


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def domain_readiness(domain: dict[str, Any]) -> float:
    """Blend confidence and practice accuracy into 0-100 readiness."""
    confidence = float(domain.get("confidence", 1))
    practice_total = int(domain.get("practice_total", 0))
    if practice_total > 0:
        accuracy = domain["practice_correct"] / practice_total
        practice_score = accuracy * 100
    else:
        practice_score = confidence / 5 * 55
    confidence_score = confidence / 5 * 100
    # Prefer practice evidence when available.
    weight_practice = 0.65 if practice_total >= 10 else 0.35
    return round(
        practice_score * weight_practice + confidence_score * (1 - weight_practice),
        1,
    )


def overall_readiness(data: dict[str, Any]) -> float:
    exam = get_exam(data["exam_code"])
    weighted = 0.0
    for domain in exam.domains:
        bucket = data["domains"][domain.id]
        weighted += domain_readiness(bucket) * domain.weight
    return round(weighted, 1)


def week_minutes(data: dict[str, Any], now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    start = now - timedelta(days=7)
    total = 0
    for activity in data.get("activities", []):
        ts = _parse_ts(activity["timestamp"])
        if ts >= start:
            total += int(activity.get("minutes") or 0)
    return total


def summarize(data: dict[str, Any]) -> dict[str, Any]:
    exam = get_exam(data["exam_code"])
    domains = []
    for domain in exam.domains:
        bucket = data["domains"][domain.id]
        accuracy = None
        if bucket["practice_total"]:
            accuracy = round(
                100 * bucket["practice_correct"] / bucket["practice_total"], 1
            )
        domains.append(
            {
                "id": domain.id,
                "name": domain.name,
                "weight": domain.weight,
                "minutes": bucket["minutes"],
                "confidence": bucket["confidence"],
                "practice_accuracy": accuracy,
                "practice_total": bucket["practice_total"],
                "readiness": domain_readiness(bucket),
                "topics_covered": list(bucket.get("topics_covered", [])),
            }
        )

    by_type: dict[str, int] = defaultdict(int)
    for activity in data.get("activities", []):
        by_type[activity["type"]] += 1

    return {
        "exam_code": data["exam_code"],
        "exam_name": data["exam_name"],
        "target_exam_date": data.get("target_exam_date"),
        "overall_readiness": overall_readiness(data),
        "total_minutes": sum(d["minutes"] for d in domains),
        "week_minutes": week_minutes(data),
        "goal_weekly_minutes": data.get("goal_weekly_minutes", 300),
        "activity_counts": dict(by_type),
        "activity_total": len(data.get("activities", [])),
        "domains": domains,
    }


def suggest_plan(data: dict[str, Any], slots: int = 3) -> list[dict[str, Any]]:
    """Suggest next focus areas: low readiness, high exam weight first."""
    summary = summarize(data)
    ranked = sorted(
        summary["domains"],
        key=lambda d: (d["readiness"], -d["weight"]),
    )
    exam = get_exam(data["exam_code"])
    topic_map = {d.id: d.topics for d in exam.domains}
    plan = []
    for domain in ranked[:slots]:
        covered = set(domain["topics_covered"])
        remaining = [t for t in topic_map[domain["id"]] if t not in covered]
        focus = remaining[:2] or list(topic_map[domain["id"]][:2])
        action = "practice exam set" if domain["practice_total"] < 20 else "targeted review"
        plan.append(
            {
                "domain_id": domain["id"],
                "domain_name": domain["name"],
                "readiness": domain["readiness"],
                "weight": domain["weight"],
                "action": action,
                "focus_topics": focus,
                "why": (
                    f"Readiness {domain['readiness']}% with "
                    f"{int(domain['weight'] * 100)}% exam weight"
                ),
            }
        )
    return plan


def render_status_markdown(data: dict[str, Any]) -> str:
    summary = summarize(data)
    plan = suggest_plan(data)
    lines = [
        f"# AWS Certification Progress — {summary['exam_code']}",
        "",
        f"**{summary['exam_name']}**",
        "",
        f"- Overall readiness: **{summary['overall_readiness']}%**",
        f"- Total study minutes: **{summary['total_minutes']}**",
        (
            f"- This week: **{summary['week_minutes']}** / "
            f"{summary['goal_weekly_minutes']} goal minutes"
        ),
        f"- Logged activities: **{summary['activity_total']}**",
    ]
    if summary["target_exam_date"]:
        lines.append(f"- Target exam date: **{summary['target_exam_date']}**")
    lines.extend(["", "## Domains", ""])
    lines.append("| Domain | Weight | Minutes | Confidence | Practice | Readiness |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for d in summary["domains"]:
        practice = (
            f"{d['practice_accuracy']}%"
            if d["practice_accuracy"] is not None
            else "—"
        )
        lines.append(
            f"| {d['name']} ({d['id']}) | {int(d['weight'] * 100)}% | "
            f"{d['minutes']} | {d['confidence']}/5 | {practice} | {d['readiness']}% |"
        )

    lines.extend(["", "## Suggested next focus", ""])
    for i, item in enumerate(plan, start=1):
        topics = "; ".join(item["focus_topics"])
        lines.append(
            f"{i}. **{item['domain_name']}** — {item['action']} "
            f"({item['why']}). Topics: {topics}"
        )

    recent = sorted(
        data.get("activities", []),
        key=lambda a: a["timestamp"],
        reverse=True,
    )[:8]
    lines.extend(["", "## Recent activity", ""])
    if not recent:
        lines.append("_No activities logged yet._")
    else:
        for activity in recent:
            domain = activity.get("domain") or "general"
            note = f" — {activity['notes']}" if activity.get("notes") else ""
            score = ""
            if activity.get("score") is not None and activity.get("total"):
                pct = round(100 * activity["score"] / activity["total"], 1)
                score = f", score {activity['score']}/{activity['total']} ({pct}%)"
            lines.append(
                f"- `{activity['timestamp']}` **{activity['type']}** "
                f"({activity.get('minutes', 0)}m, {domain}){score}{note}"
            )

    lines.append("")
    return "\n".join(lines)


def render_status_text(data: dict[str, Any]) -> str:
    summary = summarize(data)
    plan = suggest_plan(data)
    lines = [
        f"{summary['exam_code']} — {summary['exam_name']}",
        f"Overall readiness: {summary['overall_readiness']}%",
        (
            f"Minutes: {summary['total_minutes']} total | "
            f"{summary['week_minutes']}/{summary['goal_weekly_minutes']} this week"
        ),
        "",
        "Domains:",
    ]
    for d in summary["domains"]:
        practice = (
            f", practice {d['practice_accuracy']}%"
            if d["practice_accuracy"] is not None
            else ""
        )
        lines.append(
            f"  - {d['id']}: readiness {d['readiness']}% "
            f"(weight {int(d['weight'] * 100)}%, {d['minutes']}m, "
            f"confidence {d['confidence']}/5{practice})"
        )
    lines.extend(["", "Next focus:"])
    for i, item in enumerate(plan, start=1):
        lines.append(
            f"  {i}. {item['domain_id']} — {item['action']}: "
            + ", ".join(item["focus_topics"])
        )
    return "\n".join(lines) + "\n"
