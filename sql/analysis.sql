-- Business questions answered against the loans table.
-- Each block starts with "-- name:" and is run on its own by src/02_sql_report.py.

-- name: portfolio_overview
-- How big is the book and what does it earn on paper?
SELECT
    COUNT(*)                                   AS loans,
    ROUND(SUM(funded_amnt) / 1e6, 1)           AS funded_millions,
    ROUND(AVG(funded_amnt))                    AS avg_loan,
    ROUND(AVG(int_rate), 2)                    AS avg_rate_pct,
    ROUND(AVG(annual_inc))                     AS avg_income,
    SUM(is_default)                            AS defaults,
    ROUND(100.0 * SUM(is_default) / COUNT(*), 2) AS default_rate_pct
FROM loans;

-- name: default_by_grade
-- Does the lender's own grade separate good borrowers from bad ones?
SELECT
    grade,
    COUNT(*)                                     AS loans,
    ROUND(AVG(int_rate), 2)                      AS avg_rate_pct,
    SUM(is_default)                              AS defaults,
    ROUND(100.0 * SUM(is_default) / COUNT(*), 2) AS default_rate_pct,
    ROUND(
        (1.0 * SUM(is_default) / COUNT(*))
        / (SELECT 1.0 * SUM(is_default) / COUNT(*) FROM loans), 2
    )                                            AS lift_vs_book
FROM loans
GROUP BY grade
ORDER BY grade;

-- name: price_vs_risk
-- The money question: does the interest rate cover the credit loss on each grade?
-- Loss given default is set at 65 percent of the amount funded. The default rate
-- here is over the life of the loan, not per year, so the spread is a rough guide
-- rather than a profit figure.
SELECT
    grade,
    COUNT(*)                                       AS loans,
    ROUND(AVG(int_rate), 2)                        AS rate_pct,
    ROUND(100.0 * SUM(is_default) / COUNT(*), 2)   AS default_rate_pct,
    ROUND(0.65 * 100.0 * SUM(is_default) / COUNT(*), 2) AS expected_loss_pct,
    ROUND(AVG(int_rate) - 0.65 * 100.0 * SUM(is_default) / COUNT(*), 2) AS spread_pct
FROM loans
GROUP BY grade
ORDER BY grade;

-- name: default_by_term
-- Longer loans are priced higher, but do they also go bad more often?
SELECT
    term_months,
    COUNT(*)                                     AS loans,
    ROUND(AVG(int_rate), 2)                      AS avg_rate_pct,
    ROUND(100.0 * SUM(is_default) / COUNT(*), 2) AS default_rate_pct
FROM loans
GROUP BY term_months
ORDER BY term_months;

-- name: default_by_loan_to_income
-- How much can a borrower safely borrow against income?
SELECT
    CASE
        WHEN loan_to_income < 0.10 THEN 'a. under 0.10'
        WHEN loan_to_income < 0.20 THEN 'b. 0.10 to 0.20'
        WHEN loan_to_income < 0.30 THEN 'c. 0.20 to 0.30'
        WHEN loan_to_income < 0.45 THEN 'd. 0.30 to 0.45'
        ELSE                             'e. 0.45 and over'
    END                                          AS loan_to_income_band,
    COUNT(*)                                     AS loans,
    ROUND(AVG(funded_amnt))                      AS avg_loan,
    ROUND(100.0 * SUM(is_default) / COUNT(*), 2) AS default_rate_pct
FROM loans
WHERE loan_to_income IS NOT NULL
GROUP BY loan_to_income_band
ORDER BY loan_to_income_band;

-- name: default_by_utilisation
-- Revolving credit already in use, the strongest single warning sign in most books.
SELECT
    CASE
        WHEN revol_util < 25 THEN 'a. under 25'
        WHEN revol_util < 50 THEN 'b. 25 to 50'
        WHEN revol_util < 75 THEN 'c. 50 to 75'
        WHEN revol_util < 90 THEN 'd. 75 to 90'
        ELSE                      'e. 90 and over'
    END                                          AS revolving_utilisation_pct,
    COUNT(*)                                     AS loans,
    ROUND(100.0 * SUM(is_default) / COUNT(*), 2) AS default_rate_pct
FROM loans
GROUP BY revolving_utilisation_pct
ORDER BY revolving_utilisation_pct;

-- name: default_by_enquiries
-- Shopping for credit everywhere at once is a classic distress signal.
SELECT
    MIN(inq_last_12m, 5)                         AS enquiries_last_12m,
    COUNT(*)                                     AS loans,
    ROUND(100.0 * SUM(is_default) / COUNT(*), 2) AS default_rate_pct
FROM loans
GROUP BY enquiries_last_12m
ORDER BY enquiries_last_12m;

-- name: default_by_employment
-- Does job tenure matter once the grade is known?
SELECT
    CASE
        WHEN emp_known = 0   THEN 'z. not stated'
        WHEN emp_years < 1   THEN 'a. under 1 year'
        WHEN emp_years < 3   THEN 'b. 1 to 3 years'
        WHEN emp_years < 6   THEN 'c. 3 to 6 years'
        WHEN emp_years < 10  THEN 'd. 6 to 10 years'
        ELSE                      'e. 10 years or more'
    END                                          AS employment,
    COUNT(*)                                     AS loans,
    ROUND(100.0 * SUM(is_default) / COUNT(*), 2) AS default_rate_pct
FROM loans
GROUP BY employment
ORDER BY employment;

-- name: default_by_verification
-- Is checking the stated income worth the effort?
SELECT
    verification_status,
    COUNT(*)                                     AS loans,
    ROUND(AVG(annual_inc))                       AS avg_stated_income,
    ROUND(100.0 * SUM(is_default) / COUNT(*), 2) AS default_rate_pct
FROM loans
GROUP BY verification_status
ORDER BY default_rate_pct DESC;

-- name: riskiest_states
-- Where the losses sit, limited to states with enough loans to mean something.
SELECT
    addr_state,
    COUNT(*)                                     AS loans,
    SUM(is_default)                              AS defaults,
    ROUND(100.0 * SUM(is_default) / COUNT(*), 2) AS default_rate_pct
FROM loans
GROUP BY addr_state
HAVING COUNT(*) >= 150
ORDER BY default_rate_pct DESC
LIMIT 10;

-- name: loss_concentration
-- Which grades carry the losses, and what share of the book would be given up
-- by declining them outright.
WITH by_grade AS (
    SELECT
        grade,
        COUNT(*)                        AS loans,
        SUM(is_default)                 AS defaults,
        SUM(0.65 * funded_amnt * is_default) AS credit_loss
    FROM loans
    GROUP BY grade
)
SELECT
    grade,
    loans,
    defaults,
    ROUND(credit_loss / 1e3)                                     AS credit_loss_thousands,
    ROUND(100.0 * credit_loss / SUM(credit_loss) OVER (), 1)     AS share_of_losses_pct,
    ROUND(100.0 * SUM(credit_loss) OVER (ORDER BY grade DESC)
          / SUM(credit_loss) OVER (), 1)                         AS cumulative_from_worst_pct,
    ROUND(100.0 * SUM(loans) OVER (ORDER BY grade DESC)
          / SUM(loans) OVER (), 1)                               AS cumulative_share_of_book_pct
FROM by_grade
ORDER BY grade;
