"""Loan decision tool.

Enter an application and the scorecard returns a score, a chance of default, a
decision band and the points that produced it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"
sys.path.insert(0, str(ROOT / "src"))
import score as scorer  # noqa: E402

BLUE, RED, MUTED = "#2a78d6", "#e34948", "#6b6b66"

st.set_page_config(page_title="Loan decision tool", page_icon="📊", layout="wide")


@st.cache_data
def load():
    card = scorer.load_card(OUT / "scorecard.json")
    summary = json.loads((OUT / "summary.json").read_text())
    tables = {
        name: pd.read_csv(OUT / f"{name}.csv")
        for name in ["model_metrics", "decision_bands", "risk_appetite",
                     "information_value", "scorecard_points", "sensitivity"]
    }
    return card, summary, tables


CARD, SUMMARY, TABLES = load()

# ---------------------------------------------------------------- sidebar ----
st.sidebar.title("The application")
st.sidebar.caption("Change anything and the decision updates.")

st.sidebar.subheader("The loan")
amount = st.sidebar.number_input("Amount requested", 1000, 40000, 15000, step=500)
term = st.sidebar.selectbox("Term", [36, 60], format_func=lambda m: f"{m} months")
grade = st.sidebar.selectbox("Credit grade", list("ABCDEFG"), index=2)
rate = st.sidebar.slider("Interest rate offered (percent)", 5.0, 29.0, 13.0, 0.25)

st.sidebar.subheader("The borrower")
income = st.sidebar.number_input("Annual income", 10000, 500000, 65000, step=1000)
emp_stated = st.sidebar.checkbox("Employment length was given", value=True)
emp_years = st.sidebar.slider("Years in the current job", 0.0, 10.0, 5.0, 0.5,
                              disabled=not emp_stated)
verification = st.sidebar.selectbox(
    "Income checked?", ["Not_Verified", "Source_Verified", "Verified"], index=1,
    format_func=lambda v: {"Not_Verified": "Not checked",
                           "Source_Verified": "Checked at source",
                           "Verified": "Documents requested"}[v],
)

st.sidebar.subheader("The credit file")
inq6 = st.sidebar.number_input("Credit enquiries, last 6 months", 0, 10, 0)
inq12 = st.sidebar.number_input("Credit enquiries, last 12 months", 0, 20, 1)
inq_fi = st.sidebar.number_input("Finance company enquiries", 0, 15, 0)
open6 = st.sidebar.number_input("Instalment accounts opened, last 6 months", 0, 20, 1)
open12 = st.sidebar.number_input("Instalment accounts opened, last 12 months", 0, 20, 1)
open24 = st.sidebar.number_input("Instalment accounts opened, last 24 months", 0, 30, 2)
num_il = st.sidebar.number_input("Instalment accounts held", 0, 60, 7)
bal_il = st.sidebar.number_input("Balance on instalment accounts", 0, 600000,
                                 23000, step=1000)
limit_il = st.sidebar.number_input("Credit limit on instalment accounts", 0, 600000,
                                   34000, step=1000)
all_util = st.sidebar.slider("Credit in use across all accounts (percent)",
                             0, 150, 60)

pay = scorer.instalment(amount, rate, term)
application = {
    "grade": grade,
    "term_months": str(term),
    "verification_status": verification,
    "emp_years": emp_years if emp_stated else None,
    "instalment_to_income": pay * 12 / income if income else None,
    "inq_last_6mths": inq6, "inq_last_12m": inq12, "inq_fi": inq_fi,
    "open_il_6m": open6, "open_il_12m": open12, "open_il_24m": open24,
    "num_il_tl": num_il, "total_bal_il": bal_il,
    "total_il_high_credit_limit": limit_il, "all_util": all_util,
}

result = scorer.score_application(application, CARD)
score, pd_est, band = result["score"], result["probability"], result["band"]
cutoff = CARD["cutoff"]
breakdown = pd.DataFrame(result["lines"]).sort_values("points")

# ------------------------------------------------------------------- main ----
st.title("Loan decision tool")
st.caption(
    f"A credit scorecard trained on {SUMMARY['rows']:,} consumer loans. Every "
    "point below traces back to one line of the application, which is what a "
    "credit committee and a regulator both ask for."
)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Score", f"{score}")
c2.metric("Chance of default", f"{pd_est:.1%}")
c3.metric("Monthly payment", f"${pay:,.0f}")
c4.metric("Cutoff in force", f"{cutoff}")

if band.startswith(("A", "B")):
    st.success(f"**{band[3:].capitalize()}**  ·  score {score} against a cutoff of {cutoff}")
elif band.startswith("C"):
    st.warning(f"**{band[3:].capitalize()}**  ·  score {score} against a cutoff of {cutoff}")
else:
    st.error(f"**{band[3:].capitalize()}**  ·  score {score} against a cutoff of {cutoff}")

tab1, tab2, tab3 = st.tabs(["Why this score", "The scorecard", "How it performs"])

with tab1:
    st.subheader("Where this application lost points")
    st.caption(
        "Each bar is the gap between the points this application earned on that "
        "line and the best band available on it. The longest bar is the reason "
        "for the decision."
    )
    lost = breakdown.sort_values("points_lost")
    fig, ax = plt.subplots(figsize=(8, 5.2))
    ax.barh(lost["label"], lost["points_lost"],
            color=[RED if v > 0 else BLUE for v in lost["points_lost"]], height=0.65)
    for i, (_, r) in enumerate(lost.iterrows()):
        ax.text(r["points_lost"] + 0.6, i,
                f"{r['points_lost']}  ({r['bin']})", va="center", fontsize=8.5,
                color=MUTED)
    ax.set_xlim(0, max(4, lost["points_lost"].max() * 1.55))
    ax.set_xlabel("points given up against the best band")
    ax.set_title(f"Score {score} of a possible "
                 f"{int(breakdown['best_possible'].sum())}",
                 loc="left", fontweight="bold")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.grid(axis="x", color="#ededea")
    ax.set_axisbelow(True)
    fig.tight_layout()
    st.pyplot(fig)
    shown = breakdown[["label", "value", "bin", "points", "best_possible",
                       "bin_default_rate_pct"]].sort_values("points").copy()
    shown["value"] = shown["value"].map(
        lambda v: "not stated" if v is None else
        (f"{v:,.3f}".rstrip("0").rstrip(".") if isinstance(v, float) else f"{v:,}"
         if isinstance(v, int) else str(v))
    )
    st.dataframe(
        shown.rename(columns={"label": "Line on the application", "value": "Value entered",
                         "bin": "Band it falls in", "points": "Points",
                         "best_possible": "Best band",
                         "bin_default_rate_pct": "Default rate in that band (%)"}),
        hide_index=True, width="stretch")

with tab2:
    st.subheader("Every rule in the scorecard")
    st.caption("This is the whole model. Points add up to the score, so it runs "
               "in a spreadsheet as easily as in Python.")
    st.dataframe(TABLES["scorecard_points"].drop(columns=["code"], errors="ignore"),
                 hide_index=True, width="stretch")
    st.subheader("Which fields carry the signal")
    st.dataframe(TABLES["information_value"], hide_index=True, width="stretch")

with tab3:
    st.subheader("Against the lender's own grade")
    st.dataframe(TABLES["model_metrics"], hide_index=True, width="stretch")
    st.caption("AUC is the chance the model ranks a loan that went bad below one "
               "that was repaid. The scorecard beats the lender's own grade on "
               "loans it was never trained on.")
    st.subheader("What a loss target costs in volume")
    st.dataframe(TABLES["risk_appetite"], hide_index=True, width="stretch")
    st.subheader("The bands in use")
    st.dataframe(TABLES["decision_bands"], hide_index=True, width="stretch")

st.divider()
st.caption(
    f"Data: {SUMMARY['rows']:,} Lending Club loans from the first quarter of "
    "2016, via the modeldata R package. Built by Devin McIntosh."
)
