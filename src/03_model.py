"""Build the default model, turn it into a scorecard, and pick a cutoff on profit.

Four models are compared:
  1. the lender's own grade, as a benchmark
  2. a scorecard built only from application and credit bureau fields
  3. the same scorecard with the grade added
  4. gradient boosting on the same inputs, to show what the simple model gives up

The cutoff is then chosen on expected profit per loan, not on accuracy.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, roc_curve
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split

sys.path.insert(0, str(Path(__file__).resolve().parent))
import woe  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "loans.db"
OUT = ROOT / "outputs"
SEED = 42

NUMERIC = [
    "funded_amnt", "annual_inc", "loan_to_income", "instalment_to_income",
    "emp_years", "delinq_2yrs", "inq_last_6mths", "revol_util", "acc_now_delinq",
    "open_il_6m", "open_il_12m", "open_il_24m", "total_bal_il", "all_util",
    "inq_fi", "inq_last_12m", "delinq_amnt", "num_il_tl",
    "total_il_high_credit_limit",
]
CATEGORICAL = ["term_months", "verification_status", "emp_known"]
GRADE = "grade"
# addr_state is left out. Fifty states across 9,857 loans is too thin to trust,
# and pricing by location invites a fair lending problem.
# int_rate is left out because it is set from the grade, so it would tell the
# model the answer it is meant to work out.

# Economics of one loan, per dollar of principal.
LGD = 0.65              # lost when a loan goes bad
COST_OF_FUNDS = 0.05    # a year, on the balance still outstanding
SERVICING = 0.01        # a year, on the balance still outstanding
AVG_BALANCE = 0.55      # average outstanding share of principal over the term
INTEREST_REALISED = 1.00  # share of scheduled interest actually collected on a good loan

PDO = 20                # points that double the odds
BASE_SCORE = 600
BASE_ODDS = 20


def ks_stat(y: np.ndarray, p: np.ndarray) -> float:
    fpr, tpr, _ = roc_curve(y, p)
    return float(np.max(tpr - fpr))


def fit_scorecard(X_tr, y_tr, X_te, seed=SEED):
    model = LogisticRegression(max_iter=2000, C=1.0, random_state=seed)
    cv = cross_val_score(
        model, X_tr, y_tr,
        cv=StratifiedKFold(5, shuffle=True, random_state=seed), scoring="roc_auc",
    )
    model.fit(X_tr, y_tr)
    return model, model.predict_proba(X_te)[:, 1], cv


def main() -> None:
    with sqlite3.connect(DB) as con:
        df = pd.read_sql_query("SELECT * FROM loans", con)
    y = df["is_default"]
    train_idx, test_idx = train_test_split(
        df.index, test_size=0.25, stratify=y, random_state=SEED
    )
    tr, te = df.loc[train_idx], df.loc[test_idx]
    y_tr, y_te = y.loc[train_idx], y.loc[test_idx]
    print(f"train {len(tr)} rows ({y_tr.mean():.2%} bad), "
          f"test {len(te)} rows ({y_te.mean():.2%} bad)")

    # --- weight of evidence, learned on the training rows only ----------------
    all_bins = woe.fit_all(tr, y_tr, NUMERIC, CATEGORICAL + [GRADE])
    iv = woe.iv_frame(all_bins)
    print("\ntop features by information value")
    print(iv.head(10).to_string(index=False))

    keep = iv.loc[iv["information_value"] >= 0.02, "feature"].tolist()
    own = [f for f in keep if f != GRADE]
    bins_own = {k: all_bins[k] for k in own}
    bins_full = {k: all_bins[k] for k in keep}
    print(f"\n{len(own)} application and bureau features kept out of "
          f"{len(all_bins) - 1}")

    Xo_tr, Xo_te = woe.transform_all(tr, bins_own), woe.transform_all(te, bins_own)
    Xf_tr, Xf_te = woe.transform_all(tr, bins_full), woe.transform_all(te, bins_full)

    m_own, p_own, cv_own = fit_scorecard(Xo_tr, y_tr, Xo_te)
    m_full, p_full, cv_full = fit_scorecard(Xf_tr, y_tr, Xf_te)

    # --- gradient boosting, same inputs as the full scorecard -----------------
    raw = NUMERIC + CATEGORICAL + [GRADE]
    cats = CATEGORICAL + [GRADE]
    gbm_tr, gbm_te = tr[raw].copy(), te[raw].copy()
    for c in cats:
        levels = sorted(gbm_tr[c].astype(str).unique())
        for frame in (gbm_tr, gbm_te):
            frame[c] = pd.Categorical(frame[c].astype(str), categories=levels)
    gbm = HistGradientBoostingClassifier(
        max_depth=3, learning_rate=0.05, max_iter=300, l2_regularization=1.0,
        categorical_features=[c in cats for c in raw], random_state=SEED,
    )
    gbm.fit(gbm_tr, y_tr)
    p_gbm = gbm.predict_proba(gbm_te)[:, 1]

    # --- benchmark ------------------------------------------------------------
    grade_rate = tr.groupby(GRADE)["is_default"].mean()
    p_grade = te[GRADE].map(grade_rate).fillna(y_tr.mean()).to_numpy()

    candidates = [
        ("Lender's own grade", p_grade, None),
        ("Scorecard, no grade", p_own, cv_own),
        ("Scorecard with grade", p_full, cv_full),
        ("Gradient boosting", p_gbm, None),
    ]
    rows = []
    for name, p, cv in candidates:
        auc = roc_auc_score(y_te, p)
        rows.append({
            "model": name,
            "test_auc": round(auc, 4),
            "gini": round(2 * auc - 1, 4),
            "ks": round(ks_stat(y_te.to_numpy(), p), 4),
            "cv_auc_train": "" if cv is None else f"{cv.mean():.4f} +/- {cv.std():.4f}",
        })
    metrics = pd.DataFrame(rows)
    print("\n" + metrics.to_string(index=False))

    # The scorecard with the grade is what goes forward: it is the strongest
    # model a credit committee can read line by line.
    chosen, p_chosen, bins_chosen, model_chosen = (
        "Scorecard with grade", p_full, bins_full, m_full
    )

    # --- scorecard points -----------------------------------------------------
    factor = PDO / np.log(2)
    offset = BASE_SCORE - factor * np.log(BASE_ODDS)
    n_feat = len(bins_chosen)
    pts_rows = []
    for i, col in enumerate(Xf_tr.columns):
        name = col.replace("woe_", "")
        coef = model_chosen.coef_[0][i]
        for _, r in bins_chosen[name].table.iterrows():
            pts = -(coef * r["woe"] + model_chosen.intercept_[0] / n_feat) * factor \
                  + offset / n_feat
            pts_rows.append({
                "feature": name,
                "code": r["code"],
                "bin": str(r["bin"]),
                "loans_in_train": int(r["loans"]),
                "default_rate_pct": round(100 * r["default_rate"], 2),
                "points": int(round(pts)),
            })
    scorecard = pd.DataFrame(pts_rows)

    def to_score(p: np.ndarray) -> np.ndarray:
        odds = np.clip((1 - p) / np.clip(p, 1e-9, None), 1e-9, None)
        return factor * np.log(odds) + offset

    score_te = to_score(p_chosen)

    # --- the cutoff, chosen on money -----------------------------------------
    # Value of approving one loan: interest earned if it is repaid, loss of
    # principal if it is not, less the cost of carrying it for the term.
    years = te["term_months"] / 12.0
    scheduled_interest = te["instalment"] * te["term_months"] - te["funded_amnt"]
    carry = (COST_OF_FUNDS + SERVICING) * AVG_BALANCE * years * te["funded_amnt"]

    def loan_value(lgd: float, interest_realised: float) -> np.ndarray:
        earned = scheduled_interest * interest_realised
        return np.where(y_te == 1, -lgd * te["funded_amnt"], earned) - carry

    value = loan_value(LGD, INTEREST_REALISED)

    def profit_curve(val: np.ndarray) -> pd.DataFrame:
        grid = np.arange(np.floor(score_te.min()), np.ceil(score_te.max()) + 1, 1.0)
        rows = []
        for cut in grid:
            take = score_te >= cut
            if take.sum() < 25:
                continue
            rows.append({
                "cutoff": float(cut),
                "approval_rate": float(take.mean()),
                "approved_default_rate": float(y_te[take].mean()),
                "profit": float(val[take].sum()),
                "profit_per_application": float(val[take].sum() / len(te)),
            })
        return pd.DataFrame(rows)

    curve = profit_curve(value)
    best = curve.loc[curve["profit"].idxmax()]
    approve_all = float(value.sum())

    avg_int = float((scheduled_interest * INTEREST_REALISED / te["funded_amnt"]).mean())
    avg_carry = float((carry / te["funded_amnt"]).mean())
    break_even_p = (avg_int - avg_carry) / (avg_int + LGD)
    above_break_even = float((p_chosen > break_even_p).mean())

    print(f"\nbase case: approve everyone earns {approve_all:,.0f} over {len(te)} loans")
    print(f"best cutoff {best.cutoff:.0f}: approve {best.approval_rate:.1%}, "
          f"profit {best.profit:,.0f} ({best.profit - approve_all:+,.0f})")
    print(f"break even default probability {break_even_p:.1%}, "
          f"{above_break_even:.1%} of applications sit above it")

    # --- does the answer survive harsher assumptions? -------------------------
    sens = []
    for lgd in (0.65, 0.80, 0.95):
        for realised in (1.00, 0.70, 0.50):
            v = loan_value(lgd, realised)
            c = profit_curve(v)
            b = c.loc[c["profit"].idxmax()]
            base = float(v.sum())
            sens.append({
                "loss_given_default": lgd,
                "interest_realised": realised,
                "best_cutoff": int(b.cutoff),
                "approval_rate_pct": round(100 * b.approval_rate, 1),
                "profit_at_cutoff": round(float(b.profit)),
                "profit_approve_all": round(base),
                "uplift_pct": round(100 * (b.profit / base - 1), 1) if base > 0 else None,
            })
    sensitivity = pd.DataFrame(sens)
    print("\nsensitivity of the cutoff to harsher assumptions")
    print(sensitivity.to_string(index=False))

    # --- what a loss target costs in volume -----------------------------------
    order = np.argsort(-score_te)
    y_sorted, s_sorted = y_te.to_numpy()[order], score_te[order]
    running = np.cumsum(y_sorted) / np.arange(1, len(y_sorted) + 1)
    appetite = []
    for target in (0.02, 0.03, 0.04, 0.05):
        ok = np.where(running <= target)[0]
        if not len(ok):
            continue
        k = ok[-1]
        take = score_te >= s_sorted[k]
        appetite.append({
            "target_default_rate_pct": round(100 * target, 1),
            "cutoff": int(s_sorted[k]),
            "approval_rate_pct": round(100 * take.mean(), 1),
            "realised_default_rate_pct": round(100 * running[k], 2),
            "profit": round(float(value[take].sum())),
        })
    appetite = pd.DataFrame(appetite)
    print("\nwhat each loss target costs in volume")
    print(appetite.to_string(index=False))

    # --- decision bands, set on risk appetite ---------------------------------
    # The 3 percent loss target is used as the working cutoff.
    policy = appetite.loc[appetite["target_default_rate_pct"] == 3.0].iloc[0]
    cutoff = float(policy["cutoff"])
    edges = [-np.inf, cutoff - 15, cutoff, cutoff + 20, np.inf]
    names = ["D. decline or reprice", "C. refer to an officer", "B. approve",
             "A. approve and pre-approve more"]
    bands = pd.DataFrame({
        "band": pd.cut(score_te, bins=edges, labels=names),
        "bad": y_te.to_numpy(),
        "value": value,
    })
    band_tab = (
        bands.groupby("band", observed=True)
        .agg(loans=("bad", "size"),
             default_rate_pct=("bad", lambda s: round(100 * s.mean(), 2)),
             value_per_loan=("value", lambda s: round(float(s.mean()))))
        .reindex(names)
    )
    band_tab["share_of_applications_pct"] = (100 * band_tab["loans"] / len(te)).round(1)
    band_tab = band_tab.reset_index()
    print("\n" + band_tab.to_string(index=False))

    # --- save -----------------------------------------------------------------
    OUT.mkdir(exist_ok=True)
    iv.to_csv(OUT / "information_value.csv", index=False)
    scorecard.to_csv(OUT / "scorecard_points.csv", index=False)
    curve.to_csv(OUT / "profit_curve.csv", index=False)
    sensitivity.to_csv(OUT / "sensitivity.csv", index=False)
    appetite.to_csv(OUT / "risk_appetite.csv", index=False)
    metrics.to_csv(OUT / "model_metrics.csv", index=False)
    band_tab.to_csv(OUT / "decision_bands.csv", index=False)
    # The scorecard is saved as plain data, not as a pickled model. Points add up
    # to the score, so anything that can read JSON can run it, including a
    # spreadsheet or a core banking system.
    export = {"features": [], "factor": factor, "offset": offset,
              "cutoff": int(cutoff),
              "bands": {"edges": [float(e) for e in edges[1:-1]], "names": names}}
    for name, b in bins_chosen.items():
        feat_rows = scorecard[scorecard["feature"] == name]
        out_bins = []
        for _, r in feat_rows.iterrows():
            lo, hi = b.bounds(r["code"])
            out_bins.append({
                "code": r["code"], "label": r["bin"], "lo": lo, "hi": hi,
                "points": int(r["points"]),
                "default_rate_pct": float(r["default_rate_pct"]),
                "loans": int(r["loans_in_train"]),
            })
        export["features"].append({
            "name": name, "kind": b.kind,
            "edges": [float(e) for e in b.edges] if b.kind == "numeric" else [],
            "levels": list(b.levels), "bins": out_bins,
        })
    (OUT / "scorecard.json").write_text(json.dumps(export, indent=2))
    joblib.dump({"bins": bins_chosen, "model": model_chosen,
                 "columns": list(Xf_tr.columns)}, OUT / "model.joblib")
    np.savez(OUT / "test_scores.npz", score=score_te, y=y_te.to_numpy(),
             p_own=p_own, p_full=p_full, p_gbm=p_gbm, p_grade=p_grade,
             value=value)
    (OUT / "summary.json").write_text(json.dumps({
        "rows": int(len(df)), "train": int(len(tr)), "test": int(len(te)),
        "book_default_rate": round(float(y.mean()), 4),
        "metrics": rows,
        "chosen_model": chosen,
        "features_kept_without_grade": own,
        "profit_optimal_cutoff": int(round(float(best.cutoff))),
        "profit_optimal_approval_rate": round(float(best.approval_rate), 4),
        "profit_approve_all": round(approve_all),
        "break_even_default_prob": round(float(break_even_p), 4),
        "share_above_break_even": round(above_break_even, 4),
        "policy_cutoff": int(cutoff),
        "policy_approval_rate": round(float(policy["approval_rate_pct"]) / 100, 4),
        "policy_default_rate": round(float(policy["realised_default_rate_pct"]) / 100, 4),
        "assumptions": {"lgd": LGD, "cost_of_funds": COST_OF_FUNDS,
                        "servicing": SERVICING, "avg_balance": AVG_BALANCE,
                        "interest_realised": INTEREST_REALISED,
                        "pdo": PDO, "base_score": BASE_SCORE,
                        "base_odds": BASE_ODDS},
    }, indent=2))
    print(f"\nartefacts written to {OUT}")


if __name__ == "__main__":
    main()
