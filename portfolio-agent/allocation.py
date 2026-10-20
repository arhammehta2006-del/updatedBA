"""
allocation.py - the calculation engine (plain Python + numpy, NO AI).
Steps:  goals -> emergency-fund top-up -> per-goal allocation -> funding split (by priority) ->
        3 portfolio options (existing-portfolio-aware) -> simulated outcomes -> financial health.
The AI layer only ever explains numbers produced here.
"""
from functools import lru_cache
import numpy as np
from scipy.optimize import minimize
import config as C
import risk as R

# Index positions of the "growth" (equity-type) sleeves within C.ASSETS - Equity + the 4 mutual-fund
# categories. Real Estate (index 3) is its own diversifier, not counted as equity.
EQUITY_IDX = [4, 5, 6, 7, 8]

# ---- Mean-Variance Optimisation (MVO) solver — revision item 7/8 -----------------------------
# The numerical portfolio must come from an explicit, deterministic optimiser, not a hand-set
# lookup table and never from the GenAI layer. We solve, for each (horizon bucket, risk profile):
#     maximise   w'mu - 0.5 * lambda * w'Sigma*w      (mean-variance utility, Markowitz 1952)
#     subject to sum(w) = 1, w_i >= 0 for all i (no short selling),
#                sum of equity-type weights <= a horizon-based cap (capital-protection constraint)
# `lambda` (risk aversion) is a documented constant per profile — the SAME mechanism used by every
# profile; a higher lambda simply penalises variance more heavily, which is how "Conservative" vs
# "Aggressive" are actually implemented here (not a separate rule per profile).
RISK_AVERSION = {"Conservative": 9.0, "Moderate": 3.5, "Aggressive": 1.2}
# Maximum SHARE of the portfolio that may sit in equity-type sleeves, by horizon bucket — the
# capital-protection constraint that keeps near-term money safe regardless of what the solver would
# otherwise prefer. Documented, fixed assumption (not fitted), reviewed the same as any other rule.
BUCKET_EQUITY_CAP = {"Short": 0.15, "Medium": 0.55, "Long": 1.0}
# Per-asset maximum weight — a documented constraint against the well-known MVO "estimation-error
# maximisation" artifact (Michaud, 1989): an unconstrained mean-variance solver systematically
# over-weights whichever single asset has the most favourable combination of return and (low)
# correlation to everything else, even when that is largely estimation noise rather than a real
# edge — in this dataset, Real Estate's low correlation to everything else made it dominate the
# unconstrained solution to over 80%, which is not a usable real-world recommendation. Liquid Fund
# and Debt Fund are left uncapped (a genuinely safety-first Conservative profile SHOULD be able to
# concentrate there); every other single asset is capped at this documented ceiling.
# Alternative/illiquid assets (Gold, Real Estate) are capped lower than mainstream equity sleeves —
# a commonly cited retail asset-allocation ceiling, and also a deliberate counter to real-estate
# index data's well-documented "appraisal smoothing" (appraisal-based indices such as NHB RESIDEX
# move more smoothly than true transaction prices, understating volatility and therefore making the
# asset look more attractive to an MVO solver than it would with transaction-based data).
MVO_ASSET_MAX = {"Gold": 0.20, "Real Estate": 0.20}
MVO_ASSET_MAX_DEFAULT = 0.35
_UNCAPPED_ASSETS = {"Liquid Fund", "Debt Fund"}


def _solve_mvo(mu, cov, risk_aversion, equity_cap):
    """Solve the MVO problem above for one (mu, cov, risk_aversion, equity_cap) combination."""
    n = len(mu)

    def neg_utility(w):
        return -(w @ mu - 0.5 * risk_aversion * (w @ cov @ w))

    constraints = [
        {"type": "eq", "fun": lambda w: np.sum(w) - 1.0},
        {"type": "ineq", "fun": lambda w: equity_cap - sum(w[i] for i in EQUITY_IDX)},
    ]
    bounds = [(0.0, 1.0 if a in _UNCAPPED_ASSETS else MVO_ASSET_MAX.get(a, MVO_ASSET_MAX_DEFAULT))
              for a in C.ASSETS]
    w0 = np.full(n, 1.0 / n)
    res = minimize(neg_utility, w0, method="SLSQP", bounds=bounds, constraints=constraints,
                   options={"maxiter": 200, "ftol": 1e-10})
    w = np.clip(res.x, 0.0, None)
    s = w.sum()
    return (w / s) if s > 1e-9 else w0


@lru_cache(maxsize=32)
def _goal_allocation_cached(bucket, profile):
    # _MU/_COV are module-level constants defined further down this file (resolved at call time,
    # which is always after the whole module has finished loading).
    w = _solve_mvo(_MU, _COV, RISK_AVERSION[profile], BUCKET_EQUITY_CAP[bucket])
    return tuple(round(float(x), 6) for x in w)


def goal_allocation(years, profile):
    """
    Weights (fractions, same order as C.ASSETS) for a goal `years` away under a risk profile,
    from the MVO solver above. Cached per (bucket, profile) pair since the solver's answer only
    depends on those two things, not the exact year count within a bucket — this keeps repeated
    calls (one per goal, per Monte Carlo option, every rerun) fast without changing the result.
    """
    if years <= C.CAPITAL_PROTECTION_YEARS:
        return [1.0] + [0.0] * (len(C.ASSETS) - 1)      # goal is very close: 100% Liquid Fund
    return list(_goal_allocation_cached(R.bucket_for(years), profile))


def solver_table(profile):
    """The per-asset rows for the 'How was this portfolio calculated?' transparency panel
    (revision item 8): expected return, volatility, and the solver's own weight, for the LONG
    bucket of a given profile (the bucket with the fewest constraints active, so it best shows
    what the optimiser actually chose)."""
    w = goal_allocation(C.MEDIUM_MAX_YEARS + 1, profile)
    return [{"asset": a, "expected_return": _MU[i], "volatility": _SD[i], "weight": w[i]}
            for i, a in enumerate(C.ASSETS)]


def alloc_dict(weights):
    return {a: float(round(float(w) * 100, 1)) for a, w in zip(C.ASSETS, weights)}


def equity_share(weights):
    return sum(weights[i] for i in EQUITY_IDX) * 100


def tilt_for_existing(weights, existing_equity_share):
    """
    Item 19: don't blindly add more equity if the client's EXISTING holdings are already
    equity-heavy (or the reverse). Shifts new-money equity weight toward/away from debt+liquid,
    proportionally to how far the existing portfolio sits from this mix's own equity target.
    Applied only to the blended overall view (not each goal's own protective allocation), so a
    near-term goal's capital-protection rule is never weakened by this adjustment.
    """
    if existing_equity_share is None:
        return weights
    w = list(weights)
    target_equity = sum(w[i] for i in EQUITY_IDX)
    diff = existing_equity_share - target_equity   # positive = already overweight equity vs. this target
    if abs(diff) < 1e-6 or target_equity <= 0:
        return w
    shift = C.EXISTING_PORTFOLIO_OFFSET * diff * target_equity
    shift = max(-target_equity, min(target_equity, shift))
    for i in EQUITY_IDX:
        w[i] -= shift * (w[i] / target_equity)
    w[1] += shift          # absorb into debt first
    if w[1] < 0:
        w[0] += w[1]        # spill any remainder into liquid
        w[1] = 0.0
    w = [max(0.0, x) for x in w]
    s = sum(w)
    return [x / s for x in w] if s > 0 else w


# ---- Income/expense growth (new) --------------------------------------------------
def expense_growth_rate(income_growth):
    """
    Expenses grow with general inflation, plus a documented 'lifestyle creep' slice of any REAL
    (above-inflation) income growth - a commonly-cited planning heuristic (people typically save
    60-70% of a raise, so config.LIFESTYLE_CREEP_FACTOR of the rest tends to get spent).
    """
    g = income_growth or 0.0
    return C.INFLATION + C.LIFESTYLE_CREEP_FACTOR * max(0.0, g - C.INFLATION)


def project_disposable_income(inp, years):
    """Year-by-year projection of monthly income/expenses/disposable income, `years` years ahead
    (today = year 0). EMI is assumed flat (a fixed loan schedule doesn't grow with income)."""
    income_growth = inp.get("income_growth") or 0.0
    exp_growth = expense_growth_rate(income_growth)
    income0 = inp.get("monthly_income") or 0.0
    expenses0 = inp.get("monthly_expenses") or 0.0
    emi0 = inp.get("emi_total") or 0.0
    n = max(1, round(years or 10))
    rows = []
    for y in range(n + 1):
        income = income0 * (1 + income_growth) ** y
        expenses = expenses0 * (1 + exp_growth) ** y
        rows.append({"year": y, "income": income, "expenses": expenses,
                     "disposable": max(0.0, income - expenses - emi0)})
    return rows


def implied_disposable_growth(inp):
    """Annualised growth rate implied for disposable income over a 10-year window, given the income/
    expense growth assumptions - used only to SUGGEST a SIP step-up %, never to set it automatically."""
    proj = project_disposable_income(inp, 10)
    first, last = proj[0]["disposable"], proj[-1]["disposable"]
    yrs = len(proj) - 1
    if not (first > 0) or not (last > 0) or yrs <= 0:
        return 0.0
    return (last / first) ** (1 / yrs) - 1


def net_worth_projection(inp, plan):
    """Age-by-age projection of TOTAL wealth: existing investments + emergency savings (today) plus
    every rupee invested through this plan, compounding at the recommended portfolio's expected return.
    A single simplified, deterministic growth path (not the per-goal Monte Carlo) - the median story of
    'how does my overall wealth build up', used only for the results-page wealth-over-time chart."""
    snap = plan["snapshot"]
    rec_opt = plan["options"][plan["recommended"]]
    r = rec_opt["exp_return"]
    sip = plan["mode"].startswith("SIP")
    amount = plan["amount"]
    step_up = plan["sip_step_up"] if sip else 0.0

    age0 = int(inp.get("age") or 0)
    goal_years = [g["years"] for g in plan["goals"] if g.get("years")]
    retire_years = (inp["retirement_age"] - inp["age"]) if inp.get("has_retirement") and inp.get("retirement_age", 0) > age0 else 0
    horizon = max([retire_years] + goal_years + [plan["profile"]["weighted_horizon_years"]])
    horizon = int(min(50, max(5, round(horizon))))

    wealth = snap["existing_total"] + snap["emergency_current"] + (0.0 if sip else amount)
    rows = [{"age": age0, "year": 0, "wealth": wealth}]
    for j in range(1, horizon + 1):
        contribution = amount * 12 * ((1 + step_up) ** (j - 1)) if sip else 0.0
        wealth = wealth * (1 + r) + contribution
        rows.append({"age": age0 + j, "year": j, "wealth": wealth})
    return rows


# ---- Portfolio maths ---------------------------------------------------------
_MU = np.array([C.ASSUMPTIONS[a][0] for a in C.ASSETS])
_SD = np.array([C.ASSUMPTIONS[a][1] for a in C.ASSETS])


def _shrunk_correlation(corr, alpha):
    """Ledoit-Wolf 'constant correlation' shrinkage (see config.CORR_SHRINKAGE) — pulls every
    off-diagonal correlation a documented fraction toward the average off-diagonal correlation,
    so the MVO solver below isn't driven by artificial exact-zero correlations."""
    n = corr.shape[0]
    off_diag_mask = ~np.eye(n, dtype=bool)
    avg_corr = corr[off_diag_mask].mean()
    shrunk = (1 - alpha) * corr + alpha * avg_corr
    np.fill_diagonal(shrunk, 1.0)
    return shrunk


_CORR_RAW = np.array(C.CORR)
_CORR = _shrunk_correlation(_CORR_RAW, C.CORR_SHRINKAGE)
_COV = np.outer(_SD, _SD) * _CORR


def portfolio_stats(w):
    """Expected yearly return and volatility (typical ups and downs) of a mix."""
    w = np.array(w, dtype=float)
    return float(w @ _MU), float(np.sqrt(w @ _COV @ w))


def sharpe_ratio(mu, sd):
    """Return per unit of risk, relative to a risk-free rate (config.RISK_FREE_RATE). Item 14."""
    return float((mu - C.RISK_FREE_RATE) / sd) if sd > 1e-9 else 0.0


def scenario_ranges(mu, sd):
    """
    Market scenarios as RANGES, never a falsely-precise single number (revision item 12).
    Centre of each scenario = portfolio mu + (a documented number of SDs) x sd; the displayed
    range is that centre +/- a fixed half-width (config.SCENARIO_RANGE_HALF_WIDTH). The widths
    themselves (-1 SD / 0 SD / +1 SD) are a fixed, stated convention, not fitted to this user.
    """
    out = {}
    for label, k in C.SCENARIO_WIDTH_SD.items():
        centre = mu + k * sd
        lo, hi = centre - C.SCENARIO_RANGE_HALF_WIDTH, centre + C.SCENARIO_RANGE_HALF_WIDTH
        out[label] = {"low": max(-0.5, lo), "high": hi}
    return out


# ---- Combining existing investments with new money (revision item 9) -------------------------
# Categories a user can describe their EXISTING holdings in, mapped onto our 9-asset model. A
# user rarely knows their existing split asset-by-asset, so we use a small, recognisable set of
# buckets and map each one onto the single closest asset class in C.ASSETS (documented, simplified
# mapping — see DATA_SOURCES.md) rather than pretending to know a finer split that was never asked.
EXISTING_CATEGORIES = ["Liquid / Cash", "Debt / Fixed Income", "Gold", "Real Estate", "Equity / Mutual Funds"]
_EXISTING_CATEGORY_TO_ASSET_IDX = {
    "Liquid / Cash": 0, "Debt / Fixed Income": 1, "Gold": 2, "Real Estate": 3, "Equity / Mutual Funds": 4,
}


def existing_mix_vector(existing_by_category):
    """existing_by_category: {category name -> rupee value}. Returns (total_value, weights vector)
    in C.ASSETS order, or (0.0, None) if nothing was entered."""
    n = len(C.ASSETS)
    v = np.zeros(n)
    for cat, amt in (existing_by_category or {}).items():
        idx = _EXISTING_CATEGORY_TO_ASSET_IDX.get(cat)
        if idx is not None and amt:
            v[idx] += float(amt)
    total = float(v.sum())
    return total, (v / total if total > 0 else None)


def combined_portfolio(existing_by_category, new_amount, target_weights):
    """
    Revision item 9: do not optimise new money in isolation. Given what the user already holds
    and a TARGET mix (the MVO solver's recommended weights), work out how the NEW money should be
    allocated so the resulting COMBINED portfolio (existing + new) moves toward that target -
    rather than simply handing back the target mix as if no prior investments existed.

    Solved as: minimise sum_i ((existing_i + new_i)/(existing_total+new_amount) - target_i)^2
               subject to sum(new_i) = new_amount, new_i >= 0
    i.e. the smallest possible move away from the target mix for the COMBINED book, spending
    exactly the new money and never "selling" any existing holding to get there.
    Returns a dict with current_mix, target_mix, new_money_alloc, combined_mix (all as % weights,
    alloc_dict-shaped) plus the raw existing_total/combined_total rupee figures.
    """
    n = len(C.ASSETS)
    existing_total, current_w = existing_mix_vector(existing_by_category)
    target = np.array(target_weights, dtype=float)
    combined_total = existing_total + max(0.0, new_amount)

    if new_amount <= 0:
        new_w = np.zeros(n)
    elif existing_total <= 0:
        new_w = target.copy()                      # nothing existing: new money = the target mix itself
    else:
        existing_v = (current_w if current_w is not None else np.zeros(n)) * existing_total

        def obj(x):
            combined = (existing_v + x) / combined_total
            return float(np.sum((combined - target) ** 2))

        cons = [{"type": "eq", "fun": lambda x: np.sum(x) - new_amount}]
        bounds = [(0.0, new_amount)] * n
        res = minimize(obj, np.full(n, new_amount / n), method="SLSQP", bounds=bounds,
                       constraints=cons, options={"maxiter": 200, "ftol": 1e-12})
        new_w = np.clip(res.x, 0.0, None)
        s = new_w.sum()
        new_w = new_w * (new_amount / s) if s > 1e-9 else new_w

    existing_v = (current_w if current_w is not None else np.zeros(n)) * existing_total
    combined_v = existing_v + new_w
    combined_w = combined_v / combined_total if combined_total > 0 else combined_v

    return {
        "existing_total": existing_total, "new_amount": max(0.0, new_amount), "combined_total": combined_total,
        "current_mix": alloc_dict(current_w) if current_w is not None else None,
        "target_mix": alloc_dict(target),
        "new_money_alloc": alloc_dict(new_w / new_amount) if new_amount > 0 else None,
        "new_money_alloc_rupees": {a: float(round(x, 0)) for a, x in zip(C.ASSETS, new_w)},
        "combined_mix": alloc_dict(combined_w),
    }


def planning_return(w):
    """Prudent return used to size the required saving: expected - volatility drag - safety margin."""
    mu, sd = portfolio_stats(w)
    return max(0.0, mu - 0.5 * sd ** 2 - C.PLANNING_MARGIN)


def _sip_future_value(c0, months, rm, step_up):
    """Explicit month-by-month future value of a SIP whose contribution grows `step_up` each year."""
    v = 0.0
    for t in range(months):
        year_idx = t // 12
        v += c0 * (1 + step_up) ** year_idx
        v *= (1 + rm)
    return v


def required_funding(target, years, g, sip, step_up=0.0):
    """Monthly SIP (first month's amount, if step_up>0) or lumpsum today needed to reach `target`."""
    if sip:
        months = max(1, round(years * 12))
        rm = (1 + g) ** (1 / 12) - 1
        if step_up <= 1e-9:
            return target / months if rm < 1e-9 else target * rm / ((1 + rm) ** months - 1)
        lo, hi = 0.0, max(target, 1.0)
        for _ in range(60):      # binary search: ~60 iterations is far more precision than needed
            mid = (lo + hi) / 2
            fv = _sip_future_value(mid, months, rm, step_up)
            if fv < target:
                lo = mid
            else:
                hi = mid
        return hi
    return target / (1 + g) ** years


def required_return(amount, target, years, sip, step_up=0.0):
    """
    Inverse of required_funding: given a fixed amount/SIP, what annual return would be needed to
    reach `target` in `years`? Used for the 'Required Risk' angle (item 18) — a single, documented
    simplification using the client's money-weighted horizon rather than solving goal-by-goal,
    so it never needs the funding split (which itself depends on a chosen profile).
    """
    if amount <= 0 or target <= 0 or years <= 0:
        return 0.0
    lo, hi = -0.5, 0.5
    for _ in range(60):
        mid = (lo + hi) / 2
        rm = (1 + mid) ** (1 / 12) - 1 if sip else None
        fv = _sip_future_value(amount, max(1, round(years * 12)), rm, step_up) if sip else amount * (1 + mid) ** years
        if fv < target:
            lo = mid
        else:
            hi = mid
    return hi


def simulate(z, mu, sd, funding, sip, target, step_up=0.0):
    """
    Monte Carlo: run many possible futures. z is a (months x sims) array of standard normal shocks,
    re-used across options so the three portfolios are compared on the SAME simulated markets.
    """
    n, sims = z.shape
    if funding <= 0:
        return {"median": 0.0, "p10": 0.0, "p90": 0.0, "prob": 0.0 if target else None,
                "median_pct": 0.0 if target else None}
    v = np.zeros(sims) if sip else np.full(sims, float(funding))
    mm, sm = mu / 12, sd / np.sqrt(12)
    for t in range(n):
        if sip:
            year_idx = t // 12
            v = v + funding * (1 + step_up) ** year_idx
        v = v * (1 + np.maximum(mm + sm * z[t], -0.95))
    return {
        "median": float(np.median(v)), "p10": float(np.percentile(v, 10)), "p90": float(np.percentile(v, 90)),
        "prob": float((v >= target).mean()) if target else None,
        "median_pct": float(np.median(v) / target) if target else None,   # typical outcome as share of the target
    }


# ---- Financial health scorecard (item 39) ----------------------------------------
def financial_health(inp, snap, goals):
    """Labelled scorecard. Any input the user skipped comes back as 'Not assessed', never guessed."""
    card = {}

    if snap["emergency_target"] <= 0:
        card["Emergency Fund"] = "Not assessed"
    elif snap["emergency_shortfall"] <= 0:
        card["Emergency Fund"] = "Good"
    elif snap["emergency_current"] / snap["emergency_target"] >= 0.5:
        card["Emergency Fund"] = "Needs Attention"
    else:
        card["Emergency Fund"] = "At Risk"

    if snap["emi_ratio"] is None:
        card["Debt Level"] = "Not assessed"
    elif snap["high_emi_burden"]:
        card["Debt Level"] = "Needs Attention"
    else:
        card["Debt Level"] = "Healthy"

    if snap["savings_rate"] is None:
        card["Savings Rate"] = "Not assessed"
    elif snap["savings_rate"] >= 0.3:
        card["Savings Rate"] = "Strong"
    elif snap["savings_rate"] >= 0.15:
        card["Savings Rate"] = "Good"
    else:
        card["Savings Rate"] = "Needs Attention"

    ret = next((g for g in goals if g["kind"] == "retirement"), None)
    if ret is None:
        card["Retirement Planning"] = "Not assessed"
    elif ret.get("funded_ratio") is None:
        card["Retirement Planning"] = "On Track"
    elif ret["funded_ratio"] >= 0.95:
        card["Retirement Planning"] = "On Track"
    elif ret["funded_ratio"] >= 0.7:
        card["Retirement Planning"] = "Behind Target"
    else:
        card["Retirement Planning"] = "Significantly Behind"

    needs_life_cover = inp.get("dependents", 0) > 0 and snap["sole_earner"] and not snap["has_life_insurance"]
    if not snap["has_health_insurance"] or needs_life_cover:
        card["Insurance Protection"] = "Needs Review"
    else:
        card["Insurance Protection"] = "Good"

    return card


# ---- The full plan ---------------------------------------------------------------
def build_plan(inp, override=None, amount_mult=1.0):
    """
    inp: validated inputs dict. override: force a risk profile (what-if). amount_mult: scale the money (what-if).
    Returns one big dict that both the UI and the AI layer read from.
    """
    sip = inp["mode"].startswith("SIP")
    step_up = float(inp.get("sip_step_up") or 0.0) if sip and inp.get("sip_step_up_enabled") else 0.0
    goals = R.build_goals(inp)
    prof = R.risk_profile(inp, goals)
    rec = override or prof["label"]
    amount = inp["amount"] * amount_mult
    snap = R.financial_snapshot(inp)

    # 1) plan returns from the RECOMMENDED profile's allocation for each goal
    for g in goals:
        w = goal_allocation(g["years"], rec)
        g["plan_return"] = planning_return(w)

    # 2) emergency-fund top-up comes out of the investable amount FIRST (item 3) — it is tracked
    #    separately from the goals list so the existing per-goal simulation loop below is untouched.
    avail = amount
    topup_needed = snap["emergency_shortfall"]
    # Capped at a share of this period's investable amount (not the whole amount) so building the
    # reserve never fully blocks goal funding — see EMERGENCY_TOPUP_MAX_SHARE in config.py.
    topup = min(topup_needed, avail * C.EMERGENCY_TOPUP_MAX_SHARE) if topup_needed > 0 else 0.0
    avail -= topup
    emergency_topup = {
        "required": topup_needed, "funding": topup,
        "funded_ratio": (topup / topup_needed) if topup_needed > 0 else 1.0,
    }

    # 3) split the remaining money: fund goals by PRIORITY first, then nearest goal within a tier (item 11)
    avail_after_emergency = avail
    targeted = [x for x in goals if x["target"] is not None]
    targeted.sort(key=lambda x: (C.PRIORITY_ORDER.get(x.get("priority", "Important"), 1), x["years"]))
    for g in targeted:
        g["required"] = required_funding(g["target"], g["years"], g["plan_return"], sip, step_up)
        g["funding"] = min(g["required"], avail)
        g["funded_ratio"] = g["funding"] / g["required"] if g["required"] > 0 else 1.0
        avail -= g["funding"]
    for g in goals:
        if g["target"] is None:
            g.update(required=None, funding=0.0, funded_ratio=None)

    # 4) anything left over goes to open-ended goals, or to an automatic wealth-building bucket
    surplus = max(avail, 0.0)
    if surplus > 0.5:
        open_goals = [g for g in goals if g["target"] is None]
        if open_goals:
            for g in open_goals:
                g["funding"] += surplus / len(open_goals)
        else:
            longest = max([g["years"] for g in goals], default=0)
            yrs = longest if longest >= C.MEDIUM_MAX_YEARS else float(C.DEFAULT_WEALTH_YEARS)
            goals.append({"name": "Long-term wealth building (surplus)", "years": yrs, "kind": "wealth",
                          "today_value": None, "target": None, "bucket": R.bucket_for(yrs),
                          "priority": "Aspirational", "inflation_category": "General", "inflation_rate": C.GOAL_INFLATION["General"],
                          "required": None, "funding": surplus, "funded_ratio": None, "plan_return": 0.0})

    # 5) build the three portfolio options and simulate every goal under each
    z_list = []
    for i, g in enumerate(goals):
        rng = np.random.default_rng(C.SEED + i)
        z_list.append(rng.standard_normal((max(1, round(g["years"] * 12)), C.N_SIMS)))

    options = {}
    for name in C.PROFILES:
        rows, agg = [], np.zeros(len(C.ASSETS))
        for g, z in zip(goals, z_list):
            w = goal_allocation(g["years"], name)
            mu, sd = portfolio_stats(w)
            res = simulate(z, mu, sd, g["funding"], sip, g["target"], step_up)
            rows.append({"goal": g["name"], "alloc": alloc_dict(w), "equity_pct": round(equity_share(w), 1),
                         "exp_return": mu, "volatility": sd, **res})
            agg += g["funding"] * np.array(w)
        if agg.sum() > 0:
            overall = agg / agg.sum()
        elif goals:
            overall = np.mean([goal_allocation(g["years"], name) for g in goals], axis=0)
        else:
            overall = np.zeros(len(C.ASSETS))
            overall[EQUITY_IDX[0]] = overall[EQUITY_IDX[1]] = 0.5
        overall = np.array(tilt_for_existing(list(overall), snap["existing_equity_share"]))
        mu, sd = portfolio_stats(overall)
        combined = combined_portfolio(inp.get("existing_by_category"), avail_after_emergency, overall)
        options[name] = {
            "overall_alloc": alloc_dict(overall), "exp_return": mu, "volatility": sd,
            "bad_year": mu - 1.645 * sd,          # roughly a 1-in-20 bad year (kept for internal checks;
            "stress_decline": mu - 2.0 * sd,      # the UI shows the range-based scenarios below instead)
            "scenarios": scenario_ranges(mu, sd),              # revision item 12: ranges, not single numbers
            "sharpe": round(sharpe_ratio(mu, sd), 2),
            "goals": rows,
            "combined": combined,                              # revision item 9: existing + new money
        }

    # 6) required risk (item 18's third angle) — a single, documented simplification: what annual
    #    return would the money-weighted horizon + total investable amount need to hit the
    #    money-weighted total of all dated goals? Compared against the Conservative/Moderate/
    #    Aggressive planning returns at that horizon's bucket to get a label. Shown for awareness;
    #    it does NOT override the willingness/capacity-driven recommendation above.
    weighted_horizon = prof["weighted_horizon_years"]
    total_target = sum(g["target"] for g in goals if g.get("target"))
    req_g = required_return(amount, total_target, weighted_horizon, sip, step_up) if total_target > 0 else 0.0
    bucket_here = R.bucket_for(weighted_horizon)
    cons_pr = planning_return(goal_allocation(weighted_horizon, "Conservative")) if weighted_horizon > C.CAPITAL_PROTECTION_YEARS else 0.0
    mod_pr = planning_return(goal_allocation(weighted_horizon, "Moderate")) if weighted_horizon > C.CAPITAL_PROTECTION_YEARS else 0.0
    aggr_pr = planning_return(goal_allocation(weighted_horizon, "Aggressive")) if weighted_horizon > C.CAPITAL_PROTECTION_YEARS else 0.0
    if total_target <= 0:
        required_label = "Not applicable"
    elif req_g <= cons_pr:
        required_label = "Low"
    elif req_g <= mod_pr:
        required_label = "Moderate"
    elif req_g <= aggr_pr:
        required_label = "Moderate-High"
    else:
        required_label = "High"
    prof["required_risk"] = {"label": required_label, "required_return": req_g, "bucket": bucket_here}

    # 7) plain-English notes about mismatches and gaps (item 16/17/38 — consistency checks)
    notes = []
    if override and override != prof["label"]:
        notes.append(f"You are viewing the {override} portfolio; based on your answers the suggested profile is {prof['label']}.")
    gap = prof["willingness"] - prof["capacity"]
    if gap >= 2.5:
        notes.append(f"You are more comfortable with risk (willingness {prof['willingness']}/10) than your situation "
                     f"can comfortably afford (capacity {prof['capacity']}/10), so your score follows the lower figure.")
    elif gap <= -2.5:
        notes.append(f"Your situation could support more risk (capacity {prof['capacity']}/10) than you are comfortable "
                     f"with (willingness {prof['willingness']}/10), so your score follows your comfort level. "
                     "Long goals usually need some growth, so consider the higher-risk options too.")
    if abs(prof["stated"] - prof["quiz"]) >= 4:
        notes.append("Your stated risk appetite and your answers to the scenario questions point in different directions, "
                     "so we gave more weight to the scenario answers.")
    if required_label in ("Moderate-High", "High") and prof["label"] != "Aggressive":
        notes.append(f"To reach your goals as entered, your money would need to grow at roughly {req_g*100:.1f}% a year "
                      f"(a 'Required Risk' of {required_label}) - higher than your recommended {prof['label']} profile "
                      "targets. Consider a larger amount, a later date, lower targets, or a higher-risk option.")
    if topup > 0:
        notes.append(f"Rs {topup:,.0f} of your investable amount (up to {C.EMERGENCY_TOPUP_MAX_SHARE*100:.0f}% of it) "
                     f"was set aside first to build up your emergency fund (kept 100% liquid); the rest was "
                     f"allocated to your goals so building your reserve doesn't fully pause your investing.")
    if snap["high_interest_debt"]:
        notes.append("You reported some high-interest debt. Its cost likely exceeds typical investment returns, "
                     "so consider repaying it before increasing investments further.")
    for g in goals:
        if g["years"] <= C.CAPITAL_PROTECTION_YEARS:
            notes.append(f"'{g['name']}' is {g['years']:g} year or less away, so it is kept 100% in liquid funds.")
        elif g["bucket"] == "Short" and rec != "Conservative":
            eq = equity_share(goal_allocation(g["years"], rec))
            notes.append(f"'{g['name']}' is only {g['years']:g} years away, so equity is limited to {eq:.0f}% "
                         f"for this goal even though your profile is {rec}.")
        if g["kind"] == "retirement" and g["years"] <= 10 and rec == "Aggressive":
            notes.append(f"Retirement is only {g['years']:g} years away, yet the Aggressive option still carries high "
                         "equity exposure. Consider the Moderate option as retirement gets closer.")
    for g in goals:
        if g.get("funded_ratio") is not None and g["funded_ratio"] < 0.999:
            shortfall_rupees = (g["required"] or 0) - g["funding"]
            notes.append(f"'{g['name']}' is only {g['funded_ratio']*100:.0f}% funded at your current amount "
                         f"(about Rs {shortfall_rupees:,.0f} short per {'month' if sip else 'the plan'}). "
                         "Consider a larger amount, a later date, or a lower target.")
    if snap["existing_equity_share"] is not None and snap["existing_equity_share"] >= 0.75:
        notes.append(f"Your existing investments are already about {snap['existing_equity_share']*100:.0f}% equity, "
                     "so new money has been tilted a little more toward debt/liquid to avoid over-concentration.")

    health = financial_health(inp, snap, goals)
    overall_mix = options[rec]["overall_alloc"]
    distinct_classes = sum(1 for v in overall_mix.values() if v >= 5.0)
    health["Investment Diversification"] = "Low" if distinct_classes <= 2 else "Moderate" if distinct_classes == 3 else "Good"

    # 8) income/expense growth projection (new) - informational: shows how disposable income is
    #    expected to move, and suggests (never forces) a SIP step-up consistent with that projection.
    income_growth = inp.get("income_growth") or 0.0
    expense_growth = expense_growth_rate(income_growth)
    proj_years = min(15, max(5, round(weighted_horizon or 10)))
    disposable_projection = project_disposable_income(inp, proj_years)
    suggested_sip_step_up = round(implied_disposable_growth(inp), 3)

    # Revision item 11: "Total Corpus" was ambiguous. Renamed to "Projected Investment Value" and
    # defined precisely — the sum, across goals, of the simulated outcome from money that actually
    # went INTO the investment portfolio under the recommended option. It explicitly EXCLUDES the
    # emergency reserve (revision item 10) and any unrelated existing assets not entered as
    # "existing investments". Kept under the old key too, unchanged, so nothing else breaks.
    rec_rows = options[rec]["goals"]
    projected_investment_value = {
        "median": sum(r["median"] for r in rec_rows),
        "p10": sum(r["p10"] for r in rec_rows),
        "p90": sum(r["p90"] for r in rec_rows),
        "definition": ("Current investments + future contributions to your goals + estimated growth "
                       "under the recommended portfolio - NOT including your emergency reserve."),
    }
    total_projected = projected_investment_value   # back-compat alias; identical value

    # Revision item 10/11: explicit, separate labels for the two pots of money so neither the UI
    # nor a user can accidentally read one as part of the other.
    emergency_reserve = {
        "target": snap["emergency_target"], "current": snap["emergency_current"],
        "shortfall": snap["emergency_shortfall"], "topup_this_period": topup,
        "note": (f"Kept 100% in liquid instruments. Built gradually - at most "
                 f"{C.EMERGENCY_TOPUP_MAX_SHARE*100:.0f}% of each period's investable amount goes here until "
                 "it's full, so building it never fully stops your goal investing. Never counted as part of "
                 "the investment portfolio, its expected return, or the projected investment value above."),
    }
    investment_portfolio = {
        "amount_invested": avail_after_emergency,
        "note": "Your investable amount, AFTER the emergency-reserve top-up above is set aside.",
    }

    return {
        "mode": "SIP (monthly)" if sip else "Lumpsum", "amount": amount, "surplus": surplus,
        "sip_step_up": step_up,
        "profile": prof, "recommended": rec, "goals": goals, "options": options, "notes": notes,
        "assumptions": {a: {"expected_return": C.ASSUMPTIONS[a][0], "volatility": C.ASSUMPTIONS[a][1]} for a in C.ASSETS},
        "assumptions_note": C.ASSUMPTIONS_NOTE, "methodology": C.METHODOLOGY,
        "inflation": C.INFLATION,
        "income_growth": income_growth, "expense_growth": expense_growth,
        "disposable_projection": disposable_projection, "suggested_sip_step_up": suggested_sip_step_up,
        "total_projected": total_projected, "projected_investment_value": projected_investment_value,
        "emergency_reserve": emergency_reserve, "investment_portfolio": investment_portfolio,
        "snapshot": snap, "emergency_topup": emergency_topup, "financial_health": health,
    }
