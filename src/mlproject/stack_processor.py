"""Configuration reader and data stack processor for SAS files with joins and unions."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from glob import glob
from pathlib import Path
from typing import Any, Optional

from pyspark.sql import DataFrame, SparkSession

from .pyspark_sas import read_sas_with_metadata

logger = logging.getLogger(__name__)


@dataclass
class JoinConfig:
    """Configuration for joining datasets."""
    type: str  # 'inner', 'left', 'right', 'outer', 'cross'
    keys: list[str]
    
    @classmethod
    def from_dict(cls, config: dict[str, Any]) -> Optional[JoinConfig]:
        """Create JoinConfig from dictionary."""
        if not config:
            return None
        return cls(
            type=config.get("type", "inner").lower(),
            keys=config.get("keys", [])
        )


@dataclass
class FileEntry:
    """Represents a single file entry in the stack."""
    file_pattern: str
    metadata_path: Optional[str]
    is_base: bool = False
    is_union: bool = False
    join_config: Optional[JoinConfig] = None
    union_name: Optional[str] = None
    
    @classmethod
    def from_dict(cls, entry: dict[str, Any]) -> FileEntry:
        """Create FileEntry from dictionary."""
        join_config = None
        if "join" in entry:
            join_config = JoinConfig.from_dict(entry["join"])
        
        union_name = None
        if "join" in entry and isinstance(entry["join"], dict):
            union_name = entry["join"].get("choose name")
        
        return cls(
            file_pattern=entry.get("file", ""),
            metadata_path=entry.get("metadata"),
            is_base=entry.get("basefile", False),
            is_union=entry.get("union", False),
            join_config=join_config,
            union_name=union_name
        )
    
    def expand_files(self) -> list[str]:
        """Expand glob patterns and return list of actual files."""
        expanded = glob(self.file_pattern)
        if expanded:
            return sorted(expanded)
        return [self.file_pattern]  # Return pattern as-is if no matches


@dataclass
class DataStack:
    """Represents the ordered stack of data transformations."""
    base_df: Optional[DataFrame] = None
    stack: list[tuple[DataFrame, FileEntry]] = None
    
    def __post_init__(self):
        if self.stack is None:
            self.stack = []


class ConfigReader:
    """Reads configuration from JSON/YAML files based on environment."""
    
    def __init__(self, config_path: str | Path, env: Optional[str] = None):
        """
        Initialize ConfigReader.
        
        Args:
            config_path: Path to configuration file (JSON/YAML)
            env: Environment name (uat, prod, dev, etc.)
        """
        self.config_path = Path(config_path)
        self.env = env or os.environ.get("MLPROJECT_ENV", "uat")
        self.config = self._load_config()
    
    def _load_config(self) -> dict[str, Any]:
        """Load configuration from file."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        
        if self.config_path.suffix.lower() == ".json":
            with open(self.config_path, "r") as f:
                return json.load(f)
        else:
            raise ValueError(f"Unsupported config format: {self.config_path.suffix}")
    
    def get_entries(self) -> list[FileEntry]:
        """
        Get file entries for the current environment.
        
        Returns:
            List of FileEntry objects in order
        """
        if self.env not in self.config:
            raise ValueError(
                f"Environment '{self.env}' not found in config. "
                f"Available: {list(self.config.keys())}"
            )
        
        entries_data = self.config[self.env]
        if not isinstance(entries_data, list):
            raise ValueError(
                f"Environment config must be a list, got {type(entries_data)}"
            )
        
        entries = [FileEntry.from_dict(entry) for entry in entries_data]
        return entries
    
    def validate_entries(self, entries: list[FileEntry]) -> bool:
        """Validate that configuration has exactly one base file."""
        base_count = sum(1 for e in entries if e.is_base)
        if base_count == 0:
            raise ValueError("Configuration must have exactly one base file (basefile: true)")
        if base_count > 1:
            raise ValueError("Configuration must have exactly one base file")
        return True


class DataStackProcessor:
    """Process data stack with joins and unions."""
    
    def __init__(self, spark: SparkSession, config_reader: ConfigReader):
        """
        Initialize DataStackProcessor.
        
        Args:
            spark: SparkSession instance
            config_reader: ConfigReader instance
        """
        self.spark = spark
        self.config_reader = config_reader
    
    def process(self) -> DataFrame:
        """
        Process the data stack according to configuration.
        
        Returns:
            Final DataFrame with all transformations applied
        """
        entries = self.config_reader.get_entries()
        self.config_reader.validate_entries(entries)
        
        logger.info(f"Processing stack for environment: {self.config_reader.env}")
        logger.info(f"Total entries: {len(entries)}")
        
        # Step 1: Find and process base file(s)
        base_entry = next(e for e in entries if e.is_base)
        base_df = self._process_entry(base_entry, is_base=True)
        
        logger.info("Base file(s) loaded successfully")
        
        # Step 2: Process remaining entries
        remaining_entries = [e for e in entries if not e.is_base]
        current_df = base_df
        
        for i, entry in enumerate(remaining_entries, start=1):
            logger.info(
                f"Processing entry {i}/{len(remaining_entries)}: "
                f"pattern={entry.file_pattern}, union={entry.is_union}"
            )
            
            current_df = self._apply_entry(current_df, entry)
        
        logger.info("Data stack processing completed")
        return current_df
    
    def _process_entry(self, entry: FileEntry, is_base: bool = False) -> DataFrame:
        """
        Process a single entry, handling unions internally.
        
        Args:
            entry: FileEntry to process
            is_base: Whether this is the base file
        
        Returns:
            DataFrame for this entry (may be union of multiple files)
        """
        files = entry.expand_files()
        
        logger.info(
            f"{'[BASE] ' if is_base else ''}Loading {len(files)} file(s): {files}"
        )
        
        if len(files) == 1:
            # Single file - just read it
            return read_sas_with_metadata(
                self.spark,
                files[0],
                entry.metadata_path
            )
        else:
            # Multiple files - union them
            logger.info(f"Union of {len(files)} files with pattern: {entry.file_pattern}")
            
            dataframes = []
            for file_path in files:
                df = read_sas_with_metadata(
                    self.spark,
                    file_path,
                    entry.metadata_path
                )
                dataframes.append(df)
            
            # Union all dataframes
            combined_df = dataframes[0]
            for df in dataframes[1:]:
                combined_df = combined_df.unionByName(df)
            
            logger.info(f"Union completed: {combined_df.count()} rows")
            return combined_df
    
    def _apply_entry(self, current_df: DataFrame, entry: FileEntry) -> DataFrame:
        """
        Apply an entry (join or union) to the current DataFrame.
        
        Args:
            current_df: Current DataFrame
            entry: Entry to apply
        
        Returns:
            Updated DataFrame
        """
        if entry.is_union:
            return self._apply_union(current_df, entry)
        elif entry.join_config:
            return self._apply_join(current_df, entry)
        else:
            # Just load and return
            return self._process_entry(entry, is_base=False)
    
    def _apply_union(self, current_df: DataFrame, entry: FileEntry) -> DataFrame:
        """
        Apply union operation.
        
        Args:
            current_df: Current DataFrame
            entry: Entry with union=true
        
        Returns:
            Union of current_df and entry's data
        """
        entry_df = self._process_entry(entry, is_base=False)
        
        # If union_name is specified, union all entry files first
        if entry.union_name == "union":
            logger.info(f"Union operation: combining with {entry.file_pattern}")
            combined = current_df.unionByName(entry_df)
            logger.info(f"Union result: {combined.count()} rows")
            return combined
        else:
            logger.info(f"Union operation: combining with {entry.file_pattern}")
            combined = current_df.unionByName(entry_df)
            logger.info(f"Union result: {combined.count()} rows")
            return combined
    
    def _apply_join(self, current_df: DataFrame, entry: FileEntry) -> DataFrame:
        """
        Apply join operation.
        
        Args:
            current_df: Current DataFrame (left side)
            entry: Entry to join (right side)
        
        Returns:
            Joined DataFrame
        """
        if not entry.join_config:
            raise ValueError(f"Entry {entry.file_pattern} has no join configuration")
        
        entry_df = self._process_entry(entry, is_base=False)
        join_type = entry.join_config.type.lower()
        join_keys = entry.join_config.keys
        
        if not join_keys:
            raise ValueError(
                f"Join configuration must specify keys for {entry.file_pattern}"
            )
        
        logger.info(
            f"Join operation: type={join_type}, keys={join_keys}, "
            f"right_files={entry.expand_files()}"
        )
        
        # Build join condition from keys
        join_condition = None
        for key in join_keys:
            key_condition = current_df[key] == entry_df[key]
            if join_condition is None:
                join_condition = key_condition
            else:
                join_condition = join_condition & key_condition
        
        # Apply join
        result_df = current_df.join(
            entry_df,
            on=join_condition,
            how=join_type
        )
        
        logger.info(f"Join completed: {result_df.count()} rows")
        return result_df


def create_data_stack(
    spark: SparkSession,
    config_path: str | Path,
    env: Optional[str] = None
) -> DataFrame:
    """
    Create a data stack from configuration.
    
    Args:
        spark: SparkSession instance
        config_path: Path to configuration file
        env: Environment name (optional, defaults to MLPROJECT_ENV or 'uat')
    
    Returns:
        Final processed DataFrame
    """
    config_reader = ConfigReader(config_path, env)
    processor = DataStackProcessor(spark, config_reader)
    return processor.process()
