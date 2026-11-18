"""Load the Lending Club extract into a SQLite database.

Source: modeldata::lending_club (Lending Club statistics, 2016 Q1 loans),
mirrored by Rdatasets. One row is one funded loan.
"""
import sqlite3
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "lending_club_raw.csv"
DB = ROOT / "data" / "loans.db"
SOURCE = ("https://raw.githubusercontent.com/vincentarelbundock/Rdatasets"
          "/master/csv/modeldata/lending_club.csv")

EMP_MAP = {
    "emp_lt_1": 0.5, "emp_1": 1, "emp_2": 2, "emp_3": 3, "emp_4": 4, "emp_5": 5,
    "emp_6": 6, "emp_7": 7, "emp_8": 8, "emp_9": 9, "emp_ge_10": 10, "emp_unk": None,
}


def tidy(df: pd.DataFrame) -> pd.DataFrame:
    df = df.drop(columns=[c for c in ["rownames"] if c in df.columns]).copy()
    df["loan_id"] = range(1, len(df) + 1)
    df["term_months"] = df["term"].str.replace("term_", "", regex=False).astype(int)
    df["grade"] = df["sub_grade"].str[0]
    df["emp_years"] = df["emp_length"].map(EMP_MAP)
    df["emp_known"] = (df["emp_length"] != "emp_unk").astype(int)
    df["is_default"] = (df["Class"] == "bad").astype(int)
    # Instalment on an amortising loan, so loan burden can be compared to income.
    monthly_rate = df["int_rate"] / 100.0 / 12.0
    n = df["term_months"]
    df["instalment"] = (
        df["funded_amnt"] * monthly_rate / (1 - (1 + monthly_rate) ** (-n))
    ).round(2)
    df["loan_to_income"] = (df["funded_amnt"] / df["annual_inc"].replace(0, float("nan"))).round(4)
    df["instalment_to_income"] = (
        df["instalment"] * 12 / df["annual_inc"].replace(0, float("nan"))
    ).round(4)
    df = df.drop(columns=["Class", "term", "emp_length"])
    front = ["loan_id", "is_default", "grade", "sub_grade", "term_months", "int_rate",
             "funded_amnt", "instalment", "annual_inc", "loan_to_income",
             "instalment_to_income", "emp_years", "emp_known", "addr_state",
             "verification_status"]
    rest = [c for c in df.columns if c not in front]
    return df[front + rest]


def fetch() -> None:
    """Download the source extract the first time this is run."""
    if RAW.exists():
        return
    RAW.parent.mkdir(parents=True, exist_ok=True)
    print(f"downloading {SOURCE}")
    urllib.request.urlretrieve(SOURCE, RAW)


def main() -> None:
    fetch()
    df = tidy(pd.read_csv(RAW))
    DB.unlink(missing_ok=True)
    with sqlite3.connect(DB) as con:
        df.to_sql("loans", con, index=False)
        con.executescript(
            """
            CREATE INDEX idx_loans_grade ON loans(grade);
            CREATE INDEX idx_loans_state ON loans(addr_state);
            CREATE INDEX idx_loans_default ON loans(is_default);
            """
        )
        n, bad = con.execute(
            "SELECT COUNT(*), SUM(is_default) FROM loans"
        ).fetchone()
    print(f"loans table: {n} rows, {bad} defaults ({bad / n:.2%}), {df.shape[1]} columns")
    print(f"written to {DB}")


if __name__ == "__main__":
    main()
