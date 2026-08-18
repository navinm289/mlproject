"""Top-level package for mlproject."""

from __future__ import annotations

from typing import Any

__all__ = [
    "compare_ingest_costs",
    "format_comparison",
    "read_sas_with_metadata",
]


def __getattr__(name: str) -> Any:
    if name in {"compare_ingest_costs", "format_comparison"}:
        from .ingest_cost import compare_ingest_costs, format_comparison

        return compare_ingest_costs if name == "compare_ingest_costs" else format_comparison
    if name == "read_sas_with_metadata":
        from .pyspark_sas import read_sas_with_metadata

        return read_sas_with_metadata
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
