COMMON = {"event_ts": "timestamp", "ingested_at": "timestamp"}
CONTRACTS = {
 "customers": {"customer_id":"string", "customer_name":"string", "email":"string", "country":"string", **COMMON},
 "accounts": {"account_id":"string", "customer_id":"string", "account_status":"string", "opened_date":"date", **COMMON},
 "products": {"product_id":"string", "product_name":"string", "category":"string", "risk_policy":"string", **COMMON},
 "reference_data": {"currency":"string", "rate_date":"date", "usd_rate":"decimal(18,8)", **COMMON},
 "transactions": {"transaction_id":"string", "account_id":"string", "product_id":"string", "currency":"string", "amount":"decimal(18,2)", "transaction_ts":"timestamp", "status":"string", "tags_json":"string", **COMMON},
}
KEYS = {"customers":["customer_id"], "accounts":["account_id"], "products":["product_id"], "reference_data":["currency","rate_date"], "transactions":["transaction_id"]}
