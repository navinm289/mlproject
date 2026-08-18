"""CLI entry point: python -m mlproject ..."""

from __future__ import annotations

import argparse

from .ingest_cost import Pricing, compare_ingest_costs, format_comparison


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare Snowflake COPY INTO from S3 vs Spark connector load cost."
        )
    )
    sub = parser.add_subparsers(dest="command")

    compare = sub.add_parser(
        "compare-ingest-cost",
        help="Estimate COPY INTO vs Spark connector cost for one load.",
    )
    compare.add_argument("--data-gb", type=float, required=True, help="Compressed GB")
    compare.add_argument("--warehouse", default="SMALL")
    compare.add_argument(
        "--file-count",
        type=int,
        default=None,
        help="Number of staged files (default: ~150 MB each)",
    )
    compare.add_argument("--spark-dpu", type=float, default=10.0)
    compare.add_argument(
        "--spark-minutes",
        type=float,
        default=None,
        help="Measured Spark job minutes. Default: derived from warehouse time.",
    )
    compare.add_argument(
        "--warehouse-overhead",
        type=float,
        default=2.5,
        help="Spark write warehouse time vs native COPY (default 2.5x).",
    )
    compare.add_argument(
        "--omit-spark-cluster",
        action="store_true",
        help="Ignore Spark cluster $ if Spark already runs for transforms.",
    )
    compare.add_argument("--credit-usd", type=float, default=2.00)
    compare.add_argument("--glue-dpu-hour-usd", type=float, default=0.44)
    compare.add_argument(
        "--loads-per-month",
        type=int,
        default=1,
        help="Multiply one-load totals by this many runs.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command != "compare-ingest-cost":
        parser.print_help()
        return 1

    result = compare_ingest_costs(
        args.data_gb,
        args.warehouse,
        file_count=args.file_count,
        spark_dpu=args.spark_dpu,
        spark_minutes=args.spark_minutes,
        warehouse_overhead=args.warehouse_overhead,
        include_spark_cluster=not args.omit_spark_cluster,
        pricing=Pricing(
            credit_usd=args.credit_usd,
            glue_dpu_hour_usd=args.glue_dpu_hour_usd,
        ),
    )
    print(format_comparison(result))
    if args.loads_per_month > 1:
        copy_month = result.copy_into.total_usd * args.loads_per_month
        spark_month = result.spark_connector.total_usd * args.loads_per_month
        print()
        print(f"Monthly ({args.loads_per_month} loads)")
        print(f"  COPY INTO         : ${copy_month:.2f}")
        print(f"  Spark connector   : ${spark_month:.2f}")
        print(f"  Difference        : ${spark_month - copy_month:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
