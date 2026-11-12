"""Tests for the AWS certification progress agent."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aws_cert_agent.catalog import get_exam, resolve_domain
from aws_cert_agent.cli import main
from aws_cert_agent.report import overall_readiness, suggest_plan, summarize
from aws_cert_agent.store import ProgressStore, default_progress


def test_catalog_saa_weights():
    exam = get_exam("SAA-C03")
    assert abs(sum(d.weight for d in exam.domains) - 1.0) < 1e-9
    assert resolve_domain(exam, "secure").id == "secure"
    assert resolve_domain(exam, "cost").name.startswith("Design Cost")


def test_init_log_status_plan(tmp_path: Path):
    progress = tmp_path / "progress.json"
    status = tmp_path / "STATUS.md"

    assert (
        main(
            [
                "--progress",
                str(progress),
                "--status",
                str(status),
                "init",
                "--exam",
                "SAA-C03",
            ]
        )
        == 0
    )
    assert progress.is_file()
    assert status.is_file()

    assert (
        main(
            [
                "--progress",
                str(progress),
                "--status",
                str(status),
                "log",
                "study",
                "--domain",
                "secure",
                "--minutes",
                "60",
                "--topics",
                "IAM users/roles/policies",
                "--notes",
                "IAM deep dive",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "--progress",
                str(progress),
                "--status",
                str(status),
                "log",
                "practice",
                "--domain",
                "cost",
                "--minutes",
                "45",
                "--score",
                "12",
                "--total",
                "20",
            ]
        )
        == 0
    )

    data = json.loads(progress.read_text(encoding="utf-8"))
    assert len(data["activities"]) == 2
    assert data["domains"]["secure"]["minutes"] == 60
    assert data["domains"]["cost"]["practice_total"] == 20

    summary = summarize(data)
    assert summary["total_minutes"] == 105
    assert 0 <= summary["overall_readiness"] <= 100

    plan = suggest_plan(data)
    assert len(plan) == 3
    assert all("focus_topics" in item for item in plan)

    assert main(["--progress", str(progress), "status"]) == 0
    assert main(["--progress", str(progress), "plan"]) == 0
    assert (
        main(
            [
                "--progress",
                str(progress),
                "--status",
                str(status),
                "set-goal",
                "--exam-date",
                "2026-09-15",
                "--weekly-minutes",
                "360",
            ]
        )
        == 0
    )
    refreshed = json.loads(progress.read_text(encoding="utf-8"))
    assert refreshed["target_exam_date"] == "2026-09-15"
    assert refreshed["goal_weekly_minutes"] == 360


def test_init_refuses_overwrite(tmp_path: Path):
    store = ProgressStore(tmp_path / "progress.json")
    store.init("CLF-C02")
    with pytest.raises(FileExistsError):
        store.init("CLF-C02")
    store.init("CLF-C02", force=True)
    assert store.load()["exam_code"] == "CLF-C02"


def test_default_progress_readiness_baseline():
    data = default_progress("DVA-C02")
    assert overall_readiness(data) > 0
