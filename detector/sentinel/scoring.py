"""The single decision function used by BOTH the live detector and evaluate.py.

Keeping one code path means the evaluation numbers describe the real detector.
A transaction is flagged if any of these fire:
  - the Isolation Forest calls it an outlier,
  - the velocity rule fires (too many transactions in the window),
  - the amount rule fires (single transaction above a hard ceiling).

Why the amount rule exists: an Isolation Forest score saturates for values far
outside the range it was trained on, so an extreme amount can score no worse
than a merely large one. A hard ceiling covers that blind spot.
"""
import numpy as np

LOG_AMOUNT_COLUMN = 0
VELOCITY_COLUMN = 1


def score_and_flag(model, X, velocity_rule, amount_rule):
    """Return (anomaly_scores, model_flags, velocity_flags, amount_flags)."""
    X = np.atleast_2d(np.asarray(X, dtype=float))
    scores = model.score_samples(X)
    model_flags = scores < model.offset_      # identical to model.predict(X) == -1
    velocity_flags = X[:, VELOCITY_COLUMN] >= velocity_rule
    amount_flags = np.expm1(X[:, LOG_AMOUNT_COLUMN]) >= amount_rule
    return scores, model_flags, velocity_flags, amount_flags
