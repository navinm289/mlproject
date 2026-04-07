"""Example usage of the data stack processor."""

from pyspark.sql import SparkSession
from stack_processor import create_data_stack


def main():
    """Example: Create and process a data stack."""
    
    # Create Spark session
    spark = SparkSession.builder \
        .appName("DataStackProcessor") \
        .getOrCreate()
    
    # Example 1: Process stack for UAT environment
    print("=" * 80)
    print("Processing UAT environment")
    print("=" * 80)
    
    df_uat = create_data_stack(
        spark=spark,
        config_path="src/mlproject/conf.json",
        env="uat"
    )
    
    print("\nFinal DataFrame Schema:")
    df_uat.printSchema()
    
    print("\nFinal DataFrame (first 10 rows):")
    df_uat.show(10)
    
    print(f"\nTotal rows: {df_uat.count()}")
    
    # Example 2: Process stack for PROD environment (if exists)
    # df_prod = create_data_stack(spark, "config/conf.json", env="prod")
    
    spark.stop()


if __name__ == "__main__":
    main()
