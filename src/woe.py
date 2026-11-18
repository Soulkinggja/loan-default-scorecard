"""Weight of evidence binning, the usual way a bank builds a scorecard.

Each feature is cut into a handful of bins. For every bin we record the weight
of evidence, which is how much the odds of default in that bin differ from the
book as a whole. Information value then says how useful the whole feature is.
Everything is learned on the training rows only.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

MISSING = "missing"


def _num(v: float) -> str:
    """Format a bin edge the way a person would write it."""
    if abs(v) >= 1000:
        return f"{v:,.0f}"
    if abs(v) >= 10:
        return f"{v:,.1f}".rstrip("0").rstrip(".")
    return f"{v:,.3f}".rstrip("0").rstrip(".")


@dataclass
class Binning:
    name: str
    kind: str                      # "numeric" or "categorical"
    edges: list[float] = field(default_factory=list)
    levels: list[str] = field(default_factory=list)
    woe: dict[str, float] = field(default_factory=dict)
    table: pd.DataFrame | None = None
    iv: float = 0.0

    def labels(self, s: pd.Series) -> pd.Series:
        """Return the bin each value falls in, as a stable code.

        Numeric bins are coded by position, not by the text of the interval,
        so nothing downstream has to parse a label back into numbers.
        """
        if self.kind == "numeric":
            codes = pd.cut(s, bins=self.edges, labels=False, include_lowest=True)
            out = pd.Series(codes, index=s.index).astype("object")
            out[s.isna()] = MISSING
            return out.map(lambda v: MISSING if v == MISSING else f"b{int(v)}")
        out = s.astype("object").where(s.isin(self.levels), "other")
        out[s.isna()] = MISSING
        return pd.Series(out, index=s.index).astype(str)

    def pretty(self, code: str) -> str:
        """A human readable name for a bin code."""
        if code == MISSING:
            return "not stated"
        if self.kind != "numeric":
            return code
        i = int(code[1:])
        lo, hi = self.edges[i], self.edges[i + 1]
        if lo == -np.inf:
            return f"up to {_num(hi)}"
        if hi == np.inf:
            return f"over {_num(lo)}"
        return f"{_num(lo)} to {_num(hi)}"

    def bounds(self, code: str) -> tuple[float | None, float | None]:
        if code == MISSING or self.kind != "numeric":
            return None, None
        i = int(code[1:])
        return float(self.edges[i]), float(self.edges[i + 1])

    def transform(self, s: pd.Series) -> pd.Series:
        lab = self.labels(s)
        return lab.map(self.woe).fillna(0.0).astype(float)


def _edges(s: pd.Series, max_bins: int) -> list[float]:
    qs = np.linspace(0, 1, max_bins + 1)
    cuts = sorted(set(np.nanquantile(s.dropna(), qs)))
    if len(cuts) < 3:
        cuts = sorted(set([s.min(), s.median(), s.max()]))
    cuts[0], cuts[-1] = -np.inf, np.inf
    return cuts


def fit(
    x: pd.Series,
    y: pd.Series,
    kind: str,
    max_bins: int = 5,
    min_share: float = 0.03,
) -> Binning:
    """Fit one feature. y is 1 for a default."""
    b = Binning(name=str(x.name), kind=kind)
    if kind == "numeric":
        b.edges = _edges(x, max_bins)
    else:
        counts = x.value_counts(dropna=True)
        b.levels = counts[counts >= max(30, min_share * len(x))].index.tolist()

    lab = b.labels(x)
    g = pd.DataFrame({"bin": lab, "y": y.values}).groupby("bin", observed=True)["y"]
    tab = pd.DataFrame({"loans": g.size(), "defaults": g.sum()})
    tab["good"] = tab["loans"] - tab["defaults"]
    tab["default_rate"] = tab["defaults"] / tab["loans"]

    # 0.5 added so a bin with no defaults still gets a finite weight.
    bad_share = (tab["defaults"] + 0.5) / (tab["defaults"].sum() + 0.5 * len(tab))
    good_share = (tab["good"] + 0.5) / (tab["good"].sum() + 0.5 * len(tab))
    tab["woe"] = np.log(good_share / bad_share)
    tab["iv"] = (good_share - bad_share) * tab["woe"]

    b.woe = tab["woe"].to_dict()
    b.iv = float(tab["iv"].sum())
    tab = tab.reset_index().rename(columns={"bin": "code"})
    if b.kind == "numeric":
        tab = tab.sort_values(
            "code", key=lambda s: s.map(lambda c: 1e9 if c == MISSING else int(c[1:]))
        ).reset_index(drop=True)
    tab.insert(1, "bin", tab["code"].map(b.pretty))
    b.table = tab
    return b


def fit_all(
    df: pd.DataFrame, y: pd.Series, numeric: list[str], categorical: list[str]
) -> dict[str, Binning]:
    out: dict[str, Binning] = {}
    for c in numeric:
        out[c] = fit(df[c], y, "numeric")
    for c in categorical:
        out[c] = fit(df[c].astype(str), y, "categorical")
    return out


def transform_all(df: pd.DataFrame, bins: dict[str, Binning]) -> pd.DataFrame:
    cols = {}
    for name, b in bins.items():
        s = df[name] if b.kind == "numeric" else df[name].astype(str)
        cols[f"woe_{name}"] = b.transform(s)
    return pd.DataFrame(cols, index=df.index)


def iv_frame(bins: dict[str, Binning]) -> pd.DataFrame:
    rows = [{"feature": n, "information_value": round(b.iv, 4)} for n, b in bins.items()]
    out = pd.DataFrame(rows).sort_values("information_value", ascending=False)
    def strength(v: float) -> str:
        if v < 0.02:
            return "no use"
        if v < 0.10:
            return "weak"
        if v < 0.30:
            return "medium"
        return "strong"
    out["strength"] = out["information_value"].map(strength)
    return out.reset_index(drop=True)
