import unittest
from decimal import Decimal
from pyspark.sql import SparkSession, functions as F
from gold_pipeline.contracts import CONTRACTS
from gold_pipeline.transforms import normalize, rank_versions, reasons, source_rules, enrich, JOIN_RULES, summarize
from gold_pipeline.quality import check_gold, gold_rules, rule_results
from sample_data import DATA, AS_OF
class TransformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spark=SparkSession.builder.master("local[2]").appName("gold-tests").config("spark.sql.shuffle.partitions","2").config("spark.sql.session.timeZone","UTC").getOrCreate()
    @classmethod
    def tearDownClass(cls): cls.spark.stop()
    def frames(self):
        checked={}
        for name,rows in DATA.items():
            df=self.spark.createDataFrame(rows, ','.join(f"{c} string" for c in CONTRACTS[name]))
            checked[name]=rank_versions(reasons(normalize(df,name),source_rules(name,AS_OF)),name)
        return checked
    def test_end_to_end(self):
        checked=self.frames()
        self.assertEqual(checked["transactions"].filter("version_rank > 1").count(),1)
        clean={k:v.filter("version_rank = 1 AND size(rejection_reasons)=0") for k,v in checked.items()}
        joined=reasons(enrich(*[clean[s] for s in ["transactions","accounts","customers","products","reference_data"]]),JOIN_RULES).cache()
        rejected=joined.filter("size(rejection_reasons)>0").collect()
        self.assertEqual(len(rejected),1); self.assertEqual(rejected[0].transaction_id,"T3")
        self.assertIn("account_fk",rejected[0].rejection_reasons)
        q,w=gold_rules(AS_OF,30)
        result=check_gold(summarize(joined.filter("size(rejection_reasons)=0")),q,w).cache()
        row=result.first()
        self.assertEqual(row.transaction_count,3)
        self.assertEqual(row.total_transaction_amount,Decimal("90"))
        self.assertEqual(row.average_transaction_amount,Decimal("30"))
        self.assertEqual(row.risk_transaction_count,1)
        self.assertEqual(row.data_quality_status,"PASS")
        metrics=rule_results(result,q,"gold","Quarantine","sample",AS_OF).collect()
        self.assertTrue(all(r.fail_count==0 and r.pass_count==1 for r in metrics))
        joined.unpersist(); result.unpersist()
    def test_contract_missing(self):
        with self.assertRaises(ValueError): normalize(self.spark.createDataFrame([("x",)],"customer_id string"),"customers")
    def test_bad_cast(self):
        row=list(DATA["transactions"][0]); row[4]="not_money"
        df=self.spark.createDataFrame([tuple(row)],','.join(f"{c} string" for c in CONTRACTS['transactions']))
        checked=reasons(normalize(df,"transactions"),source_rules("transactions",AS_OF)).first()
        self.assertIn("amount",checked.rejection_reasons)

    def test_pipeline_plans(self):
        """Execute the assembled DAG locally; decorators are stubs, not Lakeflow emulation.
        Validates query wiring/metrics. Real expectations and refreshes require Databricks.
        """
        import importlib.util
        import sys
        from pathlib import Path
        from types import SimpleNamespace
        from unittest.mock import patch
        registry, tables = {}, {}
        def materialized_view(**kwargs):
            def register(fn):
                registry[kwargs['name']] = fn
                return fn
            return register
        def expectation(rules):
            return lambda fn: fn
        dp = SimpleNamespace(materialized_view=materialized_view,
                             expect_all=expectation, expect_all_or_fail=expectation)
        settings = {'gold.source':'fixture.source', 'gold.run_id':'sample-001',
                    'gold.as_of':AS_OF, 'gold.max_quarantine_pct':'30',
                    'gold.baseline_posted_rows':'4'}
        for name,rows in DATA.items():
            tables['fixture.source.'+name] = self.spark.createDataFrame(
                rows, ','.join(f'{c} string' for c in CONTRACTS[name]))
        fake_spark = SimpleNamespace(conf=SimpleNamespace(get=lambda k,default=None: settings.get(k,default)),
                                     read=SimpleNamespace(table=lambda name: tables[name]))
        path = Path(__file__).resolve().parents[1]/'src'/'pipeline.py'
        spec = importlib.util.spec_from_file_location('test_pipeline_definition',path)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'pyspark.pipelines':dp}), patch.object(SparkSession,'active',return_value=fake_spark):
            spec.loader.exec_module(module)
        cached=[]
        try:
            for name,fn in registry.items():
                tables[name] = fn()
                if name != 'data_quality_results':
                    tables[name] = tables[name].cache()
                    cached.append(tables[name])
                    tables[name].count()
            controls=tables['quality_controls'].first()
            self.assertEqual(controls.source_count,4)
            self.assertEqual(controls.rejected_count,1)
            self.assertEqual(controls.quarantine_pct,20.0)
            self.assertEqual(controls.key_mismatches,0)
            self.assertEqual(tables['customer_transaction_quarantine'].count(),2)
            self.assertEqual(tables['customer_transaction_summary'].first().total_transaction_amount,Decimal('90'))
            results=tables['data_quality_results']
            self.assertEqual(results.filter("severity = 'Failure' AND fail_count > 0").count(),0)
            # Evaluate the gate predicates directly; the actual fail decorator needs Lakeflow.
            self.assertEqual(tables['quality_controls'].filter(' AND '.join(module.CONTROL_RULES.values())).count(),1)
            self.assertEqual(tables['quality_controls'].filter('quarantine_pct <= 5').count(),0)
        finally:
            for frame in cached: frame.unpersist()
