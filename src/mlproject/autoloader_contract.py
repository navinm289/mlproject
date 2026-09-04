"""Dependency-free configuration and naming rules for Auto Loader ingestion."""

from __future__ import annotations

import posixpath
from dataclasses import dataclass


@dataclass(frozen=True)
class IngestionConfig:
    landing_path: str
    checkpoint_path: str
    schema_path: str
    bronze_table: str
    csv_glob: str = "*.csv"
    control_glob: str = "*.control.json"
    header: bool = True
    delimiter: str = ","
    managed_file_events: bool = True
    creation_time_tolerance_seconds: int = 300

    def validate(self) -> None:
        if not self.landing_path.startswith(("s3://", "/Volumes/")):
            raise ValueError("landing_path must be an s3:// path or UC Volume path")
        if self.checkpoint_path.rstrip("/") == self.landing_path.rstrip("/"):
            raise ValueError("checkpoint_path must be outside the landing directory")
        if not self.bronze_table or self.bronze_table.count(".") != 2:
            raise ValueError("bronze_table must be catalog.schema.table")
        if self.creation_time_tolerance_seconds < 0:
            raise ValueError("creation_time_tolerance_seconds cannot be negative")


def safe_data_filename(name: str) -> bool:
    """Return True only for a plain CSV basename supplied by a control file."""
    return bool(name and name.endswith(".csv") and posixpath.basename(name) == name)


def expected_control_name(data_file: str) -> str:
    if not safe_data_filename(data_file):
        raise ValueError(f"Unsafe or unsupported data filename: {data_file!r}")
    return f"{data_file[:-4]}.control.json"
