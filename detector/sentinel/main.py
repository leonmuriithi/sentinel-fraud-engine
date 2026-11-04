import logging
import signal

import redis
from confluent_kafka import Consumer, Producer

from .config import load_config
from .detector import FraudDetector
from .model import train_model
from .service import DetectorService
from .velocity import VelocityTracker


def main():
    cfg = load_config()
    logging.basicConfig(level=cfg.log_level,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    log = logging.getLogger("sentinel.main")

    log.info("Training demo Isolation Forest on synthetic data (seed=%d)", cfg.model_seed)
    model = train_model(seed=cfg.model_seed, contamination=cfg.contamination)

    redis_client = redis.Redis.from_url(cfg.redis_url, decode_responses=True,
                                        socket_connect_timeout=2, socket_timeout=2)
    tracker = VelocityTracker(redis_client, cfg.velocity_window_seconds, cfg.location_jump_seconds)
    detector = FraudDetector(model, tracker, velocity_rule=cfg.velocity_rule,
                             amount_rule=cfg.amount_rule)

    consumer = Consumer({
        "bootstrap.servers": cfg.kafka_bootstrap,
        "group.id": cfg.consumer_group,
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
        "allow.auto.create.topics": True,
    })
    producer = Producer({"bootstrap.servers": cfg.kafka_bootstrap})
    consumer.subscribe([cfg.input_topic])

    service = DetectorService(consumer, producer, detector, cfg.alert_topic, cfg.dlq_topic,
                              max_backoff=cfg.max_backoff_seconds)

    stopping = {"flag": False}

    def _stop(*_):
        stopping["flag"] = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    log.info("Detector ready. Listening on topic '%s'", cfg.input_topic)
    try:
        service.run_forever(should_stop=lambda: stopping["flag"])
    finally:
        consumer.close()
        log.info("Shutdown complete. Metrics: %s", dict(service.metrics))


if __name__ == "__main__":
    main()
