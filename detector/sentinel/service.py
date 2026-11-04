"""Kafka consume loop: validate, score, publish alerts, commit.

Delivery semantics: offsets are committed after processing (at-least-once).
Malformed messages go to a dead-letter topic. Broker errors are retried with
exponential backoff instead of crashing the service.
"""
import json
import logging
import time
from collections import Counter

from .detector import InvalidTransaction, parse_transaction

log = logging.getLogger("sentinel.service")
PRODUCE_ATTEMPTS = 3


class DetectorService:
    def __init__(self, consumer, producer, detector, alert_topic, dlq_topic,
                 max_backoff=30, sleep=time.sleep):
        self.consumer = consumer
        self.producer = producer
        self.detector = detector
        self.alert_topic = alert_topic
        self.dlq_topic = dlq_topic
        self.max_backoff = max_backoff
        self.sleep = sleep
        self.metrics = Counter()
        self._consecutive_errors = 0

    # ---- public ----
    def run_forever(self, should_stop=lambda: False):
        while not should_stop():
            self.run_once()

    def run_once(self):
        try:
            msg = self.consumer.poll(1.0)
        except Exception as exc:  # noqa: BLE001 - the loop must survive client errors
            self._on_kafka_error(exc)
            return
        if msg is None:
            return
        error = msg.error()
        if error:
            self._on_kafka_error(error)
            return
        self._consecutive_errors = 0

        try:
            txn = parse_transaction(msg.value())
        except InvalidTransaction as exc:
            self.metrics["invalid"] += 1
            log.warning("Invalid message sent to dead-letter topic: %s", exc)
            self._produce(self.dlq_topic, msg.key(), json.dumps({
                "reason": str(exc), "payload": _safe_text(msg.value())}).encode())
            self._commit(msg)
            return

        verdict = self.detector.evaluate(txn)
        self.metrics["processed"] += 1
        if verdict.degraded:
            self.metrics["degraded"] += 1
        if verdict.is_fraud:
            self.metrics["flagged"] += 1
            log.warning("FRAUD FLAGGED [%s] user=%s reasons=%s score=%.3f velocity=%d degraded=%s",
                        verdict.trace_id, verdict.user_id, ",".join(verdict.reasons),
                        verdict.anomaly_score, verdict.velocity, verdict.degraded)
            if not self._produce(self.alert_topic, verdict.user_id.encode(),
                                 json.dumps(verdict.to_alert()).encode()):
                self.metrics["alert_publish_failures"] += 1
                log.error("Could not publish alert for %s: %s", verdict.trace_id, verdict.to_alert())
        else:
            log.info("CLEAN [%s] user=%s", verdict.trace_id, verdict.user_id)
        self._commit(msg)

    # ---- internals ----
    def _on_kafka_error(self, error):
        self._consecutive_errors += 1
        self.metrics["kafka_errors"] += 1
        delay = min(self.max_backoff, 2 ** (self._consecutive_errors - 1))
        log.error("Kafka error (%s). Retrying in %ss", error, delay)
        self.sleep(delay)

    def _produce(self, topic, key, value):
        for attempt in range(1, PRODUCE_ATTEMPTS + 1):
            try:
                self.producer.produce(topic, key=key, value=value)
                if self.producer.flush(5) == 0:
                    return True
            except Exception as exc:  # noqa: BLE001
                log.warning("Produce to %s failed (attempt %d): %s", topic, attempt, exc)
            self.sleep(0.2 * attempt)
        return False

    def _commit(self, msg):
        try:
            self.consumer.commit(message=msg, asynchronous=False)
        except Exception as exc:  # noqa: BLE001
            self.metrics["commit_failures"] += 1
            log.warning("Offset commit failed: %s", exc)


def _safe_text(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)
