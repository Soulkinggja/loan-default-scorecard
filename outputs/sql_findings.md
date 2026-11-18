# What the SQL says

Every table below is the output of a query in `sql/analysis.sql`.

## Portfolio overview

How big is the book and what does it earn on paper?

|   loans |   funded_millions |   avg_loan |   avg_rate_pct |   avg_income |   defaults |   default_rate_pct |
|--------:|------------------:|-----------:|---------------:|-------------:|-----------:|-------------------:|
|    9857 |             154.6 |      15684 |          12.53 |        80320 |        517 |               5.25 |

## Default by grade

Does the lender's own grade separate good borrowers from bad ones?

| grade   |   loans |   avg_rate_pct |   defaults |   default_rate_pct |   lift_vs_book |
|:--------|--------:|---------------:|-----------:|-------------------:|---------------:|
| A       |    1945 |           6.68 |         17 |               0.87 |           0.17 |
| B       |    2954 |           9.95 |         74 |               2.51 |           0.48 |
| C       |    2657 |          13.46 |        148 |               5.57 |           1.06 |
| D       |    1240 |          17.61 |        118 |               9.52 |           1.81 |
| E       |     720 |          20.75 |         90 |              12.5  |           2.38 |
| F       |     266 |          24.34 |         49 |              18.42 |           3.51 |
| G       |      75 |          28    |         21 |              28    |           5.34 |

## Price vs risk

The money question: does the interest rate cover the credit loss on each grade? Loss given default is set at 65 percent of the amount funded. The default rate here is over the life of the loan, not per year, so the spread is a rough guide rather than a profit figure.

| grade   |   loans |   rate_pct |   default_rate_pct |   expected_loss_pct |   spread_pct |
|:--------|--------:|-----------:|-------------------:|--------------------:|-------------:|
| A       |    1945 |       6.68 |               0.87 |                0.57 |         6.11 |
| B       |    2954 |       9.95 |               2.51 |                1.63 |         8.32 |
| C       |    2657 |      13.46 |               5.57 |                3.62 |         9.84 |
| D       |    1240 |      17.61 |               9.52 |                6.19 |        11.42 |
| E       |     720 |      20.75 |              12.5  |                8.13 |        12.62 |
| F       |     266 |      24.34 |              18.42 |               11.97 |        12.36 |
| G       |      75 |      28    |              28    |               18.2  |         9.8  |

## Default by term

Longer loans are priced higher, but do they also go bad more often?

|   term_months |   loans |   avg_rate_pct |   default_rate_pct |
|--------------:|--------:|---------------:|-------------------:|
|            36 |    7047 |          11.28 |               4.65 |
|            60 |    2810 |          15.66 |               6.73 |

## Default by loan to income

How much can a borrower safely borrow against income?

| loan_to_income_band   |   loans |   avg_loan |   default_rate_pct |
|:----------------------|--------:|-----------:|-------------------:|
| a. under 0.10         |    1443 |       7047 |               4.02 |
| b. 0.10 to 0.20       |    3239 |      13252 |               5.13 |
| c. 0.20 to 0.30       |    2734 |      18176 |               5.19 |
| d. 0.30 to 0.45       |    2054 |      20790 |               6.28 |
| e. 0.45 and over      |     385 |      23572 |               5.71 |

## Default by utilisation

Revolving credit already in use, the strongest single warning sign in most books.

| revolving_utilisation_pct   |   loans |   default_rate_pct |
|:----------------------------|--------:|-------------------:|
| a. under 25                 |    1532 |               4.77 |
| b. 25 to 50                 |    3153 |               4.66 |
| c. 50 to 75                 |    3221 |               5.37 |
| d. 75 to 90                 |    1336 |               5.99 |
| e. 90 and over              |     615 |               7.15 |

## Default by enquiries

Shopping for credit everywhere at once is a classic distress signal.

|   enquiries_last_12m |   loans |   default_rate_pct |
|---------------------:|--------:|-------------------:|
|                    0 |    2518 |               3.14 |
|                    1 |    2349 |               5.02 |
|                    2 |    1791 |               5.58 |
|                    3 |    1131 |               5.31 |
|                    4 |     734 |               6.54 |
|                    5 |    1334 |               8.4  |

## Default by employment

Does job tenure matter once the grade is known?

| employment          |   loans |   default_rate_pct |
|:--------------------|--------:|-------------------:|
| a. under 1 year     |     733 |               5.59 |
| b. 1 to 3 years     |    1474 |               6.31 |
| c. 3 to 6 years     |    1937 |               4.65 |
| d. 6 to 10 years    |    1616 |               5.14 |
| e. 10 years or more |    3452 |               4.78 |
| z. not stated       |     645 |               6.98 |

## Default by verification

Is checking the stated income worth the effort?

| verification_status   |   loans |   avg_stated_income |   default_rate_pct |
|:----------------------|--------:|--------------------:|-------------------:|
| Verified              |    2681 |               75831 |               7.83 |
| Source_Verified       |    3742 |               84468 |               5.05 |
| Not_Verified          |    3434 |               79306 |               3.44 |

## Riskiest states

Where the losses sit, limited to states with enough loans to mean something.

| addr_state   |   loans |   defaults |   default_rate_pct |
|:-------------|--------:|-----------:|-------------------:|
| VA           |     291 |         19 |               6.53 |
| FL           |     731 |         47 |               6.43 |
| GA           |     320 |         20 |               6.25 |
| AZ           |     223 |         13 |               5.83 |
| CA           |    1324 |         77 |               5.82 |
| NC           |     292 |         17 |               5.82 |
| PA           |     299 |         17 |               5.69 |
| WA           |     200 |         11 |               5.5  |
| TX           |     900 |         49 |               5.44 |
| NY           |     767 |         38 |               4.95 |

## Loss concentration

Which grades carry the losses, and what share of the book would be given up by declining them outright.

| grade   |   loans |   defaults |   credit_loss_thousands |   share_of_losses_pct |   cumulative_from_worst_pct |   cumulative_share_of_book_pct |
|:--------|--------:|-----------:|------------------------:|----------------------:|----------------------------:|-------------------------------:|
| A       |    1945 |         17 |                     182 |                   3.3 |                       100   |                          100   |
| B       |    2954 |         74 |                     658 |                  11.9 |                        96.7 |                           80.3 |
| C       |    2657 |        148 |                    1395 |                  25.2 |                        84.8 |                           50.3 |
| D       |    1240 |        118 |                    1270 |                  22.9 |                        59.6 |                           23.3 |
| E       |     720 |         90 |                    1182 |                  21.4 |                        36.7 |                           10.8 |
| F       |     266 |         49 |                     598 |                  10.8 |                        15.3 |                            3.5 |
| G       |      75 |         21 |                     251 |                   4.5 |                         4.5 |                            0.8 |
