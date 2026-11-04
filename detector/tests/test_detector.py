import json
import unittest

from sentinel.detector import FraudDetector, InvalidTransaction, parse_transaction
from sentinel.model import train_model
from sentinel.velocity import VelocityTracker
from tests.fakes import DownRedis, FakeRedis

GOOD = {"userId": "u1", "amount": 1500, "currency": "KES",
        "location": "Nairobi", "merchantId": "M1"}

_model = None


def setUpModule():
    global _model
    _model = train_model(seed=42, n_train=20_000)


def make_detector(redis=None):
    return FraudDetector(_model, VelocityTracker(redis or FakeRedis()),
                         velocity_rule=8, amount_rule=1_000_000)


class ParseTests(unittest.TestCase):
    def test_accepts_valid_payload(self):
        self.assertEqual(parse_transaction(json.dumps(GOOD))["userId"], "u1")

    def test_rejects_invalid_json(self):
        with self.assertRaises(InvalidTransaction):
            parse_transaction(b"{not json")

    def test_rejects_non_object(self):
        with self.assertRaises(InvalidTransaction):
            parse_transaction("[1, 2, 3]")

    def test_rejects_missing_field(self):
        bad = {k: v for k, v in GOOD.items() if k != "merchantId"}
        with self.assertRaises(InvalidTransaction):
            parse_transaction(json.dumps(bad))

    def test_rejects_non_positive_or_boolean_amount(self):
        for amount in (0, -5, True, "100", None):
            with self.assertRaises(InvalidTransaction, msg=repr(amount)):
                parse_transaction(json.dumps({**GOOD, "amount": amount}))


class DetectorTests(unittest.TestCase):
    def test_ordinary_transaction_is_clean(self):
        v = make_detector().evaluate(dict(GOOD), now=1000.0)
        self.assertFalse(v.is_fraud)
        self.assertEqual(v.reasons, ())

    def test_amount_above_ceiling_trips_the_amount_rule(self):
        v = make_detector().evaluate({**GOOD, "amount": 5_000_000}, now=1000.0)
        self.assertTrue(v.is_fraud)
        self.assertIn("AMOUNT_RULE", v.reasons)

    def test_model_flags_large_amount_with_location_jump_when_no_rule_fires(self):
        det = make_detector()
        det.evaluate({**GOOD, "amount": 1500}, now=1000.0)            # establishes Nairobi
        v = det.evaluate({**GOOD, "amount": 60_000, "location": "Lagos"}, now=1020.0)
        self.assertTrue(v.location_jump)
        self.assertEqual(v.reasons, ("ANOMALY_MODEL",))              # model only: no rule fired

    def test_velocity_burst_trips_the_rule(self):
        det = make_detector()
        for i in range(7):
            det.evaluate(dict(GOOD), now=1000.0 + i)
        v = det.evaluate(dict(GOOD), now=1008.0)        # 8th transaction in the hour
        self.assertEqual(v.velocity, 8)
        self.assertIn("VELOCITY_RULE", v.reasons)

    def test_redis_outage_still_scores_and_marks_degraded(self):
        det = make_detector(DownRedis())
        v = det.evaluate({**GOOD, "amount": 5_000_000}, now=1000.0)
        self.assertTrue(v.degraded)
        self.assertTrue(v.is_fraud)                      # the amount rule needs no Redis

    def test_alert_payload_shape(self):
        alert = make_detector().evaluate({**GOOD, "amount": 5_000_000, "traceId": "t-1"},
                                         now=1000.0).to_alert()
        self.assertEqual(alert["traceId"], "t-1")
        self.assertEqual(alert["action"], "BLOCK")
        self.assertIn("AMOUNT_RULE", alert["reasons"])


if __name__ == "__main__":
    unittest.main()
