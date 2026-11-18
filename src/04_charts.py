"""Charts for the report. Light theme, one accent colour for good and one for bad."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import roc_curve

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
FIG = OUT / "charts"

BLUE, RED, GREY, INK, MUTED = "#2a78d6", "#e34948", "#c9c9c4", "#1a1a18", "#6b6b66"
plt.rcParams.update({
    "figure.dpi": 140, "savefig.dpi": 140, "figure.facecolor": "white",
    "axes.facecolor": "white", "axes.edgecolor": GREY, "axes.labelcolor": INK,
    "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlecolor": INK,
    "axes.labelsize": 9.5, "xtick.labelsize": 9, "ytick.labelsize": 9,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.grid": True,
    "grid.color": "#ededea", "grid.linewidth": 0.8, "legend.frameon": False,
    "legend.fontsize": 9, "font.family": "DejaVu Sans",
})


def tidy(ax, title, xlabel="", ylabel=""):
    ax.set_title(title, loc="left", pad=10)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.set_axisbelow(True)


def save(fig, name):
    fig.tight_layout()
    fig.savefig(FIG / name, bbox_inches="tight")
    plt.close(fig)
    print("  ", name)


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    d = np.load(OUT / "test_scores.npz")
    y, score = d["y"], d["score"]
    summary = json.loads((OUT / "summary.json").read_text())
    with sqlite3.connect(ROOT / "data" / "loans.db") as con:
        loans = pd.read_sql_query("SELECT * FROM loans", con)

    print("charts:")

    # 1. default rate by grade, against the rate charged
    g = loans.groupby("grade").agg(
        rate=("int_rate", "mean"), bad=("is_default", "mean"), n=("is_default", "size")
    ).reset_index()
    fig, ax = plt.subplots(figsize=(7.2, 3.9))
    x = np.arange(len(g))
    ax.bar(x - 0.2, g["rate"], 0.4, color=BLUE, label="interest rate charged",
           edgecolor="white", linewidth=1.5)
    ax.bar(x + 0.2, 100 * g["bad"], 0.4, color=RED, label="loans that went bad",
           edgecolor="white", linewidth=1.5)
    for i, r in g.iterrows():
        ax.text(i - 0.2, r["rate"] + 0.5, f"{r['rate']:.0f}", ha="center",
                fontsize=8, color=MUTED)
        ax.text(i + 0.2, 100 * r["bad"] + 0.5, f"{100 * r['bad']:.0f}", ha="center",
                fontsize=8, color=MUTED)
    ax.set_xticks(x, g["grade"])
    ax.legend(loc="upper left")
    tidy(ax, "The rate charged stays above the expected loss", "loan grade", "percent")
    save(fig, "01_price_vs_risk.png")

    # 2. information value
    iv = pd.read_csv(OUT / "information_value.csv").head(12).iloc[::-1]
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.barh(iv["feature"], iv["information_value"], color=BLUE, height=0.65)
    for i, (_, r) in enumerate(iv.iterrows()):
        ax.text(r["information_value"] + 0.01, i, f"{r['information_value']:.3f}",
                va="center", fontsize=8, color=MUTED)
    ax.set_xlim(0, iv["information_value"].max() * 1.18)
    tidy(ax, "What actually predicts default", "information value", "")
    save(fig, "02_information_value.png")

    # 3. ROC for every model
    fig, ax = plt.subplots(figsize=(5.4, 5.0))
    styles = [("p_grade", "Lender's own grade", GREY, "-"),
              ("p_own", "Scorecard, no grade", MUTED, "--"),
              ("p_gbm", "Gradient boosting", RED, "-"),
              ("p_full", "Scorecard with grade", BLUE, "-")]
    for key, label, colour, ls in styles:
        fpr, tpr, _ = roc_curve(y, d[key])
        auc = [m for m in summary["metrics"] if m["model"].startswith(label[:12])]
        a = auc[0]["test_auc"] if auc else 0
        ax.plot(fpr, tpr, color=colour, linestyle=ls, linewidth=2,
                label=f"{label} ({a:.3f})")
    ax.plot([0, 1], [0, 1], color=GREY, linewidth=1, linestyle=":")
    ax.legend(loc="lower right")
    tidy(ax, "Ranking power on held out loans", "false positive rate",
         "true positive rate")
    save(fig, "03_roc.png")

    # 4. score distribution, good against bad
    fig, ax = plt.subplots(figsize=(7.2, 3.9))
    bins = np.linspace(score.min(), score.max(), 34)
    ax.hist(score[y == 0], bins=bins, color=BLUE, alpha=0.85, label="repaid",
            edgecolor="white", linewidth=0.6)
    ax.hist(score[y == 1], bins=bins, color=RED, alpha=0.85, label="went bad",
            edgecolor="white", linewidth=0.6)
    ax.axvline(summary["policy_cutoff"], color=INK, linewidth=1.4, linestyle="--")
    ax.text(summary["policy_cutoff"] + 2, ax.get_ylim()[1] * 0.92,
            f"cutoff {summary['policy_cutoff']}", fontsize=8.5, color=INK)
    ax.set_yscale("log")
    ax.legend()
    tidy(ax, "Where the bad loans sit on the scorecard", "score", "loans (log scale)")
    save(fig, "04_score_distribution.png")

    # 5. what a loss target costs in volume
    ap = pd.read_csv(OUT / "risk_appetite.csv")
    fig, ax = plt.subplots(figsize=(7.2, 3.9))
    ax.plot(ap["target_default_rate_pct"], ap["approval_rate_pct"], color=BLUE,
            marker="o", markersize=7, linewidth=2)
    for _, r in ap.iterrows():
        ax.annotate(f"score {r['cutoff']:.0f}",
                    (r["target_default_rate_pct"], r["approval_rate_pct"]),
                    textcoords="offset points", xytext=(0, -16), ha="center",
                    fontsize=8, color=MUTED)
    ax.set_ylim(50, 105)
    tidy(ax, "A tighter loss target costs volume",
         "target default rate on the approved book (percent)",
         "applications approved (percent)")
    save(fig, "05_risk_appetite.png")

    # 6. default rate and value per loan by band
    b = pd.read_csv(OUT / "decision_bands.csv")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.6, 3.9))
    lab = [s.split(". ")[0] for s in b["band"]]
    ax1.bar(lab, b["default_rate_pct"], color=RED, width=0.6,
            edgecolor="white", linewidth=1.5)
    for i, v in enumerate(b["default_rate_pct"]):
        ax1.text(i, v + 0.3, f"{v:.1f}", ha="center", fontsize=8.5, color=MUTED)
    tidy(ax1, "Default rate falls across the bands", "band", "percent")
    ax2.bar(lab, b["value_per_loan"], color=BLUE, width=0.6,
            edgecolor="white", linewidth=1.5)
    for i, v in enumerate(b["value_per_loan"]):
        ax2.text(i, v + 60, f"{v:,.0f}", ha="center", fontsize=8.5, color=MUTED)
    tidy(ax2, "But the riskiest band earns the most", "band", "dollars")
    save(fig, "06_bands.png")

    print(f"\n{len(list(FIG.glob('*.png')))} charts in {FIG}")


if __name__ == "__main__":
    main()
