"""JSON-backed progress store for AWS certification activity."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from aws_cert_agent.catalog import DEFAULT_EXAM, get_exam

ACTIVITY_TYPES = ("study", "practice", "lab", "video", "review")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_progress(exam_code: str = DEFAULT_EXAM) -> dict[str, Any]:
    exam = get_exam(exam_code)
    return {
        "version": 1,
        "exam_code": exam.code,
        "exam_name": exam.name,
        "target_exam_date": None,
        "goal_weekly_minutes": 300,
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
        "domains": {
            d.id: {
                "name": d.name,
                "weight": d.weight,
                "confidence": 1,
                "minutes": 0,
                "practice_correct": 0,
                "practice_total": 0,
                "topics_covered": [],
            }
            for d in exam.domains
        },
        "activities": [],
        "milestones": [],
    }


class ProgressStore:
    def __init__(self, path: Path):
        self.path = path

    def exists(self) -> bool:
        return self.path.is_file()

    def load(self) -> dict[str, Any]:
        if not self.exists():
            raise FileNotFoundError(
                f"No progress file at {self.path}. Run: aws-cert init"
            )
        with self.path.open(encoding="utf-8") as fh:
            return json.load(fh)

    def save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = deepcopy(data)
        data["updated_at"] = utc_now_iso()
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=False)
            fh.write("\n")
        tmp.replace(self.path)

    def init(self, exam_code: str = DEFAULT_EXAM, force: bool = False) -> dict[str, Any]:
        if self.exists() and not force:
            raise FileExistsError(
                f"Progress already exists at {self.path}. Use --force to reset."
            )
        data = default_progress(exam_code)
        self.save(data)
        return data

    def log_activity(
        self,
        *,
        activity_type: str,
        minutes: int = 0,
        domain: str | None = None,
        notes: str = "",
        score: int | None = None,
        total: int | None = None,
        topics: list[str] | None = None,
        when: str | None = None,
    ) -> dict[str, Any]:
        if activity_type not in ACTIVITY_TYPES:
            raise ValueError(
                f"Unknown activity type '{activity_type}'. "
                f"Use one of: {', '.join(ACTIVITY_TYPES)}"
            )
        if minutes < 0:
            raise ValueError("minutes must be >= 0")

        data = self.load()
        exam = get_exam(data["exam_code"])
        domain_id = None
        if domain:
            domain_id = resolve_and_ensure_domain(data, exam, domain).id

        activity = {
            "id": str(uuid4()),
            "type": activity_type,
            "timestamp": when or utc_now_iso(),
            "minutes": minutes,
            "domain": domain_id,
            "notes": notes.strip(),
            "score": score,
            "total": total,
            "topics": topics or [],
        }
        data["activities"].append(activity)

        if domain_id:
            bucket = data["domains"][domain_id]
            bucket["minutes"] += minutes
            for topic in topics or []:
                if topic and topic not in bucket["topics_covered"]:
                    bucket["topics_covered"].append(topic)
            if activity_type == "practice" and score is not None and total:
                bucket["practice_correct"] += score
                bucket["practice_total"] += total
                accuracy = bucket["practice_correct"] / bucket["practice_total"]
                # Map accuracy to 1-5 confidence.
                bucket["confidence"] = max(1, min(5, round(accuracy * 5)))
            elif activity_type in {"study", "lab", "video", "review"} and minutes > 0:
                # Light confidence bump for deliberate practice time.
                bump = 1 if minutes >= 45 else 0
                bucket["confidence"] = min(5, bucket["confidence"] + bump)

        self.save(data)
        return activity


def resolve_and_ensure_domain(data: dict[str, Any], exam, domain_ref: str):
    from aws_cert_agent.catalog import resolve_domain

    domain = resolve_domain(exam, domain_ref)
    if domain.id not in data["domains"]:
        data["domains"][domain.id] = {
            "name": domain.name,
            "weight": domain.weight,
            "confidence": 1,
            "minutes": 0,
            "practice_correct": 0,
            "practice_total": 0,
            "topics_covered": [],
        }
    return domain
