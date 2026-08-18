import unittest

from mlproject.ingest_cost import (
    MIN_WAREHOUSE_SECONDS,
    compare_ingest_costs,
    estimate_copy_into,
    estimate_copy_runtime_seconds,
    estimate_spark_connector,
    warehouse_credits,
)


class WarehouseBillingTests(unittest.TestCase):
    def test_sixty_second_minimum(self):
        credits = warehouse_credits("XSMALL", 10)
        self.assertAlmostEqual(credits, 1.0 * (MIN_WAREHOUSE_SECONDS / 3600), places=6)

    def test_size_doubles_credits(self):
        xs = warehouse_credits("XS", 120)
        small = warehouse_credits("SMALL", 120)
        self.assertAlmostEqual(small, xs * 2, places=6)


class CopyIntoTests(unittest.TestCase):
    def test_more_files_use_warehouse_parallelism(self):
        few = estimate_copy_runtime_seconds(10, "SMALL", file_count=2)
        many = estimate_copy_runtime_seconds(10, "SMALL", file_count=32)
        self.assertGreater(few, many)

    def test_copy_has_no_spark_cost(self):
        cost = estimate_copy_into(50, "SMALL")
        self.assertEqual(cost.spark_usd, 0.0)
        self.assertGreater(cost.total_usd, 0.0)


class SparkConnectorTests(unittest.TestCase):
    def test_spark_costs_more_when_cluster_is_billed(self):
        result = compare_ingest_costs(100, "SMALL", spark_dpu=10)
        self.assertEqual(result.cheaper_method, "copy_into_s3")
        self.assertGreater(result.spark_premium_usd, 0)
        self.assertGreater(result.spark_connector.spark_usd, 0)

    def test_shared_spark_cluster_still_usually_higher_warehouse(self):
        copy_into = estimate_copy_into(100, "SMALL")
        spark = estimate_spark_connector(
            100,
            "SMALL",
            include_spark_cluster=False,
        )
        self.assertGreater(spark.snowflake_usd, copy_into.snowflake_usd)
        self.assertEqual(spark.spark_usd, 0.0)

    def test_measured_spark_minutes_override_default(self):
        cheap = estimate_spark_connector(10, "SMALL", spark_minutes=1, spark_dpu=2)
        expensive = estimate_spark_connector(
            10, "SMALL", spark_minutes=60, spark_dpu=2
        )
        self.assertGreater(expensive.spark_usd, cheap.spark_usd)

    def test_package_lazy_export(self):
        import mlproject

        self.assertTrue(callable(mlproject.compare_ingest_costs))


if __name__ == "__main__":
    unittest.main()
