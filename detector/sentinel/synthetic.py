"""Simulated transaction generators.

The demo model is trained on synthetic data because no real payment data is
bundled with this project. Replace make_training_set() with real history to
use the detector on real traffic.
"""
import numpy as np


def make_normal(rng, n):
    amount = rng.lognormal(mean=7.5, sigma=0.8, size=n)       # median about KES 1,800
    velocity = rng.poisson(2, size=n) + 1                      # transactions in the last hour
    location_jump = (rng.random(n) < 0.02).astype(float)       # occasional benign travel
    return np.column_stack([np.log1p(amount), velocity, location_jump])


def make_anomalies(rng, n):
    """Three anomaly types: large amount, velocity burst, mixed with a location jump."""
    kinds = rng.integers(0, 3, size=n)
    amount = rng.lognormal(mean=7.5, sigma=0.8, size=n)
    velocity = rng.poisson(2, size=n) + 1
    location_jump = np.zeros(n)

    big = kinds == 0
    amount[big] *= rng.uniform(6, 25, size=big.sum())

    burst = kinds == 1
    velocity[burst] = rng.integers(10, 30, size=burst.sum())

    mixed = kinds == 2
    amount[mixed] *= rng.uniform(3, 10, size=mixed.sum())
    velocity[mixed] = rng.integers(6, 15, size=mixed.sum())
    location_jump[mixed] = 1.0

    return np.column_stack([np.log1p(amount), velocity, location_jump])


def make_training_set(rng, n_train=20_000, hidden_share=0.01):
    """Unlabelled stream with a small share of hidden anomalies, as a real stream would have."""
    n_hidden = int(n_train * hidden_share)
    X = np.vstack([make_normal(rng, n_train - n_hidden), make_anomalies(rng, n_hidden)])
    rng.shuffle(X)
    return X
