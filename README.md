# Loan default scorecard

A credit scorecard built the way a bank builds one, on 9,857 real consumer
loans. It answers a question a lending committee actually asks: **who should we
approve, and what does a tighter loss target cost us in volume?**

**Live tool: https://loan-scorecard.streamlit.app**

## The short version

| | |
|---|---|
| Loans | 9,857, of which 517 went bad (5.25 percent) |
| Best model | Weight of evidence scorecard, AUC **0.747** on loans it never saw |
| The lender's own grade | AUC 0.730, so the scorecard adds real information |
| Gradient boosting | AUC 0.721, worse than the scorecard and far harder to explain |
| Working cutoff | Score 587, which approves 75.7 percent of applications and holds losses at 3.0 percent |

## Three findings

**1. The price already covers the risk, so profit is not what limits lending.**
The rate charged covers the expected loss at every grade, and the gap is widest
in the middle of the book rather than at the top. A loan has to
carry better than a 16 percent chance of default before it stops being worth
writing, and only 4.5 percent of applications are that risky. On expected value
alone a lender would approve everybody. What actually limits lending is risk
appetite and capital, not profit.

**2. The riskiest band is also the most profitable one.** Loans in the bottom
band default at 16.7 percent, nine times the rate of the top band, and still
return more per loan, because they carry an average rate of 20.6 percent
against 9.1 percent at the top. This is the tension a credit committee has to
settle, and it is why a loss target has to be set deliberately rather than
falling out of a model.

**3. A tighter loss target is expensive in volume.** Holding the approved book
to 2 percent defaults means turning away 38 percent of applications. Accepting
4 percent means turning away only 9 percent. That trade is the real decision,
and the table below prices it.

| Target default rate | Cutoff | Applications approved | Realised default rate |
|---|---|---|---|
| 2.0 percent | 598 | 61.7 percent | 1.97 percent |
| 3.0 percent | 587 | 75.7 percent | 3.00 percent |
| 4.0 percent | 569 | 91.0 percent | 3.97 percent |
| 5.0 percent | 557 | 96.7 percent | 4.99 percent |

## How the model was built

The modelling follows standard credit scoring practice rather than a generic
classification recipe.

1. **Weight of evidence binning.** Every field is cut into a few bins and each
   bin is scored by how far its odds of default sit from the book as a whole.
   Information value then ranks the fields. Bins are learned on the training
   rows only.
2. **Logistic regression on the binned fields,** which is what makes the result
   a scorecard: the coefficients convert into points, and the points add up to
   the score. Twenty points double the odds, and a score of 600 means 20 good
   loans to one bad one.
3. **A benchmark and a challenger.** The lender's own grade is the benchmark.
   Gradient boosting is the challenger, to show what the simple model gives up.
   The scorecard beat both.
4. **A cutoff chosen on money,** using interest earned, loss on default, cost
   of funds and servicing, then stress tested against harsher assumptions.

### What was deliberately left out

- **The interest rate**, because it is set from the grade. Including it would
  hand the model the answer it is supposed to work out.
- **The borrower's state**, because fifty states across 9,857 loans is too thin
  to trust, and lending by location invites a fair lending problem.
- Eight further fields that carried an information value under 0.02, which is
  the usual threshold for a field being worth its place on a form.

### One result worth reading twice

Loans where the lender asked for income documents defaulted at 7.8 percent.
Loans where income was never checked defaulted at 3.4 percent. Verification
does not cause default. The lender asks for documents when an application
already looks weak, so the field is recording the lender's own suspicion. It
earns its place in the model, but anyone reading the coefficient as a cause
would get it exactly backwards.

## How honest is the cutoff?

The base case assumes a good loan pays every scheduled instalment and a bad one
loses 65 percent of principal. Those assumptions are generous to the lender, so
the model was rerun across harsher ones.

| Loss on default | Interest actually collected | Best cutoff | Approved | Gain over approving everyone |
|---|---|---|---|---|
| 65 percent | all of it | none | 100 percent | nothing |
| 80 percent | 70 percent | none | 100 percent | nothing |
| 95 percent | 70 percent | 569 | 91 percent | 28 percent more profit |
| any | 50 percent | no cutoff saves it | | the book loses money whatever you do |

The honest reading: a cutoff earns its keep only when losses run high or
borrowers settle early. If only half the scheduled interest is ever collected,
no cutoff rescues the book, because the problem is the pricing rather than the
approvals.

## Running it

```bash
pip install -r requirements.txt

python src/01_build_db.py     # load the CSV into SQLite
python src/02_sql_report.py   # run the business queries
python src/03_model.py        # bin, fit, score, choose a cutoff
python src/04_charts.py       # charts for the report
python src/test_score.py      # check the scorecard reproduces the model

streamlit run app.py          # the decision tool
```

## What is in here

```
app.py                    the decision tool
sql/analysis.sql          eleven business questions, each one a named query
src/woe.py                weight of evidence binning and information value
src/score.py              scores one application from the exported scorecard
src/test_score.py         checks the points reproduce the fitted model
outputs/sql_findings.md   every query with its answer
outputs/scorecard.json    the whole model as plain data
```

The scorecard is exported as JSON rather than a pickled model. Points add up to
the score, so it runs in a spreadsheet, in a core banking system, or on paper,
which is usually what gets a model approved for use.

## The data

9,857 loans issued by Lending Club in the first quarter of 2016, taken from the
`modeldata` R package through the
[Rdatasets](https://vincentarelbundock.github.io/Rdatasets/) mirror. A loan is
marked bad if it was charged off, defaulted, or ran 21 to 120 days late.

The economics are illustrative: 65 percent loss on default, 5 percent cost of
funds, 1 percent servicing. They are set in one place at the top of
`src/03_model.py` so anyone can put their own numbers in.

## Who built it

Devin McIntosh. BSc Economics and Statistics, MSc Applied Data Science in
progress, both at UWI Mona.
