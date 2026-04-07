"""Unit tests for the data stack processor."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from stack_processor import (
    ConfigReader,
    DataStackProcessor,
    FileEntry,
    JoinConfig,
)


class TestJoinConfig:
    """Tests for JoinConfig dataclass."""
    
    def test_from_dict_valid(self):
        """Test creating JoinConfig from valid dict."""
        config = {
            "type": "inner",
            "keys": ["id", "date"]
        }
        join = JoinConfig.from_dict(config)
        assert join.type == "inner"
        assert join.keys == ["id", "date"]
    
    def test_from_dict_none(self):
        """Test creating JoinConfig from None."""
        assert JoinConfig.from_dict(None) is None
        assert JoinConfig.from_dict({}) is None
    
    def test_from_dict_defaults(self):
        """Test JoinConfig defaults to 'inner' type."""
        config = {"keys": ["id"]}
        join = JoinConfig.from_dict(config)
        assert join.type == "inner"


class TestFileEntry:
    """Tests for FileEntry dataclass."""
    
    def test_from_dict_base_file(self):
        """Test creating base file entry."""
        entry_dict = {
            "file": "/path/to/file.sas",
            "metadata": "/path/to/file.metadata",
            "basefile": True
        }
        entry = FileEntry.from_dict(entry_dict)
        assert entry.file_pattern == "/path/to/file.sas"
        assert entry.metadata_path == "/path/to/file.metadata"
        assert entry.is_base is True
        assert entry.is_union is False
    
    def test_from_dict_with_join(self):
        """Test creating entry with join."""
        entry_dict = {
            "file": "/path/to/file.sas",
            "join": {"type": "left", "keys": ["id"]}
        }
        entry = FileEntry.from_dict(entry_dict)
        assert entry.join_config is not None
        assert entry.join_config.type == "left"
        assert entry.join_config.keys == ["id"]
    
    def test_from_dict_with_union(self):
        """Test creating entry with union."""
        entry_dict = {
            "file": "/path/to/file*.sas",
            "union": True
        }
        entry = FileEntry.from_dict(entry_dict)
        assert entry.is_union is True
    
    def test_expand_files_literal(self):
        """Test expanding literal file paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            test_file = Path(tmpdir) / "test.sas"
            test_file.write_text("test")
            
            entry = FileEntry(file_pattern=str(test_file))
            expanded = entry.expand_files()
            assert expanded == [str(test_file)]
    
    def test_expand_files_glob(self):
        """Test expanding glob patterns."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            files = []
            for i in range(3):
                test_file = Path(tmpdir) / f"kb{i}.sas"
                test_file.write_text("test")
                files.append(str(test_file))
            
            pattern = str(Path(tmpdir) / "kb*.sas")
            entry = FileEntry(file_pattern=pattern)
            expanded = sorted(entry.expand_files())
            assert len(expanded) == 3
            assert expanded == sorted(files)


class TestConfigReader:
    """Tests for ConfigReader."""
    
    def test_load_config_json(self):
        """Test loading JSON configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {
                "uat": [
                    {"file": "file1.sas", "basefile": True},
                    {"file": "file2.sas", "join": {"type": "inner", "keys": ["id"]}}
                ]
            }
            config_file = Path(tmpdir) / "config.json"
            with open(config_file, "w") as f:
                json.dump(config, f)
            
            reader = ConfigReader(config_file)
            assert reader.env == "uat"
            assert reader.config == config
    
    def test_config_not_found(self):
        """Test error when config file not found."""
        with pytest.raises(FileNotFoundError):
            ConfigReader("/nonexistent/path/config.json")
    
    def test_get_entries(self):
        """Test getting entries for environment."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {
                "uat": [
                    {"file": "file1.sas", "basefile": True},
                    {"file": "file2.sas"}
                ]
            }
            config_file = Path(tmpdir) / "config.json"
            with open(config_file, "w") as f:
                json.dump(config, f)
            
            reader = ConfigReader(config_file, env="uat")
            entries = reader.get_entries()
            assert len(entries) == 2
            assert entries[0].is_base is True
            assert entries[1].is_base is False
    
    def test_env_not_found(self):
        """Test error when environment not in config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {"uat": []}
            config_file = Path(tmpdir) / "config.json"
            with open(config_file, "w") as f:
                json.dump(config, f)
            
            reader = ConfigReader(config_file, env="prod")
            with pytest.raises(ValueError, match="not found"):
                reader.get_entries()
    
    def test_validate_no_base_file(self):
        """Test validation fails with no base file."""
        entries = [
            FileEntry(file_pattern="file1.sas"),
            FileEntry(file_pattern="file2.sas")
        ]
        reader = ConfigReader.__new__(ConfigReader)
        
        with pytest.raises(ValueError, match="must have exactly one base file"):
            reader.validate_entries(entries)
    
    def test_validate_multiple_base_files(self):
        """Test validation fails with multiple base files."""
        entries = [
            FileEntry(file_pattern="file1.sas", is_base=True),
            FileEntry(file_pattern="file2.sas", is_base=True)
        ]
        reader = ConfigReader.__new__(ConfigReader)
        
        with pytest.raises(ValueError, match="must have exactly one base file"):
            reader.validate_entries(entries)
    
    def test_validate_success(self):
        """Test validation passes with exactly one base file."""
        entries = [
            FileEntry(file_pattern="file1.sas", is_base=True),
            FileEntry(file_pattern="file2.sas")
        ]
        reader = ConfigReader.__new__(ConfigReader)
        
        assert reader.validate_entries(entries) is True


class TestDataStackProcessor:
    """Tests for DataStackProcessor."""
    
    def test_initialization(self):
        """Test processor initialization."""
        mock_spark = MagicMock()
        mock_config = MagicMock()
        
        processor = DataStackProcessor(mock_spark, mock_config)
        assert processor.spark == mock_spark
        assert processor.config_reader == mock_config
    
    @patch('stack_processor.read_sas_with_metadata')
    def test_process_single_file_base(self, mock_read):
        """Test processing with single base file."""
        mock_spark = MagicMock()
        mock_config = MagicMock()
        mock_df = MagicMock()
        mock_read.return_value = mock_df
        
        entries = [FileEntry(file_pattern="base.sas", is_base=True)]
        mock_config.get_entries.return_value = entries
        
        processor = DataStackProcessor(mock_spark, mock_config)
        result = processor._process_entry(entries[0], is_base=True)
        
        mock_read.assert_called_once()
        assert result == mock_df
    
    @patch('stack_processor.read_sas_with_metadata')
    def test_apply_join(self, mock_read):
        """Test applying join operation."""
        mock_spark = MagicMock()
        mock_config = MagicMock()
        
        # Mock DataFrames
        left_df = MagicMock()
        right_df = MagicMock()
        joined_df = MagicMock()
        left_df.join.return_value = joined_df
        
        mock_read.return_value = right_df
        
        processor = DataStackProcessor(mock_spark, mock_config)
        
        # Create entry with join
        entry = FileEntry(
            file_pattern="right.sas",
            join_config=JoinConfig(type="inner", keys=["id"])
        )
        
        result = processor._apply_join(left_df, entry)
        
        left_df.join.assert_called_once()
        assert result == joined_df


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
