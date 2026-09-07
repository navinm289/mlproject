import unittest
from gold_pipeline.policy import evaluate_policy
class PolicyTests(unittest.TestCase):
    def test_nested(self):
        self.assertEqual(evaluate_policy('{"all":[{"tag":"online"},{"not":{"tag":"trusted"}}]}',["online"]),(True,None))
    def test_malformed_branch(self):
        self.assertEqual(evaluate_policy('{"any":[{"tag":"online"},{"bad":1}]}',["online"]),(False,"invalid_risk_policy"))
    def test_depth_limit(self):
        tree='{"tag":"x"}'
        for _ in range(20): tree='{"not":'+tree+'}'
        self.assertIsNotNone(evaluate_policy(tree,[])[1])
    def test_null(self):
        self.assertIsNotNone(evaluate_policy(None,[])[1])
