-- Execute after the sample pipeline update, with named catalog/gold_schema parameters.
SELECT assert_true(count(*) = 1, 'expected one Gold key'),
       assert_true(sum(transaction_count) = 3, 'count mismatch'),
       assert_true(sum(total_transaction_amount) = 90, 'amount mismatch'),
       assert_true(sum(total_amount_usd) = 90, 'USD amount mismatch'),
       assert_true(min(data_quality_status) = 'PASS', 'unexpected warning')
FROM IDENTIFIER(:catalog || '.' || :gold_schema || '.customer_transaction_summary');
SELECT assert_true(count(*) = 2, 'one duplicate plus one orphan expected')
FROM IDENTIFIER(:catalog || '.' || :gold_schema || '.customer_transaction_quarantine');
SELECT assert_true(count_if(severity = 'Failure' AND fail_count > 0) = 0, 'critical quality failure')
FROM IDENTIFIER(:catalog || '.' || :gold_schema || '.data_quality_results');
