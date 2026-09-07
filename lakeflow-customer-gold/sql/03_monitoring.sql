-- REPLACE the literal with the actual pipeline UUID. Run with event-log privileges.
SELECT timestamp, origin.update_id AS platform_update_id, event_type, level, message,
       details:flow_progress:data_quality AS expectation_metrics
FROM event_log('REPLACE_PIPELINE_UUID')
WHERE event_type IN ('flow_progress', 'update_progress')
ORDER BY timestamp DESC;

-- Run only AFTER successful update, with the SAME named catalog/gold_schema/run_id.
-- Separate audit table is operationally owned; never include this SQL in the pipeline DAG.
CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.' || :gold_schema || '.data_quality_history')
USING DELTA AS SELECT * FROM IDENTIFIER(:catalog || '.' || :gold_schema || '.data_quality_results') WHERE false;
MERGE INTO IDENTIFIER(:catalog || '.' || :gold_schema || '.data_quality_history') t
USING (SELECT * FROM IDENTIFIER(:catalog || '.' || :gold_schema || '.data_quality_results')
       WHERE pipeline_run_id = :run_id) s
ON t.pipeline_run_id = s.pipeline_run_id AND t.table_name = s.table_name
   AND t.rule_name = s.rule_name AND t.severity = s.severity
WHEN NOT MATCHED THEN INSERT *;
-- Persist platform failure events separately; current results may be stale after failure.
