import json
import random
import unittest

from sentinel.detector import FraudDetector
from sentinel.model import train_model
from sentinel.service import DetectorService
from sentinel.velocity import VelocityTracker
from tests.fakes import (FakeConsumer, FakeMessage, FakeProducer, FakeRedis,
                         FlakyRedis)

_model = None


def setUpModule():
    global _model
    _model = train_model(seed=42, n_train=20_000)


def txn(user="u1", amount=1500, **extra):
    return {"userId": user, "amount": amount, "currency": "KES",
            "location": "Nairobi", "merchantId": "M1", **extra}


def msg(payload):
    return FakeMessage(value=json.dumps(payload).encode())


def build(script, redis=None, producer=None):
    sleeps = []
    consumer = FakeConsumer(script)
    producer = producer or FakeProducer()
    detector = FraudDetector(_model, VelocityTracker(redis or FakeRedis()), velocity_rule=8, amount_rule=1_000_000)
    service = DetectorService(consumer, producer, detector, "fraud-alerts", "transaction-dlq",
                              max_backoff=30, sleep=sleeps.append)
    return service, consumer, producer, sleeps


class ServiceTests(unittest.TestCase):
    def test_clean_transaction_is_committed_and_not_alerted(self):
        service, consumer, producer, _ = build([msg(txn())])
        service.run_once()
        self.assertEqual(len(consumer.commits), 1)
        self.assertEqual(producer.produced, [])
        self.assertEqual(service.metrics["processed"], 1)

    def test_fraud_publishes_one_alert(self):
        service, consumer, producer, _ = build([msg(txn(amount=5_000_000, traceId="t-9"))])
        service.run_once()
        self.assertEqual(len(producer.produced), 1)
        topic, key, value = producer.produced[0]
        self.assertEqual(topic, "fraud-alerts")
        self.assertEqual(key, b"u1")
        self.assertEqual(json.loads(value)["traceId"], "t-9")
        self.assertEqual(len(consumer.commits), 1)

    def test_malformed_message_goes_to_dead_letter_topic(self):
        service, consumer, producer, _ = build([FakeMessage(value=b"{broken")])
        service.run_once()
        self.assertEqual(producer.produced[0][0], "transaction-dlq")
        self.assertEqual(service.metrics["invalid"], 1)
        self.assertEqual(len(consumer.commits), 1)        # poison message must not block the stream

    def test_kafka_consumer_errors_back_off_then_recover(self):
        script = [FakeMessage(error="broker down"), FakeMessage(error="broker down"),
                  FakeMessage(error="broker down"), msg(txn())]
        service, consumer, _, sleeps = build(script)
        for _ in range(4):
            service.run_once()
        self.assertEqual(sleeps, [1, 2, 4])               # exponential backoff
        self.assertEqual(service.metrics["kafka_errors"], 3)
        self.assertEqual(service.metrics["processed"], 1)  # recovered and processed the message

    def test_backoff_is_capped(self):
        script = [FakeMessage(error="down")] * 10
        service, _, _, sleeps = build(script)
        for _ in range(10):
            service.run_once()
        self.assertEqual(max(sleeps), 30)

    def test_poll_exception_does_not_crash_the_loop(self):
        service, _, _, sleeps = build([RuntimeError("socket closed"), msg(txn())])
        service.run_once()
        service.run_once()
        self.assertEqual(sleeps, [1])
        self.assertEqual(service.metrics["processed"], 1)

    def test_transient_producer_failure_is_retried(self):
        service, _, producer, _ = build([msg(txn(amount=5_000_000))],
                                        producer=FakeProducer(fail_times=2))
        service.run_once()
        self.assertEqual(len(producer.produced), 1)
        self.assertEqual(service.metrics["alert_publish_failures"], 0)

    def test_persistent_producer_failure_is_counted_not_fatal(self):
        service, consumer, producer, _ = build([msg(txn(amount=5_000_000))],
                                               producer=FakeProducer(fail_times=99))
        service.run_once()
        self.assertEqual(producer.produced, [])
        self.assertEqual(service.metrics["alert_publish_failures"], 1)
        self.assertEqual(len(consumer.commits), 1)

    def test_redis_cache_miss_and_outage_both_keep_processing(self):
        from tests.fakes import DownRedis
        service, _, _, _ = build([msg(txn()), msg(txn())], redis=DownRedis())
        service.run_once()
        service.run_once()
        self.assertEqual(service.metrics["processed"], 2)
        self.assertEqual(service.metrics["degraded"], 2)


class SimulatedLoadTests(unittest.TestCase):
    def test_flaky_redis_under_load_loses_no_messages_and_still_catches_outliers(self):
        rng = random.Random(3)
        messages, injected = [], set()
        for i in range(600):
            amount = rng.lognormvariate(7.5, 0.8)
            payload = txn(user=f"user{rng.randrange(150)}", amount=amount, traceId=f"t{i}")
            if i % 50 == 0:                               # inject obvious outliers
                payload["amount"] = 5_000_000
                injected.add(f"t{i}")
            messages.append(msg(payload))

        service, consumer, producer, _ = build(messages, redis=FlakyRedis(failure_rate=0.15))
        for _ in range(len(messages)):
            service.run_once()

        alerted = {json.loads(v)["traceId"] for t, _, v in producer.produced if t == "fraud-alerts"}
        self.assertEqual(service.metrics["processed"], 600)      # nothing dropped
        self.assertEqual(len(consumer.commits), 600)             # everything committed
        self.assertGreater(service.metrics["degraded"], 0)       # Redis failures really happened
        self.assertTrue(injected <= alerted)                     # every outlier still flagged
        self.assertEqual(service.metrics["alert_publish_failures"], 0)


if __name__ == "__main__":
    unittest.main()
