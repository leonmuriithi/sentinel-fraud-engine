"""Feature layout shared by training, evaluation and the live detector."""
import math

FEATURE_NAMES = ("log_amount", "velocity_1h", "location_jump")


def build_vector(amount, velocity, location_jump):
    return [math.log1p(amount), float(velocity), 1.0 if location_jump else 0.0]
