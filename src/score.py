"""Score one application against the exported scorecard.

The scorecard is plain JSON. Points add up to the score, and the score converts
back to a probability of default, so this module needs nothing but the standard
library.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

CARD_PATH = Path(__file__).resolve().parents[1] / "outputs" / "scorecard.json"

READABLE = {
    "grade": "Credit grade",
    "term_months": "Term",
    "verification_status": "Income checked",
    "emp_years": "Years in the job",
    "instalment_to_income": "Payment against income",
    "inq_last_6mths": "Enquiries, 6 months",
    "inq_last_12m": "Enquiries, 12 months",
    "inq_fi": "Finance company enquiries",
    "open_il_6m": "Accounts opened, 6 months",
    "open_il_12m": "Accounts opened, 12 months",
    "open_il_24m": "Accounts opened, 24 months",
    "num_il_tl": "Instalment accounts held",
    "total_bal_il": "Balance on instalment accounts",
    "total_il_high_credit_limit": "Limit on instalment accounts",
    "all_util": "Credit in use, all accounts",
}


BIN_NAMES = {
    "Not_Verified": "income not checked",
    "Source_Verified": "income checked at source",
    "Verified": "documents requested",
    "36": "36 months",
    "60": "60 months",
}


def load_card(path: Path | str = CARD_PATH) -> dict:
    card = json.loads(Path(path).read_text())
    card["by_name"] = {f["name"]: f for f in card["features"]}
    return card


def pick_bin(feature: dict, value) -> dict:
    """Find the bin a value falls in. Numeric bins carry their own bounds."""
    bins = feature["bins"]
    missing = next((b for b in bins if b["code"] == "missing"), None)
    if value is None or (isinstance(value, float) and math.isnan(value)):
        if missing is not None:
            return missing
        return min(bins, key=lambda b: b["points"])
    if feature["kind"] == "categorical":
        text = str(value)
        hit = next((b for b in bins if b["code"] == text), None)
        if hit is not None:
            return hit
        other = next((b for b in bins if b["code"] == "other"), None)
        return other or min(bins, key=lambda b: b["points"])
    for b in bins:
        if b["lo"] is None:
            continue
        lo, hi = b["lo"], b["hi"]
        if (lo == -math.inf or value > lo) and (value <= hi or hi == math.inf):
            return b
    return min(bins, key=lambda b: b["points"])


def score_application(application: dict, card: dict) -> dict:
    """Return the score, the probability of default, the band and the workings."""
    lines = []
    for name, feature in card["by_name"].items():
        b = pick_bin(feature, application.get(name))
        best = max(x["points"] for x in feature["bins"])
        lines.append({
            "feature": name,
            "label": READABLE.get(name, name),
            "value": application.get(name),
            "bin": BIN_NAMES.get(b["label"], b["label"]),
            "points": b["points"],
            "best_possible": best,
            "points_lost": best - b["points"],
            "bin_default_rate_pct": b["default_rate_pct"],
        })
    score = sum(line["points"] for line in lines)
    return {"score": score, "probability": probability(score, card),
            "band": band_for(score, card), "lines": lines}


def probability(score: float, card: dict) -> float:
    odds = math.exp((score - card["offset"]) / card["factor"])
    return 1 / (1 + odds)


def band_for(score: float, card: dict) -> str:
    for edge, name in zip(card["bands"]["edges"], card["bands"]["names"]):
        if score < edge:
            return name
    return card["bands"]["names"][-1]


def instalment(amount: float, annual_rate_pct: float, months: int) -> float:
    r = annual_rate_pct / 100 / 12
    if r == 0:
        return amount / months
    return amount * r / (1 - (1 + r) ** (-months))
