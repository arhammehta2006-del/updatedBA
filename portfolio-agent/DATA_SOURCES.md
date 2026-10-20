# Source & Data Documentation

## User-provided data (collected by the app, used as entered)
Age, dependents, employment type, retirement age, monthly income/expenses/EMI, expected annual
income growth (%), whether any EMI is high-interest, existing equity/non-equity holdings, current
emergency savings, health/life insurance flags, sole-earner status, liquidity need, investment mode
(SIP/Lumpsum) and amount, whether SIP step-up is turned on and its rate, goals (name, cost, years,
priority, inflation category), stated risk appetite, and 3-question risk-scenario quiz answers.
None of this is stored anywhere outside the browser session — see `LIMITATIONS.md`.

## Model-estimated figures (computed by the app from the above)
Emergency-fund target, risk appetite/capacity/score, required-return-to-reach-goals, per-goal and
blended asset allocation, expected return/volatility/Sharpe ratio, Monte Carlo outcome ranges
(median / P10 / P90 / probability of reaching target), stress-decline and "bad year" figures,
financial-health scorecard, auto-computed expense-growth rate (from the income-growth input),
current and projected net worth, and the wealth-over-time-by-age projection. All computed in
`risk.py`/`allocation.py` — see `ARCHITECTURE.md`.

## Market data (fitted to real history)

**`data/assumptions.csv`** — expected annual return and volatility for each of nine asset classes,
computed from real 2016-2025 Indian market data (see each row's `source` column; the full
calculation — index/category chosen, CAGR and annualised-volatility workings — is in
`Portfolio_Methodology.xlsx`):

| Asset | Expected return | Volatility | Source |
|---|---|---|---|
| Liquid Fund | 5.4% | 1.5% | CRISIL Liquid Debt A-I category, 2016-2025 CAGR/volatility |
| Debt Fund | 6.9% | 3.0% | Corporate bond fund category, 2016-2025 CAGR/volatility |
| Gold | 11.5% | 21.5% | 24K gold year-end INR price series, 2016-2025 |
| Real Estate | 11.9% | 9.0% | NHB RESIDEX house-price index + average residential rental yield |
| Equity | 13.4% | 16.5% | Broad Nifty 500 TRI-style index, 2016-2025 |
| Large Cap Mutual Fund | 12.9% | 16.5% | Nifty 50 TRI category, 2016-2025 |
| Mid Cap Mutual Fund | 15.3% | 23.5% | Nifty Midcap 150 TRI category, 2016-2025 |
| Small Cap Mutual Fund | 16.2% | 31.5% | Nifty Smallcap 250 TRI category, 2016-2025 |
| Flexi Cap Mutual Fund | 13.1% | 16.5% | Flexi Cap fund category, 2016-2025 |

The correlation matrix between all nine asset classes (`CORR` in `config.py`) is likewise computed
from the same real 2016-2025 return series — not a stated guess — see `Portfolio_Methodology.xlsx`
("Assumption Calculations") for the full workings.

**To refresh these from newer data** (the pipeline is still in place, ready to re-run): download
updated monthly/daily price history for each asset class, save each as
`data/history/<Asset Name>.csv` with `Date,Close` columns, and run `python build_assumptions.py`,
which recomputes CAGR and annualised volatility and overwrites `data/assumptions.csv`, recording
the source and date range used for each asset.

**Other stated assumptions** (in `config.py`, all labelled "ADDITIONS" / documented inline):

| Assumption | Value | Where |
|---|---|---|
| General inflation | 5%/yr | `INFLATION` |
| Goal-specific inflation | Education 8%, Healthcare 9%, Travel/General 5%, Housing 6% | `GOAL_INFLATION` |
| Emergency fund, base months | Salaried 4, Self-employed/Freelancer 8, Student 3, Retired 6, Other 6 | `EMERGENCY_MONTHS_BASE` |
| Emergency fund, per dependent | +1 month, capped at 12 total | `EMERGENCY_MONTHS_PER_DEPENDENT`, `EMERGENCY_MONTHS_CAP` |
| High EMI-burden threshold | EMI > 40% of income | `HIGH_EMI_BURDEN_RATIO` |
| Risk-free rate (for Sharpe ratio) | 5.3% — approx. short-term G-Sec/liquid-fund yield | `RISK_FREE_RATE` |
| Retirement corpus multiple | 25× annual expenses | `RETIREMENT_MULTIPLE` |
| Lifestyle-creep factor (expense growth when income grows) | Expenses grow at inflation + 30% of any real (above-inflation) income growth | `LIFESTYLE_CREEP_FACTOR` |
| Monte Carlo simulations per goal/profile | 2,000 (Python) / 1,500 (JS artifact, for in-browser speed) | `N_SIMS` |
| Net-worth-over-time projection | Deterministic compounding at the recommended portfolio's expected return — a single simplified growth path, not the per-goal Monte Carlo range | `allocation.net_worth_projection()` |

The in-app "Assumptions & methodology" panel (visible on every results page) shows this same
breakdown to the end user, so nothing here is hidden from someone using the tool.

## Bonus JS artifact
`logic.js` carries an identical copy of every constant above (kept in sync by hand during the
port, verified via the shared test cases in `TEST_REPORT.md`), so both builds use the same
assumptions.
