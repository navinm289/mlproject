"""CLI entrypoint for the AWS certification progress agent."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from aws_cert_agent.catalog import DEFAULT_EXAM, EXAMS
from aws_cert_agent.report import render_status_markdown, render_status_text, suggest_plan
from aws_cert_agent.store import ProgressStore

DEFAULT_PROGRESS_PATH = Path("aws-cert/progress.json")
DEFAULT_STATUS_PATH = Path("aws-cert/STATUS.md")


def _store_from_args(args: argparse.Namespace) -> ProgressStore:
    return ProgressStore(Path(args.progress))


def cmd_init(args: argparse.Namespace) -> int:
    store = _store_from_args(args)
    data = store.init(exam_code=args.exam, force=args.force)
    status_path = Path(args.status)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(render_status_markdown(data), encoding="utf-8")
    print(f"Initialized {data['exam_code']} progress at {store.path}")
    print(f"Wrote status dashboard to {status_path}")
    return 0


def cmd_log(args: argparse.Namespace) -> int:
    store = _store_from_args(args)
    topics = [t.strip() for t in (args.topics or "").split(",") if t.strip()]
    activity = store.log_activity(
        activity_type=args.type,
        minutes=args.minutes,
        domain=args.domain,
        notes=args.notes or "",
        score=args.score,
        total=args.total,
        topics=topics,
        when=args.when,
    )
    data = store.load()
    status_path = Path(args.status)
    status_path.write_text(render_status_markdown(data), encoding="utf-8")
    print(
        f"Logged {activity['type']} ({activity['minutes']}m"
        + (f", domain={activity['domain']}" if activity["domain"] else "")
        + f") → {activity['id']}"
    )
    print(f"Updated {status_path}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    store = _store_from_args(args)
    data = store.load()
    if args.json:
        from aws_cert_agent.report import summarize

        print(json.dumps(summarize(data), indent=2))
    else:
        print(render_status_text(data), end="")
    if args.write_status:
        Path(args.status).write_text(render_status_markdown(data), encoding="utf-8")
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    store = _store_from_args(args)
    data = store.load()
    plan = suggest_plan(data, slots=args.slots)
    if args.json:
        print(json.dumps(plan, indent=2))
        return 0
    print(f"Suggested focus for {data['exam_code']}:")
    for i, item in enumerate(plan, start=1):
        print(
            f"{i}. {item['domain_name']} [{item['domain_id']}] — "
            f"{item['action']} (readiness {item['readiness']}%)"
        )
        print(f"   Why: {item['why']}")
        print(f"   Topics: {', '.join(item['focus_topics'])}")
    return 0


def cmd_set_goal(args: argparse.Namespace) -> int:
    store = _store_from_args(args)
    data = store.load()
    if args.exam_date is not None:
        data["target_exam_date"] = args.exam_date or None
    if args.weekly_minutes is not None:
        if args.weekly_minutes < 0:
            raise SystemExit("weekly minutes must be >= 0")
        data["goal_weekly_minutes"] = args.weekly_minutes
    store.save(data)
    Path(args.status).write_text(render_status_markdown(data), encoding="utf-8")
    print("Updated goals:")
    print(f"  target_exam_date={data.get('target_exam_date')}")
    print(f"  goal_weekly_minutes={data.get('goal_weekly_minutes')}")
    return 0


def cmd_exams(_: argparse.Namespace) -> int:
    for code, exam in sorted(EXAMS.items()):
        print(f"{code}: {exam.name}")
        for domain in exam.domains:
            print(f"  - {domain.id}: {domain.name} ({int(domain.weight * 100)}%)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aws-cert",
        description="Track AWS certification study activity and readiness.",
    )
    parser.add_argument(
        "--progress",
        default=str(DEFAULT_PROGRESS_PATH),
        help=f"Path to progress JSON (default: {DEFAULT_PROGRESS_PATH})",
    )
    parser.add_argument(
        "--status",
        default=str(DEFAULT_STATUS_PATH),
        help=f"Path to STATUS.md dashboard (default: {DEFAULT_STATUS_PATH})",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    init_p = sub.add_parser("init", help="Create a new progress tracker")
    init_p.add_argument(
        "--exam",
        default=DEFAULT_EXAM,
        help=f"Exam code (default: {DEFAULT_EXAM}). Supported: {', '.join(sorted(EXAMS))}",
    )
    init_p.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing progress file",
    )
    init_p.set_defaults(func=cmd_init)

    log_p = sub.add_parser("log", help="Log a study activity")
    log_p.add_argument(
        "type",
        choices=("study", "practice", "lab", "video", "review"),
        help="Activity type",
    )
    log_p.add_argument("--minutes", type=int, default=0, help="Time spent in minutes")
    log_p.add_argument("--domain", help="Domain id or name fragment (e.g. secure)")
    log_p.add_argument("--notes", default="", help="Short notes about the session")
    log_p.add_argument("--score", type=int, help="Correct answers (practice)")
    log_p.add_argument("--total", type=int, help="Total questions (practice)")
    log_p.add_argument(
        "--topics",
        default="",
        help="Comma-separated topics covered",
    )
    log_p.add_argument(
        "--when",
        help="ISO timestamp override (default: now UTC)",
    )
    log_p.set_defaults(func=cmd_log)

    status_p = sub.add_parser("status", help="Show readiness summary")
    status_p.add_argument("--json", action="store_true", help="Emit JSON")
    status_p.add_argument(
        "--write-status",
        action="store_true",
        help="Refresh STATUS.md",
    )
    status_p.set_defaults(func=cmd_status)

    plan_p = sub.add_parser("plan", help="Suggest next study focus")
    plan_p.add_argument("--slots", type=int, default=3, help="Number of suggestions")
    plan_p.add_argument("--json", action="store_true", help="Emit JSON")
    plan_p.set_defaults(func=cmd_plan)

    goal_p = sub.add_parser("set-goal", help="Set exam date or weekly minute goal")
    goal_p.add_argument("--exam-date", help="Target exam date YYYY-MM-DD (empty to clear)")
    goal_p.add_argument("--weekly-minutes", type=int, help="Weekly study minute goal")
    goal_p.set_defaults(func=cmd_set_goal)

    exams_p = sub.add_parser("exams", help="List supported exams and domains")
    exams_p.set_defaults(func=cmd_exams)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
