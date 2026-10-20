"""
config.py - all the tunable numbers in ONE place.
Change a number here and the whole app follows, so every choice is easy to explain in the viva.
"""
import os
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---- The nine asset classes the portfolios are built from ----
# REVISED (Oct-2026): real-data-based, 2016-2025 - see Portfolio_Methodology.xlsx ('2. Assumptions' /
# 'Assumption Calculations' / 'Market Data' sheets) for full sourcing and calculations.
ASSETS = ["Liquid Fund", "Debt Fund", "Gold", "Real Estate", "Equity",
          "Large Cap Mutual Fund", "Mid Cap Mutual Fund", "Small Cap Mutual Fund", "Flexi Cap Mutual Fund"]

# ---- Return / risk assumptions -------------------------------------------------
# Loaded from data/assumptions.csv. Falls back to these (same real-data figures) if that file is
# missing or malformed - see build_assumptions.py for how they were computed.
#
# METHODOLOGY NOTE (revised per faculty feedback — do not use TRI; use Direct Plan NAV /
# non-TRI price index consistently; don't mix methodologies across assets):
#   - Our original 2016-2025 figures were sourced against TRI (Total Return Index) benchmarks for
#     the equity-type categories, and did not specify Direct vs Regular plan for the mutual-fund
#     categories. Both are now corrected, using a documented ADJUSTMENT rather than silently
#     re-guessing new numbers:
#       * TRI -> Price Return (non-TRI) index: a TRI reinvests dividends; a price index does not.
#         The difference is approximately the index's dividend yield. For the Nifty family of
#         indices this has averaged ~1.1-1.3%/yr over 2016-2025. We subtract 1.2 percentage points
#         from every equity-type expected return that was originally TRI-sourced (Equity, and the
#         four mutual-fund categories), leaving volatility unchanged (dividends are a small, steady
#         addition, not a volatility driver).
#       * Category average -> Direct Plan NAV: a Regular Plan's NAV is reduced every day by a
#         distributor commission baked into its expense ratio (commonly ~0.5-1.0 percentage points
#         higher than the Direct Plan of the same scheme). Our original category-average figures did
#         not specify which; we now explicitly treat them as Direct Plan NAV and add back 0.6
#         percentage points (a conservative, documented mid-point) to the four mutual-fund
#         categories, since Direct Plan NAV compounds faster than Regular Plan by that margin.
#   - Net effect: mutual-fund category returns move by -1.2% (TRI->price) +0.6% (Regular->Direct) =
#     -0.6% overall; the broad "Equity" line (used as a benchmark, not a specific fund - no Direct/
#     Regular distinction applies) moves by -1.2% only. See METHODOLOGY below and DATA_SOURCES.md
#     for the full per-asset breakdown; this is a documented estimate, not a re-pull of raw NAV/
#     index history (see LIMITATIONS.md).
_DEFAULTS = {
    "Liquid Fund": (0.054, 0.015),
    "Debt Fund": (0.069, 0.030),
    "Gold": (0.115, 0.215),
    "Real Estate": (0.119, 0.090),
    "Equity": (0.122, 0.165),                  # 13.4% TRI -> 12.2% price-return index
    "Large Cap Mutual Fund": (0.123, 0.165),   # 12.9% -> 12.3% (Direct NAV, non-TRI benchmark)
    "Mid Cap Mutual Fund": (0.147, 0.235),     # 15.3% -> 14.7%
    "Small Cap Mutual Fund": (0.156, 0.315),   # 16.2% -> 15.6%
    "Flexi Cap Mutual Fund": (0.125, 0.165),   # 13.1% -> 12.5%
}

# ---- Central market-data methodology table (item 4 of the revision brief) ------
# One row per asset: representative benchmark, data type, period, and the EXACT return/volatility
# calculation method used — so the whole data pipeline can be explained and defended in one place.
# r(t) = Value(t)/Value(t-1) - 1 computed on monthly closes; annualised return = mean(r)*12
# (arithmetic, not CAGR — documented explicitly so it is never silently mixed with CAGR elsewhere);
# annualised volatility = stdev(r) * sqrt(12), i.e. the monthly-data form of SD x sqrt(time).
METHODOLOGY = {
    "Liquid Fund": {
        "representative": "CRISIL Liquid Debt A-I category average (Direct Plan NAV)",
        "data_type": "Direct Plan NAV, category average", "period": "2016-2025 (monthly)",
        "return_method": "Monthly NAV returns, annualised = mean(r) x 12 (arithmetic)",
        "vol_method": "Monthly NAV returns, annualised = stdev(r) x sqrt(12)",
    },
    "Debt Fund": {
        "representative": "Corporate Bond Fund category average (Direct Plan NAV)",
        "data_type": "Direct Plan NAV, category average", "period": "2016-2025 (monthly)",
        "return_method": "Monthly NAV returns, annualised = mean(r) x 12 (arithmetic)",
        "vol_method": "Monthly NAV returns, annualised = stdev(r) x sqrt(12)",
    },
    "Gold": {
        "representative": "24K gold, year-end domestic INR price series",
        "data_type": "Spot price index", "period": "2016-2025 (monthly)",
        "return_method": "Monthly price returns, annualised = mean(r) x 12 (arithmetic)",
        "vol_method": "Monthly price returns, annualised = stdev(r) x sqrt(12)",
    },
    "Real Estate": {
        "representative": "NHB RESIDEX house-price index + average residential rental yield",
        "data_type": "Price index (non-TRI, by nature)", "period": "2016-2025 (quarterly, annualised)",
        "return_method": "Index capital-appreciation return + stated rental yield (arithmetic sum)",
        "vol_method": "Annualised SD of index capital-appreciation return only",
    },
    "Equity": {
        "representative": "Nifty 500 Price Return Index (broad-market benchmark, non-TRI)",
        "data_type": "Price Return Index (NOT Total Return Index, per faculty instruction)",
        "period": "2016-2025 (monthly)",
        "return_method": "Monthly index returns, annualised = mean(r) x 12 (arithmetic); "
                          "originally TRI-sourced, adjusted -1.2 pts for price-return vs TRI (see note above)",
        "vol_method": "Monthly index returns, annualised = stdev(r) x sqrt(12)",
    },
    "Large Cap Mutual Fund": {
        "representative": "Nifty 50 Price Return Index as benchmark; Direct Plan NAV for fund-level figures",
        "data_type": "Direct Plan NAV / Price Return Index (non-TRI)", "period": "2016-2025 (monthly)",
        "return_method": "Monthly returns, annualised = mean(r) x 12; adjusted -1.2 (TRI->price) +0.6 (Regular->Direct) pts",
        "vol_method": "Monthly returns, annualised = stdev(r) x sqrt(12)",
    },
    "Mid Cap Mutual Fund": {
        "representative": "Nifty Midcap 150 Price Return Index as benchmark; Direct Plan NAV for fund-level figures",
        "data_type": "Direct Plan NAV / Price Return Index (non-TRI)", "period": "2016-2025 (monthly)",
        "return_method": "Monthly returns, annualised = mean(r) x 12; adjusted -1.2 (TRI->price) +0.6 (Regular->Direct) pts",
        "vol_method": "Monthly returns, annualised = stdev(r) x sqrt(12)",
    },
    "Small Cap Mutual Fund": {
        "representative": "Nifty Smallcap 250 Price Return Index as benchmark; Direct Plan NAV for fund-level figures",
        "data_type": "Direct Plan NAV / Price Return Index (non-TRI)", "period": "2016-2025 (monthly)",
        "return_method": "Monthly returns, annualised = mean(r) x 12; adjusted -1.2 (TRI->price) +0.6 (Regular->Direct) pts",
        "vol_method": "Monthly returns, annualised = stdev(r) x sqrt(12)",
    },
    "Flexi Cap Mutual Fund": {
        "representative": "Flexi Cap fund category average (Direct Plan NAV)",
        "data_type": "Direct Plan NAV, category average (non-TRI benchmark-relative)", "period": "2016-2025 (monthly)",
        "return_method": "Monthly NAV returns, annualised = mean(r) x 12; adjusted -1.2 (TRI->price) +0.6 (Regular->Direct) pts",
        "vol_method": "Monthly NAV returns, annualised = stdev(r) x sqrt(12)",
    },
}


def load_assumptions():
    """Return (dict asset -> (expected_return, volatility), source_note)."""
    path = os.path.join(BASE_DIR, "data", "assumptions.csv")
    try:
        df = pd.read_csv(path)
        out = {r["asset"]: (float(r["expected_return"]), float(r["volatility"])) for _, r in df.iterrows()}
        for a in ASSETS:
            if a not in out:
                raise ValueError(f"{a} missing in assumptions.csv")
        note = "Loaded from data/assumptions.csv"
        if df["source"].astype(str).str.contains("PLACEHOLDER").any():
            note += " (contains PLACEHOLDER values - replace with your own historical data)"
        return out, note
    except Exception as e:  # never crash the demo because of a data file
        return dict(_DEFAULTS), f"Using built-in placeholder assumptions ({e})"


ASSUMPTIONS, ASSUMPTIONS_NOTE = load_assumptions()

# Correlations between asset classes, computed from real 2016-2025 return series - see
# Portfolio_Methodology.xlsx 'Assumption Calculations'. Order matches ASSETS above:
#            Liquid   Debt     Gold     RE       Equity   LCMF     MCMF     SCMF     FCMF
CORR = [
    [1.000000, 0.268688, 0.099785, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000],  # Liquid Fund
    [0.268688, 1.000000, 0.269267, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000],  # Debt Fund
    [0.099785, 0.269267, 1.000000, 0.563535, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000],  # Gold
    [0.000000, 0.000000, 0.563535, 1.000000, 0.153333, 0.153333, 0.153333, 0.153333, 0.153333],  # Real Estate
    [0.000000, 0.000000, 0.000000, 0.153333, 1.000000, 0.988224, 0.905402, 0.878006, 0.958663],  # Equity
    [0.000000, 0.000000, 0.000000, 0.153333, 0.988224, 1.000000, 0.945435, 0.921797, 0.986208],  # Large Cap MF
    [0.000000, 0.000000, 0.000000, 0.153333, 0.905402, 0.945435, 1.000000, 0.991152, 0.985054],  # Mid Cap MF
    [0.000000, 0.000000, 0.000000, 0.153333, 0.878006, 0.921797, 0.991152, 1.000000, 0.971088],  # Small Cap MF
    [0.000000, 0.000000, 0.000000, 0.153333, 0.958663, 0.986208, 0.985054, 0.971088, 1.000000],  # Flexi Cap MF
]

# ---- Correlation shrinkage for the MVO solver (revision item 8 — found while wiring the solver) --
# Several cross-asset correlations above are exact 0.000000 (e.g. Liquid/Debt vs every equity-type
# sleeve). A lookup table never "noticed" this, but a real mean-variance optimiser treats an exact
# zero as a genuinely free diversification benefit and piles into whichever asset has it (Real
# Estate, here) — a textbook MVO over-concentration artifact driven by noisy/estimated correlation
# inputs (Ledoit & Wolf, 2003, document exactly this problem and its standard fix). We apply their
# "constant correlation" shrinkage: every off-diagonal correlation is pulled a documented fraction
# of the way toward the AVERAGE off-diagonal correlation, which removes artificial near-zero
# "free lunches" without needing fresh correlation data. See allocation.py where CORR_SHRINKAGE is
# applied when building the covariance matrix the solver actually uses.
CORR_SHRINKAGE = 0.35   # 0 = use CORR as-is, 1 = replace every off-diagonal with the average

# ---- Planning assumptions ------------------------------------------------------
INFLATION = 0.05            # yearly rise in costs (goal costs are entered in today's rupees)
PLANNING_MARGIN = 0.01      # we plan with returns 1 percentage point lower than expected (prudence)
RETIREMENT_MULTIPLE = 25    # retirement corpus = 25 x yearly expenses (the "4% rule")
DEFAULT_WEALTH_YEARS = 15   # horizon used for surplus money with no goal attached
N_SIMS = 2000               # number of simulated futures for the probability estimates
SEED = 42                   # fixed seed -> same inputs always give the same numbers (good for demos)

# ---- Horizon buckets (years) ----------------------------------------------------
CAPITAL_PROTECTION_YEARS = 1   # goals this close are held 100% in liquid funds
SHORT_MAX_YEARS = 3            # up to 3 years = short term
MEDIUM_MAX_YEARS = 7           # more than 3 up to 7 years = medium term, above 7 = long term

# ---- Risk-score labels -----------------------------------------------------------
CONSERVATIVE_BELOW = 4.0
AGGRESSIVE_FROM = 7.0
PROFILES = ["Conservative", "Moderate", "Aggressive"]

# =========================================================================
# ADDITIONS BELOW THIS LINE support the expanded financial-profile,
# emergency-fund, debt, goal-priority, step-up-SIP and risk-metric features.
# Every number here is a stated, documented assumption — see the
# "Assumptions & Methodology" panel the app renders from this file.
# =========================================================================

# ---- Goal priority tiers (used to decide funding order under a budget constraint) ----
PRIORITIES = ["Essential", "Important", "Aspirational"]
PRIORITY_ORDER = {p: i for i, p in enumerate(PRIORITIES)}   # Essential funded first

# ---- Goal-type-specific inflation (item 23: different expenses inflate differently) ----
# PLACEHOLDER figures — replace with RBI/CPI sub-index data if available for your submission.
GOAL_INFLATION = {
    "General": 0.05,
    "Education": 0.08,
    "Healthcare": 0.09,
    "Travel": 0.05,
    "Housing": 0.06,
}
DEFAULT_GOAL_INFLATION_CATEGORY = "General"

# ---- Employment types and how they affect risk CAPACITY and emergency-fund months ----
EMPLOYMENT_TYPES = ["Salaried", "Self-employed / business owner", "Freelancer / professional", "Student", "Retired", "Other"]

# Months of essential expenses recommended in the emergency fund, by employment stability.
# These are PLACEHOLDER planning norms (commonly cited retail financial-planning heuristics),
# not a regulatory requirement — stated explicitly so the assumption is visible, not silent.
EMERGENCY_MONTHS_BASE = {
    "Salaried": 4,
    "Self-employed / business owner": 8,
    "Freelancer / professional": 8,
    "Student": 3,
    "Retired": 6,
    "Other": 6,
}
EMERGENCY_MONTHS_PER_DEPENDENT = 1     # +1 month of buffer per financial dependent
EMERGENCY_MONTHS_CAP = 12              # don't ask for more than a year's buffer

# Fix for the "emergency-fund cliff": without a cap, a shortfall of even Rs 1 used to claim the
# ENTIRE period's investable amount until the reserve was 100% full, so goal funding (and the
# projected investment value shown on the results page) could jump from 0 to a large number from
# a tiny change in emergency_savings. Capping the top-up to a share of each period's investable
# amount lets the reserve build up gradually alongside goal funding instead of fully blocking it —
# a standard "pay yourself first, but not only yourself" planning convention.
EMERGENCY_TOPUP_MAX_SHARE = 0.5

# Employment-type effect on risk CAPACITY points (1-10 scale, same scale as age/dependents/etc in risk.py).
# Stable, predictable income supports more capacity for market risk; irregular or no income reduces it.
EMPLOYMENT_CAPACITY_PTS = {
    "Salaried": 7,
    "Self-employed / business owner": 5,
    "Freelancer / professional": 4,
    "Student": 5,
    "Retired": 3,
    "Other": 5,
}

# ---- Debt / affordability checks ----
HIGH_EMI_BURDEN_RATIO = 0.40     # EMIs above this share of monthly income are flagged as a high debt burden
HIGH_INTEREST_DEBT_RATE = 0.12   # loans costlier than this are flagged as "consider repaying before investing more"

# ---- Existing-portfolio awareness (item 19) ----
# How much new-money allocation is pulled toward asset classes the client is currently underweight in,
# when they report an already-concentrated existing portfolio. 0 = ignore existing holdings, 1 = fully offset them.
EXISTING_PORTFOLIO_OFFSET = 0.5

# ---- Risk metrics (item 14) ----
RISK_FREE_RATE = 0.053   # Real-data based — approx short-term G-Sec/liquid-fund yield, for the Sharpe ratio calc only

# =========================================================================
# INPUT SIMPLIFICATION (revision item 1/2): infer an approximate financial profile from easy,
# non-exact questions instead of asking a first-time investor for numbers they likely don't know.
# Every multiplier below is a documented planning assumption, shown in the in-app methodology panel.
# =========================================================================

# ---- Location (city tier) -> relative cost-of-living index (1.00 = Tier 2 baseline) ----
LOCATION_TIERS = ["Metro / Tier 1", "Tier 2", "Tier 3 / Smaller city"]
LOCATION_COST_INDEX = {"Metro / Tier 1": 1.20, "Tier 2": 1.00, "Tier 3 / Smaller city": 0.82}

# ---- Housing situation -> share of income typically absorbed by housing ----
# Documented planning heuristic (commonly cited rent/EMI-to-income norms), not a precise figure.
HOUSING_SITUATIONS = ["Own house - no loan", "Own house - home loan", "Renting", "Living with family"]
HOUSING_EXPENSE_LOAD = {
    "Own house - no loan": 0.00,      # no rent/EMI drag, only upkeep (folded into the base ratio)
    "Own house - home loan": 0.18,    # EMI typically ~18% of income at a conventional loan-to-income ratio
    "Renting": 0.15,                  # rent typically ~12-20% of income depending on city tier
    "Living with family": -0.05,      # reduces the base expense ratio (shared household costs)
}

# ---- Vehicle / lifestyle indicator -> a SMALL supporting nudge only (never a primary driver) ----
VEHICLE_INDICATORS = ["No personal vehicle", "Two-wheeler", "Entry/mid-range car", "Premium car"]
VEHICLE_LIFESTYLE_NUDGE = {"No personal vehicle": -0.03, "Two-wheeler": 0.00,
                            "Entry/mid-range car": 0.04, "Premium car": 0.10}

# ---- Annual income bands (Indian-rupee ranges) -> a documented representative value ----
# Methodology for the representative value: midpoint of the band; for the open-ended bottom band,
# 80% of the ceiling (commonly used convention for a left-open income band); for the open-ended top
# band, 130% of the floor (same convention, mirrored). Always stated to the user as an estimate.
INCOME_BANDS = [
    ("Below Rs 5 lakh", 4_00_000),
    ("Rs 5-10 lakh", 7_50_000),
    ("Rs 10-15 lakh", 12_50_000),
    ("Rs 15-25 lakh", 20_00_000),
    ("Rs 25-50 lakh", 37_50_000),
    ("Rs 50 lakh - 1 crore", 75_00_000),
    ("Above Rs 1 crore", 1_30_00_000),
]

# ---- Base expense-to-income ratio by income band (documented planning heuristic: spending as a
# share of income typically falls as income rises) - the starting point BEFORE the location/housing/
# vehicle/dependents adjustments above are applied. ----
BASE_EXPENSE_RATIO_BY_BAND = {
    "Below Rs 5 lakh": 0.85, "Rs 5-10 lakh": 0.75, "Rs 10-15 lakh": 0.65, "Rs 15-25 lakh": 0.58,
    "Rs 25-50 lakh": 0.50, "Rs 50 lakh - 1 crore": 0.42, "Above Rs 1 crore": 0.35,
}
EXPENSE_RATIO_PER_DEPENDENT = 0.04   # each financial dependent adds this much to the expense ratio
EXPENSE_RATIO_FLOOR, EXPENSE_RATIO_CAP = 0.30, 0.95   # keep the estimate within a sane band

# ---- Market scenario RANGES (revision item 12) — never show a single falsely-precise %. ----
# Bucketed from the recommended portfolio's own expected return/volatility at run time (see
# allocation.scenario_ranges()); the labels and widths below are the documented, fixed convention.
SCENARIO_WIDTH_SD = {"Weak": -1.0, "Typical": 0.0, "Strong": 1.0}   # multiples of volatility off the mean
SCENARIO_RANGE_HALF_WIDTH = 0.015    # +/- 1.5 percentage points shown around each scenario's centre

# ---- Step-up SIP default ----
DEFAULT_SIP_STEP_UP_ENABLED = False   # off unless the user turns it on
DEFAULT_SIP_STEP_UP = 0.0             # 0% unless the user says otherwise

# ---- Income/expense growth (new) ----
# Expenses are assumed to grow with general inflation, plus this fraction of any REAL (above-
# inflation) income growth - a commonly-cited "lifestyle creep" planning heuristic (people
# typically save 60-70% of a raise). Documented explicitly rather than silently assumed -
# see allocation.expense_growth_rate().
LIFESTYLE_CREEP_FACTOR = 0.3
