import numpy as np
from sklearn.ensemble import IsolationForest

from . import synthetic


def train_model(seed=42, contamination=0.01, n_train=20_000, n_estimators=100):
    rng = np.random.default_rng(seed)
    X = synthetic.make_training_set(rng, n_train=n_train)
    model = IsolationForest(n_estimators=n_estimators, contamination=contamination,
                            random_state=seed)
    model.fit(X)
    return model
