# Validation record

Validated locally on 2026-09-06 using Python 3.11, PySpark 3.5.6 and Java 17.

- Eight unittest tests passed, including actual local Spark execution (84.248 seconds).
- Policy tests cover nested Boolean evaluation, malformed branches, recursion limits and NULL input.
- Spark tests cover missing contracts, invalid amount casts, latest-version deduplication, five-source joins, orphan rejection, financial aggregates, row-level quality metrics and assembled pipeline query plans.
- The assembled DAG test confirms source count=4, rejected count=1, rejection percentage=20%, per-key reconciliation mismatches=0, two quarantine rows, Gold amount=90, and no failing critical controls at the sample threshold. It also confirms that the production 5% threshold rejects the fixture.
- All Python files parsed and bundle YAML parsed successfully.

Local DAG tests stub Lakeflow decorators. They do not prove Databricks expectation enforcement, Delta refresh semantics, incremental eligibility, UC grants or bundle resource validation. Databricks CLI is not installed in the authoring environment; no workspace deployment, bundle CLI validation or remote integration test was performed. Execute the SQL assertions and transition scenarios in operations.md before promotion.
