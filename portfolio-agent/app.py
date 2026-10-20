"""
app.py - interactive front-end (Streamlit).
Run with:   streamlit run app.py

Flow:  How it works -> About you -> Financial life -> Money & goals -> Risk comfort -> Review -> Your plan
(plan page follows the Investor Snapshot -> Financial Health -> Risk Profile -> Goals -> Portfolio ->
Why This Fits -> Expected Results -> Risk Analysis -> Alternatives -> Action Plan -> Maintenance order,
with Compare/Goal tracker/What-if/Ask the advisor/Download kept as secondary tabs underneath it.)
"""
import html
import json
import os
import re

import altair as alt
import pandas as pd
import streamlit as st

import advisor as D
import allocation as A
import config as C
import risk as R
from utils import fmt_inr

st.set_page_config(page_title="Goal-Based Portfolio Planner", page_icon="📈", layout="wide")

STEPS = ["How it works", "About you", "Financial life", "Money & goals", "Risk comfort", "Review", "Your plan"]
GOAL_COLS = ["Goal name", "Cost today (Rs)", "Years to go", "Priority", "Inflation category"]
# Classic-finance navy/blue palette. Gold and Real Estate keep their own realistic accent colors
# (brass / brown); the five equity-type sleeves run as a dark-to-light navy-blue ramp so they read
# as one family, graduated by risk (Equity direct = darkest, Flexi Cap = a distinct teal-blue blend).
ASSET_COLORS = ["#AEB8C4", "#4A6FA5", "#C9A227", "#8C6239", "#0E2A43", "#1B4971", "#2E72A4", "#5FA3D0", "#3F8FA3"]
ASSET_SCALE = alt.Scale(domain=C.ASSETS, range=ASSET_COLORS)
DISCLAIMER = ("Educational guidance only, not personalised financial advice. Figures are estimates based on stated "
              "assumptions and are not guaranteed. Please consult a SEBI-registered advisor before investing.")

HEALTH_COLOR = {"Good": "🟢", "Strong": "🟢", "On Track": "🟢", "Healthy": "🟢",
                "Needs Attention": "🟡", "Behind Target": "🟡", "Moderate": "🟡", "Needs Review": "🟡",
                "At Risk": "🔴", "Significantly Behind": "🔴", "Low": "🔴",
                "Not assessed": "⚪"}

CUSTOM_CSS = """
<style>
:root { --accent: #1B4971; --accent-dark: #0E2A43; --accent-soft: #E8EEF5; --line: #D7E1EC; }
.block-container { padding-top: 2rem; max-width: 1100px; }
h1, h2, h3 { letter-spacing: -0.01em; color: var(--accent-dark); }
div[data-testid="stMetricValue"] { font-size: 1.6rem; font-weight: 600; color: var(--accent-dark); }
div[data-testid="stMetric"] {
    background: #F7F9FB; border: 1px solid var(--line); border-radius: 10px; padding: 10px 14px;
}
.snapshot-card {
    background: #F7F9FB; border: 1px solid var(--line); border-radius: 10px;
    padding: 18px 20px; margin-bottom: 10px;
}
.reason-chip {
    background: var(--accent-soft); border-left: 3px solid var(--accent); border-radius: 6px;
    padding: 10px 14px; margin-bottom: 8px; font-size: 0.95rem;
}
.health-row { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid var(--line); font-size: 0.95rem; }
.health-row:last-child { border-bottom: none; }
.maintenance-box { background: #F7F9FB; border: 1px solid var(--line); border-radius: 10px; padding: 16px 20px; }
button[kind="primary"], button[kind="primaryFormSubmit"] { background-color: var(--accent); border-color: var(--accent); }
button[kind="primary"]:hover { background-color: var(--accent-dark); border-color: var(--accent-dark); }
[data-testid="stSidebar"] { background: #F2F5F9; }
div[data-testid="stProgress"] div[role="progressbar"] > div:first-child { background-color: var(--accent); }
</style>
"""


# ------------------------------------------------------------------ state helpers
def init_state():
    ss = st.session_state
    if "step" not in ss:
        ss.step = 0
    if "inputs" not in ss:
        ss.inputs = {
            "age": 28, "dependents": 0, "has_retirement": True, "retirement_age": 60,
            "mode": "SIP (monthly)", "amount": 10000, "sip_step_up_enabled": False, "sip_step_up": 0.0,
            "income_growth": 0.0, "stated_risk": "Moderate",
            "quiz_idx": [None, None, None],
            "goals_df": pd.DataFrame({
                GOAL_COLS[0]: ["Vacation"], GOAL_COLS[1]: [150000.0], GOAL_COLS[2]: [2.0],
                GOAL_COLS[3]: ["Important"], GOAL_COLS[4]: ["Travel"],
            }),
            "employment": "Salaried", "emi_total": 0, "emi_high_interest": False,
            "emergency_savings": 0,
            "has_health_insurance": True, "has_life_insurance": True, "sole_earner": False,
            "liquidity_need": "Some",
            # ---- Revision items 1/2: easy, non-exact questions used to ESTIMATE income/expenses ----
            "location_tier": C.LOCATION_TIERS[1], "housing_situation": C.HOUSING_SITUATIONS[2],
            "vehicle_indicator": C.VEHICLE_INDICATORS[1], "income_band": C.INCOME_BANDS[2][0],
            "use_exact_financials": False,            # True = user chose to type exact Rs figures instead
            "monthly_income": 0, "monthly_expenses": 0,   # only used when use_exact_financials is True
            # ---- Revision item 9: existing investments by category, not a 2-bucket equity/other split ----
            "existing_by_category": {c: 0 for c in A.EXISTING_CATEGORIES},
        }


def _num(x):
    return 0.0 if x is None or pd.isna(x) else float(x)


def _txt(x, default=""):
    s = "" if x is None or pd.isna(x) else str(x).strip()
    return s or default


def resolve_income_expenses(i):
    """Revision items 1/2: by default, income/expenses come from the easy questions (income band,
    location, housing, vehicle, dependents) via risk.estimate_income_expenses() - never asked as
    exact numbers. A user who explicitly says they know their own numbers (use_exact_financials)
    gets to type them directly instead, overriding the estimate. Returns
    (monthly_income, monthly_expenses, is_estimated, note)."""
    if i.get("use_exact_financials"):
        return float(i.get("monthly_income") or 0), float(i.get("monthly_expenses") or 0), False, None
    mi, me, note = R.estimate_income_expenses(i)
    return (mi or 0.0), (me or 0.0), True, note


def engine_inputs():
    """Convert what the user typed into the plain dict the engine expects."""
    i = st.session_state.inputs
    goals = [{
        "name": _txt(r.get(GOAL_COLS[0])), "cost": _num(r.get(GOAL_COLS[1])), "years": _num(r.get(GOAL_COLS[2])),
        "priority": _txt(r.get(GOAL_COLS[3]), "Important"), "inflation_category": _txt(r.get(GOAL_COLS[4]), "General"),
    } for r in i["goals_df"].to_dict("records")]
    quiz = [R.QUIZ[k]["options"][idx][1] for k, idx in enumerate(i["quiz_idx"]) if idx is not None]
    monthly_income, monthly_expenses, is_estimated, note = resolve_income_expenses(i)
    return {
        "age": int(i["age"]), "dependents": int(i["dependents"]), "has_retirement": bool(i["has_retirement"]),
        "retirement_age": int(i["retirement_age"]), "monthly_expenses": float(monthly_expenses),
        "mode": i["mode"], "amount": float(i["amount"]),
        "sip_step_up_enabled": bool(i.get("sip_step_up_enabled", False)),
        "sip_step_up": float(i.get("sip_step_up") or 0.0) / 100.0,
        "income_growth": float(i.get("income_growth") or 0.0) / 100.0,
        "goals": goals, "stated_risk": i["stated_risk"], "quiz": quiz,
        "employment": i["employment"], "monthly_income": float(monthly_income), "emi_total": float(i["emi_total"]),
        "emi_high_interest": bool(i["emi_high_interest"]),
        "existing_by_category": dict(i.get("existing_by_category") or {}),
        "emergency_savings": float(i["emergency_savings"]),
        "has_health_insurance": bool(i["has_health_insurance"]), "has_life_insurance": bool(i["has_life_insurance"]),
        "sole_earner": bool(i["sole_earner"]), "liquidity_need": i["liquidity_need"],
        "location_tier": i["location_tier"], "housing_situation": i["housing_situation"],
        "vehicle_indicator": i["vehicle_indicator"], "income_band": i["income_band"],
        "income_expense_estimated": is_estimated, "income_expense_note": note,
    }


@st.cache_data(show_spinner=False)
def cached_plan(sig, override, mult):
    return A.build_plan(json.loads(sig), override=override, amount_mult=mult)


def go(step):
    st.session_state.step = step
    st.rerun()


def suffix(mode):
    return "/month" if mode.startswith("SIP") else ""


# ------------------------------------------------------------------ chart helpers
def donut(alloc):
    df = pd.DataFrame({"Asset": list(alloc.keys()), "Percent": list(alloc.values())})
    df = df[df["Percent"] > 0]
    return (alt.Chart(df).mark_arc(innerRadius=55)
            .encode(theta=alt.Theta("Percent:Q"),
                    color=alt.Color("Asset:N", scale=ASSET_SCALE, legend=alt.Legend(orient="bottom", title=None)),
                    tooltip=["Asset:N", alt.Tooltip("Percent:Q", format=".1f")])
            .properties(height=260))


def disposable_income_chart(projection):
    """Line chart: how income, expenses and disposable income are projected to move over time,
    given the income-growth assumption (and the auto-computed expense-growth rate)."""
    rows = []
    for r in projection:
        rows += [{"Year": r["year"], "Series": s, "Amount": r[k]}
                 for s, k in [("Income", "income"), ("Expenses", "expenses"), ("Disposable income", "disposable")]]
    df = pd.DataFrame(rows)
    return (alt.Chart(df).mark_line(point=True)
            .encode(x=alt.X("Year:Q", title="Years from now"),
                    y=alt.Y("Amount:Q", title="Rs / month"),
                    color=alt.Color("Series:N", scale=alt.Scale(domain=["Income", "Expenses", "Disposable income"],
                                                                 range=["#1B4971", "#C9A227", "#2E72A4"]),
                                    legend=alt.Legend(orient="bottom", title=None)),
                    tooltip=["Year:Q", "Series:N", alt.Tooltip("Amount:Q", format=",.0f")])
            .properties(height=260, width="container"))


def net_worth_chart(projection):
    """Line chart: total projected wealth (existing assets + everything invested through this plan,
    compounding at the recommended portfolio's expected return) against age."""
    df = pd.DataFrame(projection)
    return (alt.Chart(df).mark_line(point=True, color="#1B4971")
            .encode(x=alt.X("age:Q", title="Age"),
                    y=alt.Y("wealth:Q", title="Total wealth (Rs)"),
                    tooltip=[alt.Tooltip("age:Q", title="Age"), alt.Tooltip("wealth:Q", title="Wealth", format=",.0f")])
            .properties(height=280, width="container"))


# ------------------------------------------------------------------ table helpers
def goals_table(plan):
    sip = plan["mode"].startswith("SIP")
    opt = plan["options"][plan["recommended"]]
    rows = []
    for g, r in zip(plan["goals"], opt["goals"]):
        rows.append({
            "Goal": g["name"], "Priority": g.get("priority", "-"), "Years": f"{g['years']:g}", "Horizon": g["bucket"],
            "Target (future Rs)": fmt_inr(g["target"]) if g["target"] else "No fixed target",
            "Needed": (fmt_inr(g["required"]) + suffix(plan["mode"])) if g.get("required") else "-",
            "Allocated": fmt_inr(g["funding"]) + suffix(plan["mode"]),
            "Funded": f"{g['funded_ratio'] * 100:.0f}%" if g.get("funded_ratio") is not None else "-",
            "Equity share": f"{r['equity_pct']:.0f}%",
        })
    return pd.DataFrame(rows)


def per_goal_alloc_table(plan):
    opt = plan["options"][plan["recommended"]]
    rows = []
    for r in opt["goals"]:
        row = {"Goal": r["goal"]}
        row.update({a: f"{v:.0f}%" for a, v in r["alloc"].items()})
        rows.append(row)
    return pd.DataFrame(rows)


def outcomes_table(plan):
    rows = []
    for n, o in plan["options"].items():
        for r in o["goals"]:
            rows.append({
                "Option": n + (" (suggested)" if n == plan["recommended"] else ""), "Goal": r["goal"],
                "Chance of reaching target": "n/a" if r["prob"] is None else f"{r['prob'] * 100:.0f}%",
                "Typical outcome": fmt_inr(r["median"]),
                "Typical as % of target": "n/a" if r["median_pct"] is None else f"{r['median_pct'] * 100:.0f}%",
                "Weak market (10th pct)": fmt_inr(r["p10"]), "Strong market (90th pct)": fmt_inr(r["p90"]),
            })
    return pd.DataFrame(rows)


GOAL_STATUS_COLOR = {"On Track": "🟢", "Needs Attention": "🟡", "Currently Unfunded": "🔴"}


def goal_status(g):
    """Revision item 17: a simple, honest status label - On Track / Needs Attention / Currently
    Unfunded. Open-ended goals (no fixed cost) always receive whatever money is left over, so
    they're always 'On Track' by definition."""
    if g.get("target") is None:
        return "On Track"
    fr = g.get("funded_ratio")
    if fr is None or g.get("funding", 0) <= 0:
        return "Currently Unfunded"
    return "On Track" if fr >= 0.95 else "Needs Attention"


def goals_tracker_table(plan, current_year):
    """Revision item 17: one table per goal with everything the brief asked for - target year,
    estimated future cost, amount allocated, projected amount available, funding gap/surplus, and
    status. Funding is NEVER double-counted: build_plan() allocates money to goals sequentially,
    subtracting each goal's funding from what's left before the next goal is considered - verified
    in allocation.build_plan() step 3 and by test_engine.py's priority-ordering check."""
    opt = plan["options"][plan["recommended"]]
    rows = []
    for g, r in zip(plan["goals"], opt["goals"]):
        status = goal_status(g)
        if g.get("required") and g["funding"] < g["required"] - 0.5:
            gap_surplus = f"-{fmt_inr(g['required'] - g['funding'])} short"
        elif g.get("required"):
            gap_surplus = "Fully funded"
        else:
            gap_surplus = "-"
        rows.append({
            "Goal": g["name"],
            "Target year": f"{current_year + round(g['years'])}" if g.get("years") else "-",
            "Estimated future cost": fmt_inr(g["target"]) if g.get("target") else "Open-ended",
            "Amount allocated": fmt_inr(g["funding"]) + suffix(plan["mode"]),
            "Projected amount available": fmt_inr(r["median"]) if r.get("median") else "-",
            "Funding gap / surplus": gap_surplus,
            "Chance of success": f"{r['prob']*100:.0f}%" if r.get("prob") is not None else "n/a",
            "Status": f"{GOAL_STATUS_COLOR[status]} {status}",
        })
    return pd.DataFrame(rows)


def combined_mix_section(plan, opt):
    """Revision item 9: Current Mix / Target Mix / New-money allocation / Combined Mix, so the
    recommendation is never shown as if existing investments didn't exist."""
    combined = opt.get("combined")
    if not combined or combined["existing_total"] <= 0:
        st.caption("No existing investments entered in Step 2 - the recommended mix above applies "
                   "directly to your new investment.")
        return
    k = st.columns(3)
    k[0].metric("Existing investments", fmt_inr(combined["existing_total"]))
    k[1].metric("New money (this period)", fmt_inr(combined["new_amount"]) + suffix(plan["mode"]))
    k[2].metric("Combined total", fmt_inr(combined["combined_total"]))
    rows = []
    for a in C.ASSETS:
        cur = (combined["current_mix"] or {}).get(a, 0.0)
        tgt = combined["target_mix"].get(a, 0.0)
        new = (combined["new_money_alloc"] or {}).get(a, 0.0) if combined["new_money_alloc"] else 0.0
        comb = combined["combined_mix"].get(a, 0.0)
        if max(cur, tgt, new, comb) < 0.5:
            continue
        rows.append({"Asset": a, "Current mix": f"{cur:.0f}%", "Target mix": f"{tgt:.0f}%",
                     "New money →": f"{new:.0f}%", "Combined mix": f"{comb:.0f}%"})
    st.dataframe(pd.DataFrame(rows), hide_index=True)
    st.caption("'New money →' is how THIS period's investment should be split so your overall combined "
               "portfolio moves toward the target mix - your existing holdings are never sold to get there.")


def alt_comparison_df(plan, alt_name):
    """Revision item 15: show an alternative portfolio as WEIGHT CHANGES vs the recommended one,
    not as an unexplained separate option."""
    rec = plan["recommended"]
    rec_alloc = plan["options"][rec]["overall_alloc"]
    alt_alloc = plan["options"][alt_name]["overall_alloc"]
    rows = []
    for a in C.ASSETS:
        r, v = rec_alloc[a], alt_alloc[a]
        if r < 0.5 and v < 0.5:
            continue
        delta = v - r
        change = "—" if abs(delta) < 0.5 else (f"↑{delta:.0f} pts" if delta > 0 else f"↓{abs(delta):.0f} pts")
        rows.append({"Asset": a, f"{rec} (recommended)": f"{r:.0f}%", alt_name: f"{v:.0f}%", "Change": change})
    return pd.DataFrame(rows)


def methodology_solver_section(plan):
    """Revision item 8: the 'How was this portfolio calculated?' transparency panel - collapsed by
    default, so it never competes for attention with the main result, but is one click away for
    academic evaluation."""
    with st.expander("View methodology / solver (how this portfolio was calculated)"):
        st.markdown(
            "**Optimisation objective:** maximise `w'μ − 0.5×λ×w'Σw` (mean-variance utility) subject to: "
            "weights sum to 100%, no short selling, equity-type exposure capped by goal horizon, and a "
            "per-asset ceiling (to avoid any single asset dominating due to estimation noise in the "
            "correlation data). λ (risk aversion) is the single documented number that separates "
            "Conservative/Moderate/Aggressive - a bigger λ penalises portfolio variance more heavily."
        )
        for name in C.PROFILES:
            st.markdown(f"**{name}** (λ = {A.RISK_AVERSION[name]})")
            table = A.solver_table(name)
            st.dataframe(pd.DataFrame([
                {"Asset": r["asset"], "Expected return": f"{r['expected_return']*100:.1f}%",
                 "Volatility": f"{r['volatility']*100:.1f}%", "Optimised weight": f"{r['weight']*100:.1f}%"}
                for r in table]), hide_index=True)
        st.caption("Market-data methodology (per asset class) - see DATA_SOURCES.md for the full write-up:")
        st.dataframe(pd.DataFrame([
            {"Asset": a, "Representative benchmark": m["representative"], "Data type": m["data_type"], "Period": m["period"]}
            for a, m in C.METHODOLOGY.items()]), hide_index=True)


def action_plan(plan):
    """Item 12/44: concrete next steps, not just an allocation. Every line traces to a computed number."""
    sip = plan["mode"].startswith("SIP")
    tips = []
    for g in plan["goals"]:
        if g.get("required") and g.get("funded_ratio") is not None and g["funded_ratio"] < 0.999:
            gap = max(0.0, g["required"] - g["funding"])
            tips.append(f"'{g['name']}': increase funding by about {fmt_inr(gap)}{suffix(plan['mode'])}, "
                        "or push the goal date out, to fully fund it.")
    et = plan["emergency_topup"]
    if et["required"] > 0 and et["funding"] < et["required"] - 0.5:
        tips.append(f"Keep building your emergency fund - about {fmt_inr(et['required'] - et['funding'])} more "
                    "is needed to reach your target buffer.")
    snap = plan["snapshot"]
    if snap["high_interest_debt"]:
        tips.append("Prioritise repaying high-interest debt before increasing investments further.")
    if not snap["has_health_insurance"]:
        tips.append("Consider adequate health insurance coverage as part of your overall plan.")
    if plan["financial_health"].get("Insurance Protection") == "Needs Review" and snap["has_health_insurance"]:
        tips.append("Consider adequate life insurance cover, since you are a primary earner with dependents.")
    if not tips:
        tips.append("Your plan looks on track based on what you've entered. Revisit it if your goals, income or dependents change.")
    return tips


def plan_markdown(plan, explanation):
    prof = plan["profile"]
    lines = ["# My goal-based investment plan", "", f"_{DISCLAIMER}_", "",
             f"**Investing:** {fmt_inr(plan['amount'])}{suffix(plan['mode'])} ({plan['mode']})  ",
             f"**Risk score:** {prof['score']}/10 - suggested profile: **{plan['recommended']}**  ",
             f"**Risk appetite / capacity / required:** {prof['willingness']}/10 / {prof['capacity']}/10 / {prof['required_risk']['label']}  ",
             "", "## Explanation", explanation, "", "## Financial health"]
    for k, v in plan["financial_health"].items():
        lines.append(f"- **{k}:** {v}")
    lines += ["", "## Goals"]
    for _, row in goals_table(plan).iterrows():
        lines.append(f"- **{row['Goal']}** ({row['Priority']}, {row['Years']} yrs, {row['Horizon']}): target {row['Target (future Rs)']}, "
                     f"allocated {row['Allocated']}, funded {row['Funded']}, equity {row['Equity share']}")
    lines += ["", "## The three options (overall mix)"]
    for n, o in plan["options"].items():
        mix = ", ".join(f"{a} {v:.0f}%" for a, v in o["overall_alloc"].items() if v > 0)
        lines.append(f"- **{n}{' (suggested)' if n == plan['recommended'] else ''}:** {mix} | expected return "
                     f"{o['exp_return'] * 100:.1f}% | Sharpe {o['sharpe']:.2f} | bad-year {o['bad_year'] * 100:.1f}%")
    lines += ["", "## Action plan"] + [f"- {t}" for t in action_plan(plan)]
    lines += ["", "## Assumptions", plan["assumptions_note"],
              f"Inflation assumed at {plan['inflation'] * 100:.0f}% a year (goal-specific rates may differ - see the Assumptions panel). "
              f"Probabilities come from {C.N_SIMS:,} simulated futures."]
    return "\n".join(lines)


# ------------------------------------------------------------------ sidebar
def sidebar():
    st.sidebar.title("📈 Portfolio Planner")
    step = st.session_state.step
    for i, s in enumerate(STEPS):
        mark = "✅" if i < step else "▶️" if i == step else "⬜"
        st.sidebar.markdown(f"{mark} {s}")
    st.sidebar.divider()
    with st.sidebar.expander("Assumptions & methodology"):
        st.caption("Return & volatility assumptions (by asset class):")
        st.dataframe(pd.DataFrame([{"Asset": a, "Exp. return": f"{v[0] * 100:.1f}%", "Volatility": f"{v[1] * 100:.1f}%"}
                                   for a, v in C.ASSUMPTIONS.items()]), hide_index=True)
        st.caption(C.ASSUMPTIONS_NOTE)
        st.caption("Inflation by goal type (item 23 - different expenses inflate at different rates):")
        st.dataframe(pd.DataFrame([{"Goal type": k, "Assumed inflation": f"{v*100:.0f}%"} for k, v in C.GOAL_INFLATION.items()]),
                    hide_index=True)
        st.caption(f"Planning margin {C.PLANNING_MARGIN * 100:.0f} pt | risk-free rate (for Sharpe) {C.RISK_FREE_RATE*100:.1f}% | "
                   f"{C.N_SIMS:,} simulations | emergency-fund months and EMI-burden threshold are stated planning "
                   "heuristics, not regulatory requirements - see config.py.")
        st.caption("User-provided: age, income, goals, risk answers. Model-estimated: required return, funding gaps, "
                   "probabilities. Default assumptions: all return/inflation/emergency-fund figures above.")
    st.sidebar.caption(DISCLAIMER)


# ------------------------------------------------------------------ step 0: how it works
def step_intro():
    st.title("Build your plan around your life.")
    st.markdown("Tell us what you're investing for, and we'll turn it into a portfolio you can understand - "
                "not just a number, but the reasoning behind it.")
    cols = st.columns(5)
    for col, (n, label) in zip(cols, enumerate([
        "Tell us about your finances", "Add your financial goals", "Understand your risk profile",
        "Get your personalised portfolio", "Compare alternative strategies"], start=1)):
        col.markdown(f"**Step {n}**")
        col.caption(label)
    st.write("")
    if st.button("Build my plan →", type="primary", key="intro_start"):
        go(1)


# ------------------------------------------------------------------ step 1: about you
def step_about():
    inp = st.session_state.inputs
    st.subheader("Step 1 of 5 · About you")
    st.caption("Easy questions, not exact numbers - we'll use these to estimate your financial picture "
               "without asking for figures a first-time investor may not know precisely.")
    c1, c2 = st.columns(2)
    age = c1.number_input("Your age", 18, 70, int(inp["age"]), key="w_age")
    deps = c2.number_input("People who depend on you financially (spouse, children, parents)", 0, 10,
                           int(inp["dependents"]), key="w_deps",
                           help="Household responsibilities affect how much risk your situation can really afford, "
                                "separately from how much risk you say you're comfortable with.")

    c3, c4 = st.columns(2)
    location = c3.selectbox("Where do you live?", C.LOCATION_TIERS,
                            index=C.LOCATION_TIERS.index(inp["location_tier"]) if inp["location_tier"] in C.LOCATION_TIERS else 1,
                            key="w_location", help="Used only to estimate a broad cost-of-living level - not your exact city.")
    employment = c4.selectbox("Occupation", C.EMPLOYMENT_TYPES,
                              index=C.EMPLOYMENT_TYPES.index(inp["employment"]) if inp["employment"] in C.EMPLOYMENT_TYPES else 0,
                              key="w_employment")

    income_band = st.selectbox("Annual income band", [b[0] for b in C.INCOME_BANDS],
                               index=[b[0] for b in C.INCOME_BANDS].index(inp["income_band"]) if inp["income_band"] in dict(C.INCOME_BANDS) else 2,
                               key="w_income_band",
                               help="A range, not an exact figure - we only use this to estimate your financial "
                                    "capacity, never to identify you personally.")
    vehicle = st.selectbox("Vehicle / lifestyle (a small supporting indicator only)", C.VEHICLE_INDICATORS,
                           index=C.VEHICLE_INDICATORS.index(inp["vehicle_indicator"]) if inp["vehicle_indicator"] in C.VEHICLE_INDICATORS else 1,
                           key="w_vehicle")

    has_ret = st.checkbox("I also want to plan for retirement", value=bool(inp["has_retirement"]), key="w_has_ret")
    ret_age = inp["retirement_age"]
    if has_ret:
        ret_age = st.number_input("Retirement age", 35, 80, max(int(inp["retirement_age"]), 35), key="w_ret_age")
    if deps > 0:
        sole = st.checkbox("I am the sole or primary income earner in my household", value=bool(inp["sole_earner"]), key="w_sole")
    else:
        sole = False
    if st.button("Next →", type="primary", key="next0"):
        inp.update(age=int(age), dependents=int(deps), has_retirement=bool(has_ret), retirement_age=int(ret_age),
                   sole_earner=bool(sole), location_tier=location, employment=employment,
                   income_band=income_band, vehicle_indicator=vehicle)
        go(2)


# ------------------------------------------------------------------ step 2: financial life
def step_financial_life():
    inp = st.session_state.inputs
    st.subheader("Step 2 of 5 · Your financial life")
    st.caption("This helps us check what you can actually afford to invest, and whether anything needs attention "
               "before building a long-term portfolio.")

    housing = st.selectbox("Housing situation", C.HOUSING_SITUATIONS,
                           index=C.HOUSING_SITUATIONS.index(inp["housing_situation"]) if inp["housing_situation"] in C.HOUSING_SITUATIONS else 2,
                           key="w_housing")

    use_exact = st.checkbox("I'd rather enter my exact monthly income and expenses", value=bool(inp.get("use_exact_financials", False)),
                            key="w_use_exact",
                            help="By default we ESTIMATE these from your income band, location, housing and vehicle "
                                 "answers (Step 1) - never asked as an exact figure. Tick this only if you already "
                                 "know your own numbers precisely.")
    preview_inp = {**inp, "housing_situation": housing}
    est_income, est_expenses, est_note = R.estimate_income_expenses(preview_inp)
    if use_exact:
        c1, c2 = st.columns(2)
        income = c1.number_input("Your monthly take-home income (Rs)", 0, 10_000_000, int(inp.get("monthly_income") or (est_income or 0)),
                                 step=1000, key="w_income")
        expenses = c2.number_input("Monthly household expenses (Rs)", 0, 10_000_000, int(inp.get("monthly_expenses") or (est_expenses or 0)),
                                   step=1000, key="w_expenses")
    else:
        income, expenses = est_income or 0.0, est_expenses or 0.0
        c1, c2 = st.columns(2)
        c1.metric("Estimated monthly income", fmt_inr(income))
        c2.metric("Estimated monthly expenses", fmt_inr(expenses))
        if est_note:
            with st.expander("View methodology (how this estimate was calculated)"):
                st.caption(est_note)

    income_growth = inp.get("income_growth", 0.0)
    if income > 0:
        income_growth = st.slider("Expected annual increase in your income (%)", 0, 20, int(inp.get("income_growth") or 0), 1,
                                  key="w_income_growth",
                                  help="If your income is likely to grow, your disposable income and affordable SIP can grow with it.")
        exp_growth = A.expense_growth_rate(income_growth / 100.0)
        if income_growth > 0:
            st.caption(f"We'll assume your expenses grow too - at {C.INFLATION*100:.0f}%/yr inflation, plus a bit more "
                       f"({C.LIFESTYLE_CREEP_FACTOR*100:.0f}% of any raise above inflation, a common \"lifestyle creep\" "
                       f"pattern) - about {exp_growth*100:.1f}%/yr in total.")

    c3, c4 = st.columns(2)
    emi = c3.number_input("Total monthly EMIs / loan payments (Rs)", 0, 10_000_000, int(inp["emi_total"]), step=500, key="w_emi")
    emi_high = c4.checkbox("Some of this debt is high-interest (e.g. credit card, personal loan)",
                           value=bool(inp["emi_high_interest"]), key="w_emi_high") if emi > 0 else False

    st.markdown("**Existing investments** (so we recommend a *combined* portfolio, not one that ignores what you already hold)")
    existing_by_category = dict(inp.get("existing_by_category") or {})
    cols = st.columns(len(A.EXISTING_CATEGORIES))
    for col, cat in zip(cols, A.EXISTING_CATEGORIES):
        existing_by_category[cat] = col.number_input(cat, 0, 100_000_000, int(existing_by_category.get(cat, 0) or 0),
                                                      step=5000, key=f"w_existing_{cat}")

    st.markdown("**Emergency fund**")
    emergency_savings = st.number_input("Money already set aside as an emergency fund (Rs)", 0, 100_000_000,
                                        int(inp["emergency_savings"]), step=5000, key="w_emergency",
                                        help="Kept separately from your long-term investments, in something liquid like a savings or liquid fund. "
                                             "Never counted as part of your investment portfolio.")
    months, target = R.emergency_fund_target({**inp, "monthly_expenses": expenses, "dependents": inp["dependents"]})
    if expenses > 0:
        st.caption(f"Based on your occupation and dependents, a buffer of about {months:g} months of expenses "
                   f"(~{fmt_inr(target)}) is a reasonable target.")

    liquidity = st.radio("How much of this investment might you need to access unexpectedly?",
                         ["Very little", "Some", "Significant"],
                         index=["Very little", "Some", "Significant"].index(inp["liquidity_need"]), horizontal=True, key="w_liquidity")

    if inp["dependents"] > 0:
        st.markdown("**Protection check** (we don't recommend insurance products - just flag a gap if one exists)")
        c7, c8 = st.columns(2)
        health = c7.checkbox("I have health insurance", value=bool(inp["has_health_insurance"]), key="w_health_ins")
        life = c8.checkbox("I have life insurance / term cover", value=bool(inp["has_life_insurance"]), key="w_life_ins")
    else:
        health, life = inp["has_health_insurance"], inp["has_life_insurance"]

    def _save():
        inp.update(housing_situation=housing, use_exact_financials=bool(use_exact),
                   monthly_income=float(income), monthly_expenses=float(expenses),
                   income_growth=float(income_growth), emi_total=float(emi), emi_high_interest=bool(emi_high),
                   existing_by_category=existing_by_category,
                   emergency_savings=float(emergency_savings),
                   liquidity_need=liquidity, has_health_insurance=bool(health), has_life_insurance=bool(life))

    c1, c2, _ = st.columns([1, 1, 4])
    if c1.button("← Back", key="back_fl"):
        _save()
        go(1)
    if c2.button("Next →", type="primary", key="next_fl"):
        _save()
        go(3)


# ------------------------------------------------------------------ step 3: money & goals
def step_money():
    inp = st.session_state.inputs
    st.subheader("Step 3 of 5 · Your money and goals")
    mode = st.radio("How will you invest?", ["SIP (monthly)", "Lumpsum"], horizontal=True, key="w_mode",
                    index=0 if inp["mode"].startswith("SIP") else 1)
    label = "Monthly SIP amount (Rs)" if mode.startswith("SIP") else "One-time amount to invest (Rs)"
    amount = st.number_input(label, 0, 100_000_000, int(inp["amount"]), step=1000, key="w_amount")
    step_up_enabled = inp.get("sip_step_up_enabled", False)
    step_up = inp["sip_step_up"]
    if mode.startswith("SIP"):
        step_up_enabled = st.checkbox("Increase my SIP every year", value=bool(step_up_enabled), key="w_stepup_on",
                                      help="If your income is likely to grow, a rising SIP reaches the same goal with a smaller starting amount.")
        if step_up_enabled:
            step_up = st.slider("Annual increase (%)", 0, 25, int(inp["sip_step_up"]), 1, key="w_stepup")
            suggestion = A.implied_disposable_growth({
                "monthly_income": inp.get("monthly_income", 0), "monthly_expenses": inp.get("monthly_expenses", 0),
                "emi_total": inp.get("emi_total", 0), "income_growth": float(inp.get("income_growth") or 0.0) / 100.0,
            })
            if suggestion > 0.005:
                st.caption(f"Based on the income/expense growth you entered earlier, your disposable income could "
                           f"grow by about {suggestion*100:.0f}%/yr - a reasonable step-up to try, though you can set any value.")
            else:
                st.caption("You didn't enter an expected income growth rate earlier, so pick a step-up you're "
                           "comfortable committing to (commonly 5-10%/yr, in line with typical salary growth).")
    st.markdown("**Your goals** - add one row per goal. Enter the cost in *today's* rupees; we adjust for inflation using "
               "a rate that depends on the goal type. Use cost 0 for an open-ended goal. Set priority so we know what to "
               "fund first if your amount can't cover everything.")
    edited = st.data_editor(
        inp["goals_df"], num_rows="dynamic", key="w_goals",
        column_config={
            GOAL_COLS[0]: st.column_config.TextColumn("Goal name", help="e.g. Marriage, Child's education, Vacation"),
            GOAL_COLS[1]: st.column_config.NumberColumn("Cost today (Rs)", min_value=0, step=10000, format="%.0f"),
            GOAL_COLS[2]: st.column_config.NumberColumn("Years to go", min_value=0.5, max_value=50, step=0.5, format="%.1f"),
            GOAL_COLS[3]: st.column_config.SelectboxColumn("Priority", options=C.PRIORITIES, default="Important"),
            GOAL_COLS[4]: st.column_config.SelectboxColumn("Inflation category", options=list(C.GOAL_INFLATION.keys()),
                                                            default="General"),
        })
    c1, c2, _ = st.columns([1, 1, 4])
    if c1.button("← Back", key="back1"):
        go(2)
    if c2.button("Next →", type="primary", key="next1"):
        inp.update(mode=mode, amount=int(amount), sip_step_up_enabled=bool(step_up_enabled),
                   sip_step_up=float(step_up), goals_df=edited.copy())
        go(4)


# ------------------------------------------------------------------ step 4: risk comfort
def step_risk():
    inp = st.session_state.inputs
    st.subheader("Step 4 of 5 · How do you feel about risk?")
    levels = ["Low", "Moderate", "High"]
    stated = st.radio("In general, how would you describe your risk appetite?", levels,
                      index=levels.index(inp["stated_risk"]), horizontal=True, key="w_stated")
    st.markdown("Now three quick scenarios. Your answers tell us more than a label does.")
    idxs = []
    for k, q in enumerate(R.QUIZ):
        opts = [o[0] for o in q["options"]]
        choice = st.radio(f"{k + 1}. {q['q']}", opts, index=inp["quiz_idx"][k], key=f"w_q{k}")
        idxs.append(None if choice is None else opts.index(choice))
    complete = all(i is not None for i in idxs)
    if not complete:
        st.caption("Please answer all three scenarios to continue.")
    c1, c2, _ = st.columns([1, 2, 3])
    if c1.button("← Back", key="back2"):
        inp.update(stated_risk=stated, quiz_idx=idxs)
        go(3)
    if c2.button("Review my profile →", type="primary", key="next2", disabled=not complete):
        inp.update(stated_risk=stated, quiz_idx=idxs)
        go(5)


# ------------------------------------------------------------------ step 5: review
def step_review():
    einp = engine_inputs()
    errors, warnings = R.validate(einp)
    st.subheader("Review · here is what we understood")
    for e in errors:
        st.error(e)
    for w in warnings:
        st.warning(w)
    if not errors:
        goals = R.build_goals(einp)
        prof = R.risk_profile(einp, goals)
        c = st.columns(4)
        c[0].metric("Risk appetite", f"{prof['willingness']}/10", help="How comfortable you say you are with ups and downs.")
        c[1].metric("Risk capacity", f"{prof['capacity']}/10", help="How much risk your age, dependents, goals and emergency fund can really afford.")
        c[2].metric("Suggested profile", prof["label"], help="The lower of appetite and capacity - never higher than either.")
        c[3].metric("Your score", f"{prof['score']}/10")
        st.progress(min(prof["score"] / 10, 1.0))
        st.caption("Your suggested profile is the LOWER of your comfort with risk and what your situation can afford. "
                   "On the next page you'll also see 'Required Risk' - what your goals would actually need.")
        st.markdown(f"**Investing:** {fmt_inr(einp['amount'])}{suffix(einp['mode'])} ({einp['mode']})"
                   + (f", stepping up {einp['sip_step_up']*100:.0f}%/year" if einp["mode"].startswith("SIP") and einp.get("sip_step_up_enabled") and einp["sip_step_up"] > 0 else ""))
        if goals:
            st.dataframe(pd.DataFrame([{
                "Goal": g["name"], "Priority": g.get("priority", "-"), "Years to go": f"{g['years']:g}", "Horizon": g["bucket"],
                "Target (future Rs)": fmt_inr(g["target"]) if g["target"] else "No fixed target"} for g in goals]),
                hide_index=True)
        preview = cached_plan(json.dumps(einp, sort_keys=True, default=str), None, 1.0)
        for n in preview["notes"][:4]:
            st.info(n)
    c1, c2, _ = st.columns([1, 2, 3])
    if c1.button("← Edit answers", key="back3"):
        go(4)
    if c2.button("Generate my plan →", type="primary", key="next3", disabled=bool(errors)):
        go(6)


# ------------------------------------------------------------------ step 6: results
def get_explanation(plan, sig, api_key, model, force=False):
    ex = st.session_state.get("expl")
    if force or not ex or ex["sig"] != sig:
        with st.spinner("Writing your personalised explanation..."):
            text, used, err = D.generate_explanation(plan, api_key, model)
        st.session_state.expl = {"sig": sig, "text": text, "used_ai": used, "err": err}
    return st.session_state.expl


def render_reasoning_chips(markdown_text):
    """Split the AI/fallback text's first '### Why this fits you' section into visual chip cards (UI item 13)."""
    lines = markdown_text.split("\n")
    try:
        start = next(i for i, l in enumerate(lines) if l.strip().startswith("### Why this fits you")) + 1
    except StopIteration:
        return markdown_text, "\n".join(lines)
    end = next((i for i in range(start, len(lines)) if lines[i].strip().startswith("###")), len(lines))
    bullets = [l.strip("- ").strip() for l in lines[start:end] if l.strip().startswith("-")]
    rest = "\n".join(lines[end:])

    def _chip_inner(b):
        # escape first (so any literal <, >, & in a goal name etc. can't break the markup or inject
        # HTML), THEN turn **markdown bold** into real <b> tags - bullets reach here as markdown text,
        # not HTML, and this div is rendered with unsafe_allow_html=True.
        escaped = html.escape(b)
        return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)

    chips_html = "".join(f'<div class="reason-chip">{_chip_inner(b)}</div>' for b in bullets) if bullets else ""
    return chips_html, rest


def step_results(api_key, model):
    einp = engine_inputs()
    sig = json.dumps(einp, sort_keys=True, default=str)
    plan = cached_plan(sig, None, 1.0)
    prof, rec = plan["profile"], plan["recommended"]
    opt = plan["options"][rec]
    snap = plan["snapshot"]
    current_year = 2026
    try:
        current_year = int(st.session_state.get("_current_year", 2026))
    except Exception:
        pass
    if st.session_state.get("chat_sig") != sig:      # new inputs -> fresh chat
        st.session_state.chat, st.session_state.chat_sig = [], sig

    top = st.columns([5, 1, 1])
    top[0].title("Your plan is ready.")
    if top[1].button("✏️ Edit", key="edit_answers"):
        go(1)
    if top[2].button("↺ Restart", key="restart"):
        for k in ["step", "inputs", "expl", "chat", "chat_sig"]:
            st.session_state.pop(k, None)
        st.rerun()

    if einp.get("income_expense_estimated") and einp.get("income_expense_note"):
        st.caption(f"ℹ️ {einp['income_expense_note']}")

    # ========== PORTFOLIO AT A GLANCE (revision items 13/14 - understand this in ~10-15 seconds) ==========
    piv = plan["projected_investment_value"]
    scen = opt["scenarios"]["Typical"]
    n_goals = len(plan["goals"])
    n_on_track = sum(1 for g in plan["goals"] if goal_status(g) == "On Track")

    st.markdown("### Portfolio at a glance")
    g = st.columns(4)
    g[0].metric("Profile", rec)
    g[1].metric("Investing", fmt_inr(plan["amount"]) + suffix(plan["mode"]))
    g[2].metric("Horizon", f"{prof['weighted_horizon_years']:g} years")
    g[3].metric("Risk score", f"{prof['score']}/10")
    g2 = st.columns(4)
    g2[0].metric("Expected return", f"{scen['low']*100:.0f}-{scen['high']*100:.0f}%/yr")
    g2[1].metric("Volatility", f"{opt['volatility']*100:.1f}%/yr")
    g2[2].metric("Projected value", f"{fmt_inr(piv['p10'])} - {fmt_inr(piv['p90'])}")
    g2[3].metric("Goals", f"{n_on_track} of {n_goals} on track")
    st.caption(f"**Projected value** = {piv['definition']} Range shown is the weak-to-strong market outcome "
               f"(10th-90th percentile across {C.N_SIMS:,} simulations), not your emergency reserve.")

    # ========== COMBINED ASSET MIX (revision item 9) ==========
    st.markdown("### Your combined asset mix")
    left, right = st.columns(2)
    left.altair_chart(donut(opt["combined"]["combined_mix"] if opt["combined"]["existing_total"] > 0 else opt["overall_alloc"]))
    with right:
        combined_mix_section(plan, opt)

    # ========== WHY THIS PORTFOLIO (revision items 13/15 - short cards, not paragraphs) ==========
    st.markdown("### Why this portfolio?")
    ex = get_explanation(plan, sig, api_key, model)
    chips_html, rest_md = render_reasoning_chips(ex["text"])
    if chips_html:
        st.markdown(CUSTOM_CSS + chips_html, unsafe_allow_html=True)
    else:
        st.markdown(rest_md)
    with st.expander("Full explanation"):
        st.markdown(rest_md if chips_html else "")
        st.caption("Explanation written by AI from the tool's calculated numbers." if ex["used_ai"]
                  else "Built-in explanation (this deployment runs on the tool's own rule-based writer, "
                       "with no live AI connection).")
        if ex["err"]:
            st.warning(ex["err"])
        if st.button("Regenerate explanation", key="regen"):
            get_explanation(plan, sig, api_key, model, force=True)
            st.rerun()

    # ========== GOALS (revision item 17 - fixed goal tracker, no double counting) ==========
    st.markdown("### Your goals")
    st.dataframe(goals_tracker_table(plan, current_year), hide_index=True)
    if plan["emergency_reserve"]["topup_this_period"] > 0:
        st.info(f"{fmt_inr(plan['emergency_reserve']['topup_this_period'])} of this amount was set aside FIRST for "
               "your emergency reserve (kept separate, 100% liquid) before any goal was funded - see 'Emergency "
               "reserve vs investment portfolio' below.")
    if plan["surplus"] > 0.5:
        st.info(f"After fully funding your goals, {fmt_inr(plan['surplus'])}{suffix(plan['mode'])} was left over and "
               "has been placed in open-ended long-term wealth building.")
    with st.expander("Emergency reserve vs investment portfolio (kept strictly separate)"):
        er, ip = plan["emergency_reserve"], plan["investment_portfolio"]
        e1, e2 = st.columns(2)
        e1.metric("Emergency reserve target", fmt_inr(er["target"]))
        e1.metric("Emergency reserve - current", fmt_inr(er["current"]))
        e2.metric("Invested this period", fmt_inr(ip["amount_invested"]) + suffix(plan["mode"]))
        st.caption(er["note"])
    with st.expander("See the asset mix for each goal"):
        st.dataframe(per_goal_alloc_table(plan), hide_index=True)

    # ========== ALTERNATIVE ALLOCATIONS (revision item 15 - weight deltas, not unexplained options) ==========
    st.markdown("### Alternative allocations")
    alt_names = [n for n in C.PROFILES if n != rec]
    alt_cols = st.columns(len(alt_names))
    consequence = {
        "Conservative": "Lower volatility, lower expected return.",
        "Moderate": "A balance between growth and stability.",
        "Aggressive": "Greater expected return potential, but greater fluctuations.",
    }
    for col, name in zip(alt_cols, alt_names):
        o = plan["options"][name]
        with col:
            st.markdown(f"**{name}**")
            st.caption(consequence.get(name, ""))
            st.dataframe(alt_comparison_df(plan, name), hide_index=True)
            sc = o["scenarios"]["Typical"]
            st.caption(f"Expected return: {sc['low']*100:.0f}-{sc['high']*100:.0f}%/yr · "
                      f"Volatility: {o['volatility']*100:.1f}%/yr")

    # ========== WHAT-IF (revision item 16 - simple, only variables that matter) ==========
    st.markdown("### What if?")
    st.caption("Change one thing and see the effect instantly - this never changes your actual saved plan.")
    w1, w2, w3 = st.columns(3)
    mult = w1.slider("Invest more or less (% of your amount)", 25, 300, 100, 5, key="wi_mult") / 100
    choice = w2.selectbox("A safer / more aggressive portfolio", ["Suggested"] + C.PROFILES, key="wi_prof")
    delay_years = w3.slider("Delay all goals by (years)", 0, 10, 0, 1, key="wi_delay")
    if delay_years > 0:
        delayed_einp = dict(einp)
        delayed_einp["goals"] = [{**gl, "years": gl["years"] + delay_years} for gl in einp["goals"]]
        if delayed_einp.get("has_retirement"):
            delayed_einp["retirement_age"] = delayed_einp["retirement_age"] + delay_years
        wi = A.build_plan(delayed_einp, override=None if choice == "Suggested" else choice, amount_mult=mult)
    else:
        wi = cached_plan(sig, None if choice == "Suggested" else choice, mult)
    wi_opt = wi["options"][wi["recommended"]]
    base_prob = {r["goal"]: r["prob"] for r in opt["goals"]}
    rows = []
    for gl, r in zip(wi["goals"], wi_opt["goals"]):
        b = base_prob.get(gl["name"])
        rows.append({
            "Goal": gl["name"],
            "Funded": f"{gl['funded_ratio'] * 100:.0f}%" if gl.get("funded_ratio") is not None else "-",
            "Chance of reaching target": "n/a" if r["prob"] is None else f"{r['prob'] * 100:.0f}%",
            "Change vs your plan": "-" if (r["prob"] is None or b is None) else f"{(r['prob'] - b) * 100:+.0f} pts",
            "Typical outcome": fmt_inr(r["median"]),
        })
    k = st.columns(4)
    k[0].metric("Amount tested", fmt_inr(wi["amount"]) + suffix(wi["mode"]))
    k[1].metric("Profile tested", wi["recommended"])
    k[2].metric("Expected return / year", f"{wi_opt['exp_return'] * 100:.1f}%")
    k[3].metric("Projected value", fmt_inr(wi["projected_investment_value"]["median"]))
    st.dataframe(pd.DataFrame(rows), hide_index=True)
    st.altair_chart(donut(wi_opt["overall_alloc"]))

    # ========== Action plan ==========
    st.markdown("### Action plan")
    for tip in action_plan(plan):
        st.markdown(f"- {tip}")

    # ========== Your financial foundation (compact scorecard) ==========
    with st.expander("Your financial foundation (scorecard)"):
        health = plan["financial_health"]
        cols = st.columns(len(health))
        for col, (k2, v) in zip(cols, health.items()):
            col.markdown(f"{HEALTH_COLOR.get(v, '⚪')} **{k2}**")
            col.caption(v)
        st.markdown("##### Your wealth over time")
        nw_proj = A.net_worth_projection(einp, plan)
        st.altair_chart(net_worth_chart(nw_proj))
        current_net_worth = snap["existing_total"] + snap["emergency_current"]
        st.caption(f"Total wealth by age ({fmt_inr(current_net_worth)} today) - existing investments/savings plus "
                   f"everything invested through this plan, compounding at the recommended {rec} portfolio's "
                   "expected return. A single simplified projection, not a guarantee.")
        if plan.get("income_growth", 0) > 0:
            dp = plan["disposable_projection"]
            st.altair_chart(disposable_income_chart(dp))
        st.markdown("**Portfolio maintenance:** review your mix at least once a year, or sooner if any asset class "
                   "drifts more than ~5 percentage points from its target, or after a major life event (marriage, "
                   "new child, new home, job change). Goal-based de-risking already happens automatically as a "
                   "goal moves closer in this tool.")

    # ========== Methodology / solver (revision item 8 - collapsed by default) ==========
    methodology_solver_section(plan)

    st.divider()
    _secondary_tabs(plan, sig, api_key, model, opt, rec, current_year)
    st.divider()
    st.caption(DISCLAIMER)


def _secondary_tabs(plan, sig, api_key, model, opt, rec, current_year):
    t_chat, t_dl = st.tabs(["Ask the advisor", "Download"])

    with t_chat:
        st.markdown("Ask anything about *your* plan. The advisor only uses the numbers calculated above.")
        suggestions = ["Why is my equity share what it is?", "Why is my short-term goal so safe?",
                      "What could I change to reach my goals?"]
        sc = st.columns(3)
        for i, s in enumerate(suggestions):
            if sc[i].button(s, key=f"sq{i}"):
                st.session_state.pending_q = s
        for msg in st.session_state.chat:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
        q = st.chat_input("Ask about your plan...") or st.session_state.pop("pending_q", None)
        if q:
            history = list(st.session_state.chat)
            with st.spinner("Thinking..."):
                answer, used, err = D.answer_question(plan, history, q, api_key, model)
            st.session_state.chat += [{"role": "user", "content": q}, {"role": "assistant", "content": answer}]
            if err:
                st.warning(err)
            st.rerun()

    with t_dl:
        ex = st.session_state.get("expl") or {"text": ""}
        st.download_button("⬇️ Download my plan (Markdown)", plan_markdown(plan, ex["text"]),
                           file_name="my_investment_plan.md", mime="text/markdown")
        st.download_button("⬇️ Download goal table (CSV)", goals_tracker_table(plan, current_year).to_csv(index=False),
                           file_name="my_goal_plan.csv", mime="text/csv")


# ------------------------------------------------------------------ main
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
init_state()
sidebar()
# No API key is collected from the user in this deployment - AI explanations stay fully optional and are
# only ever switched on via a server-side ANTHROPIC_API_KEY (e.g. a Streamlit Cloud "secret"), never a
# public input box. With no key set, the app runs entirely on its own built-in rule-based explanations.
api_key, model = os.environ.get("ANTHROPIC_API_KEY"), D.DEFAULT_MODEL
step = st.session_state.step
if step > 0:
    st.progress((step - 1) / (len(STEPS) - 2), text=f"{STEPS[step]}")
{0: step_intro, 1: step_about, 2: step_financial_life, 3: step_money, 4: step_risk, 5: step_review,
 6: lambda: step_results(api_key, model)}[step]()
