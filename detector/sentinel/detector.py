import json
import uuid
from dataclasses import dataclass, field

from .features import build_vector
from .scoring import score_and_flag


class InvalidTransaction(ValueError):
    pass


def parse_transaction(raw):
    """Decode and validate a Kafka message value. Raises InvalidTransaction."""
    try:
        txn = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise InvalidTransaction(f"not valid JSON: {exc}") from exc
    if not isinstance(txn, dict):
        raise InvalidTransaction("payload must be a JSON object")
    for field_name in ("userId", "location", "merchantId", "currency"):
        if not isinstance(txn.get(field_name), str) or not txn[field_name]:
            raise InvalidTransaction(f"{field_name} must be a non-empty string")
    amount = txn.get("amount")
    if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not amount > 0:
        raise InvalidTransaction("amount must be a positive number")
    return txn


@dataclass(frozen=True)
class Verdict:
    trace_id: str
    user_id: str
    amount: float
    currency: str
    location: str
    merchant_id: str
    is_fraud: bool
    reasons: tuple = field(default_factory=tuple)
    anomaly_score: float = 0.0
    velocity: int = 1
    location_jump: bool = False
    degraded: bool = False

    def to_alert(self):
        return {
            "traceId": self.trace_id, "userId": self.user_id, "amount": self.amount,
            "currency": self.currency, "location": self.location,
            "merchantId": self.merchant_id, "action": "BLOCK",
            "reasons": list(self.reasons), "anomalyScore": round(self.anomaly_score, 4),
            "velocity1h": self.velocity, "locationJump": self.location_jump,
            "degraded": self.degraded,
        }


class FraudDetector:
    def __init__(self, model, tracker, velocity_rule=8, amount_rule=1_000_000):
        self.model = model
        self.tracker = tracker
        self.velocity_rule = velocity_rule
        self.amount_rule = amount_rule

    def evaluate(self, txn, now=None):
        signal = self.tracker.observe(txn["userId"], txn["location"], now=now)
        vector = build_vector(txn["amount"], signal.velocity, signal.location_jump)
        scores, model_flags, velocity_flags, amount_flags = score_and_flag(
            self.model, [vector], self.velocity_rule, self.amount_rule)

        reasons = []
        if velocity_flags[0]:
            reasons.append("VELOCITY_RULE")
        if amount_flags[0]:
            reasons.append("AMOUNT_RULE")
        if model_flags[0]:
            reasons.append("ANOMALY_MODEL")

        return Verdict(
            trace_id=str(txn.get("traceId") or uuid.uuid4()),
            user_id=txn["userId"], amount=txn["amount"], currency=txn["currency"],
            location=txn["location"], merchant_id=txn["merchantId"],
            is_fraud=bool(reasons), reasons=tuple(reasons),
            anomaly_score=float(scores[0]), velocity=signal.velocity,
            location_jump=signal.location_jump, degraded=signal.degraded,
        )
