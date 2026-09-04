import pytest

from mlproject.autoloader_contract import (
    IngestionConfig,
    expected_control_name,
    safe_data_filename,
)


@pytest.mark.parametrize(
    "name,expected",
    [
        ("orders_20260904.csv", True),
        ("orders.csv", True),
        ("orders.control.json", False),
        ("../orders.csv", False),
        ("folder/orders.csv", False),
        ("", False),
    ],
)
def test_safe_data_filename(name, expected):
    assert safe_data_filename(name) is expected


def test_expected_control_name():
    assert expected_control_name("orders_20260904.csv") == "orders_20260904.control.json"


def test_rejects_unsafe_control_filename():
    with pytest.raises(ValueError):
        expected_control_name("../orders.csv")


def test_config_requires_three_part_uc_table():
    config = IngestionConfig(
        landing_path="s3://example/landing",
        checkpoint_path="/Volumes/main/ops/checkpoints/orders",
        schema_path="/Volumes/main/ops/schemas/orders",
        bronze_table="bronze.orders",
    )
    with pytest.raises(ValueError):
        config.validate()


def test_checkpoint_cannot_equal_landing_path():
    config = IngestionConfig(
        landing_path="s3://example/landing",
        checkpoint_path="s3://example/landing/",
        schema_path="/Volumes/main/ops/schemas/orders",
        bronze_table="main.bronze.orders",
    )
    with pytest.raises(ValueError):
        config.validate()
