"""Phase 3 modelling harness: baseline vs a calibrated model, honestly scored.

Design choices that matter for rigor:

* **Time-based split** (train on earlier sailings, test on later) — never a random
  split. Random splitting leaks future weather into the past and flatters the
  model; a delay predictor must be judged on genuinely unseen future sailings.
* **Baseline first.** A model that can't beat "always predict the base rate"
  (Brier / log loss) has learned nothing. We print the baseline every run.
* **Calibrated probabilities.** "30% chance of delay" must mean it. We score
  Brier + log loss and print a reliability table, not just accuracy — accuracy is
  meaningless on an imbalanced, mostly-on-time target.

Runs today against thin data: it will report that there aren't enough disrupted
sailings yet and stop cleanly. The point is that come autumn you just re-run it.
"""
from __future__ import annotations

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.dummy import DummyClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score, brier_score_loss,
                             log_loss, roc_auc_score)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .config import Config
from .features import FEATURES, TARGET, load_frame, xy

MIN_ROWS = 60          # below this, scoring a split is noise
MIN_POSITIVES = 12     # need enough disrupted sailings to learn/evaluate
TEST_FRACTION = 0.25


def _pipeline() -> Pipeline:
    return Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        ("lr", LogisticRegression(max_iter=1000, class_weight="balanced")),
    ])


def _scores(y_true, prob) -> dict:
    out = {
        "brier": brier_score_loss(y_true, prob),
        "logloss": log_loss(y_true, prob, labels=[0, 1]),
    }
    if len(set(y_true)) == 2:  # AUC/AP undefined on a single-class test set
        out["roc_auc"] = roc_auc_score(y_true, prob)
        out["pr_auc"] = average_precision_score(y_true, prob)
    return out


def _fmt(scores: dict) -> str:
    return "  ".join(f"{k}={v:.3f}" for k, v in scores.items())


def _reliability(y_true, prob, bins: int = 5) -> None:
    y_true = np.asarray(y_true)
    prob = np.asarray(prob)
    edges = np.linspace(0, 1, bins + 1)
    print("  predicted -> observed (reliability):")
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (prob >= lo) & (prob < hi if hi < 1 else prob <= hi)
        if mask.sum() == 0:
            continue
        print(f"    [{lo:.1f},{hi:.1f})  n={mask.sum():>3}  "
              f"pred={prob[mask].mean():.2f}  actual={y_true[mask].mean():.2f}")


def main() -> int:
    cfg = Config.load()
    df = load_frame(cfg)

    if df.empty:
        print("No usable sailings yet.")
        return 0

    n = len(df)
    pos = int(df[TARGET].sum())
    span = f"{df['aimed_departure'].min():%Y-%m-%d} .. {df['aimed_departure'].max():%Y-%m-%d}"
    print(f"rows={n}  disrupted={pos} ({pos/n:.1%})  span={span}\n")

    if n < MIN_ROWS or pos < MIN_POSITIVES:
        print(f"SCAFFOLD READY — not enough signal to train yet "
              f"(need >={MIN_ROWS} rows and >={MIN_POSITIVES} disrupted; "
              f"have {n} rows, {pos} disrupted).")
        print("Re-run this once autumn weather has built up the dataset.")
        return 0

    split = int(n * (1 - TEST_FRACTION))
    train, test = df.iloc[:split], df.iloc[split:]
    Xtr, ytr = xy(train)
    Xte, yte = xy(test)
    print(f"time split: train={len(train)} (to {train['aimed_departure'].max():%Y-%m-%d}) "
          f"test={len(test)} (from {test['aimed_departure'].min():%Y-%m-%d})\n")

    if ytr.nunique() < 2:
        print("Training window has only one class — need a longer span. Re-run later.")
        return 0

    # Baseline: constant base-rate probability from the training window.
    base = DummyClassifier(strategy="prior").fit(Xtr, ytr)
    base_prob = base.predict_proba(Xte)[:, 1]
    print("BASELINE (predict base rate):")
    print("  " + _fmt(_scores(yte, base_prob)))

    # Model: calibrated logistic regression, calibration fit on the train window.
    model = CalibratedClassifierCV(_pipeline(), method="sigmoid", cv=3)
    model.fit(Xtr, ytr)
    prob = model.predict_proba(Xte)[:, 1]
    print("\nMODEL (calibrated logistic regression):")
    print("  " + _fmt(_scores(yte, prob)))
    _reliability(yte, prob)

    # Interpretability: standardized coefficients from a plain fit.
    plain = _pipeline().fit(Xtr, ytr)
    coefs = plain.named_steps["lr"].coef_[0]
    print("\nstandardized coefficients (direction & strength):")
    for name, c in sorted(zip(FEATURES, coefs), key=lambda t: -abs(t[1])):
        print(f"  {name:<13} {c:+.3f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
