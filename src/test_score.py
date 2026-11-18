"""Check that the exported scorecard reproduces the model it came from."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import score as scorer  # noqa: E402
import woe  # noqa: E402


def main() -> None:
    card = scorer.load_card()
    art = joblib.load(ROOT / "outputs" / "model.joblib")
    with sqlite3.connect(ROOT / "data" / "loans.db") as con:
        df = pd.read_sql_query("SELECT * FROM loans", con)

    sample = df.sample(400, random_state=7)
    X = woe.transform_all(sample, art["bins"])[art["columns"]]
    p_model = art["model"].predict_proba(X)[:, 1]
    odds = np.clip((1 - p_model) / np.clip(p_model, 1e-9, None), 1e-9, None)
    score_model = card["factor"] * np.log(odds) + card["offset"]

    diffs, p_diffs = [], []
    for (_, row), sm, pm in zip(sample.iterrows(), score_model, p_model):
        app = {name: row.get(name) for name in card["by_name"]}
        app["term_months"] = str(int(row["term_months"]))
        app["emp_years"] = None if pd.isna(row["emp_years"]) else float(row["emp_years"])
        out = scorer.score_application(app, card)
        diffs.append(out["score"] - sm)
        p_diffs.append(out["probability"] - pm)

    diffs, p_diffs = np.array(diffs), np.array(p_diffs)
    print(f"loans checked: {len(diffs)}")
    print(f"score difference: mean {diffs.mean():+.2f}, largest {np.abs(diffs).max():.2f}")
    print(f"probability difference: largest {np.abs(p_diffs).max():.4f}")

    # Points are whole numbers, so a small rounding gap is expected and fine.
    assert np.abs(diffs).max() < 8, "scorecard does not reproduce the model"
    assert np.abs(p_diffs).max() < 0.03, "probabilities drifted too far"
    print("\nPASS: the points scorecard matches the fitted model")


if __name__ == "__main__":
    main()
