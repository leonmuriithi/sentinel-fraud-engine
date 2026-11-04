"""Evaluate the detector on simulated transactions.

Uses the SAME decision function as the live service (sentinel.scoring), so the
figures describe the real detection logic. Data is synthetic: see the README
for what that does and does not show.

    python evaluate.py
    python evaluate.py --seeds 10 --json results.json
"""
import argparse
import json

import numpy as np

from sentinel import synthetic
from sentinel.model import train_model
from sentinel.scoring import score_and_flag

N_TEST_NORMAL = 20_000
N_TEST_ANOMALY = 400
DEFAULT_CONTAMINATION = 0.01
VELOCITY_RULE = 8
AMOUNT_RULE = 1_000_000


def run_once(seed, contamination=DEFAULT_CONTAMINATION, velocity_rule=VELOCITY_RULE,
             amount_rule=AMOUNT_RULE):
    model = train_model(seed=seed, contamination=contamination, n_estimators=200)
    rng = np.random.default_rng(10_000 + seed)           # test data is independent of training data
    X_norm = synthetic.make_normal(rng, N_TEST_NORMAL)
    X_anom = synthetic.make_anomalies(rng, N_TEST_ANOMALY)

    _, m_norm, v_norm, a_norm = score_and_flag(model, X_norm, velocity_rule, amount_rule)
    _, m_anom, v_anom, a_anom = score_and_flag(model, X_anom, velocity_rule, amount_rule)
    r_norm, r_anom = v_norm | a_norm, v_anom | a_anom

    def metrics(flag_norm, flag_anom, prefix):
        fp, tp = int(flag_norm.sum()), int(flag_anom.sum())
        return {
            f"{prefix}false_positive_rate": fp / N_TEST_NORMAL,
            f"{prefix}detection_rate": tp / N_TEST_ANOMALY,
            f"{prefix}precision": tp / (tp + fp) if (tp + fp) else 0.0,
        }

    out = metrics(m_norm, m_anom, "model_")
    out.update(metrics(m_norm | r_norm, m_anom | r_anom, "hybrid_"))
    return out


def summarise(rows):
    return {k: {"mean": float(np.mean([r[k] for r in rows])),
                "std": float(np.std([r[k] for r in rows]))} for k in rows[0]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--json")
    args = ap.parse_args()

    print(f"Simulated stream: {N_TEST_NORMAL} normal + {N_TEST_ANOMALY} anomalous test "
          f"transactions per seed, {args.seeds} seeds\n")

    headline = summarise([run_once(s) for s in range(args.seeds)])
    print(f"Headline (contamination = {DEFAULT_CONTAMINATION:.0%}, velocity rule >= {VELOCITY_RULE}/hour, amount rule >= {AMOUNT_RULE:,})")
    for k, v in headline.items():
        print(f"  {k:<28} {v['mean']:.3%}  (+/- {v['std']:.3%})")

    print("\nThreshold trade-off (contamination -> FPR / detection, model only | hybrid)")
    sweep = {}
    for c in (0.005, 0.01, 0.02, 0.05):
        s = summarise([run_once(i, contamination=c) for i in range(args.seeds)])
        sweep[str(c)] = s
        print(f"  {c:>6.1%}   model: FPR {s['model_false_positive_rate']['mean']:.2%} / "
              f"detection {s['model_detection_rate']['mean']:.1%}   |   "
              f"hybrid: FPR {s['hybrid_false_positive_rate']['mean']:.2%} / "
              f"detection {s['hybrid_detection_rate']['mean']:.1%}")

    if args.json:
        with open(args.json, "w") as f:
            json.dump({"headline": headline, "sweep": sweep, "seeds": args.seeds}, f, indent=2)
        print(f"\nWrote {args.json}")


if __name__ == "__main__":
    main()
