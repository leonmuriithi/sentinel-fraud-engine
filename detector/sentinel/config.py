import os
from dataclasses import dataclass


def _int(name, default):
    return int(os.getenv(name, default))


def _float(name, default):
    return float(os.getenv(name, default))


@dataclass(frozen=True)
class Config:
    kafka_bootstrap: str
    input_topic: str
    alert_topic: str
    dlq_topic: str
    consumer_group: str
    redis_url: str
    velocity_window_seconds: int
    velocity_rule: int
    amount_rule: float
    location_jump_seconds: int
    contamination: float
    model_seed: int
    max_backoff_seconds: int
    log_level: str


def load_config():
    return Config(
        kafka_bootstrap=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092"),
        input_topic=os.getenv("INPUT_TOPIC", "transaction-stream"),
        alert_topic=os.getenv("ALERT_TOPIC", "fraud-alerts"),
        dlq_topic=os.getenv("DLQ_TOPIC", "transaction-dlq"),
        consumer_group=os.getenv("CONSUMER_GROUP", "sentinel-detector"),
        redis_url=os.getenv("REDIS_URL", "redis://redis:6379/0"),
        velocity_window_seconds=_int("VELOCITY_WINDOW_SECONDS", 3600),
        velocity_rule=_int("VELOCITY_RULE", 8),
        amount_rule=_float("AMOUNT_RULE", 1_000_000),
        location_jump_seconds=_int("LOCATION_JUMP_SECONDS", 60),
        contamination=_float("CONTAMINATION", 0.01),
        model_seed=_int("MODEL_SEED", 42),
        max_backoff_seconds=_int("MAX_BACKOFF_SECONDS", 30),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
    )
