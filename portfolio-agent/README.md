# Goal-Based Portfolio Planner — User Manual

This app turns your goals, money, and comfort with risk into a recommended investment portfolio —
and explains, in plain language, why that portfolio fits you.

## Opening the app
```
pip install -r requirements.txt
streamlit run app.py
```
This opens the app in your browser. No login and no API key is needed — everything works out of
the box.

## Walking through the app

The app is a short questionnaire, then a results page. It has 5 steps, shown as a progress list
on the left:

### Step 1 — About you
Your age, how many people depend on you financially, and whether you're planning for retirement
(and if so, at what age). This shapes how much investment risk your situation can reasonably take.

### Step 2 — Financial life
Your employment type, monthly income and expenses, any loan EMIs, what you already hold in
investments, and your emergency fund. If you expect your income to rise over time, you can set an
expected annual increase (%) here — the app will also assume your expenses rise a little with it.
This step tells the app what you can actually afford to invest, and whether anything (like a thin
emergency fund or heavy EMIs) needs attention before investing further.

### Step 3 — Money & goals
How you want to invest — a monthly SIP or a one-time lumpsum — and how much. If you're investing
monthly, you can turn on "Increase my SIP every year" to have your contribution step up annually.
Below that, list your goals: what you're saving for, how much it costs today, how many years away
it is, how important it is, and what kind of expense it is (used to inflate the cost realistically,
since education, healthcare, travel, and housing all get more expensive at different rates).

### Step 4 — Risk comfort
How you'd describe your general risk appetite, plus three short scenario questions. Your answers
here, not just the label you pick, are what the app actually uses to gauge how comfortable you are
with market ups and downs.

### Step 5 — Review
A final summary of everything you entered, with any warnings (for example, if your planned SIP is
more than you can actually afford) before the plan is generated.

## Reading your results page

Once you click "Generate my plan," you'll see:

- **Investor snapshot** — your risk score, how much you're investing, number of goals, and the
  return your goals would actually need to succeed as entered ("required risk").
- **Portfolio at a glance** — your projected total corpus (with a likely range), expected yearly
  return, volatility, and Sharpe ratio, all for the recommended portfolio.
- **Net worth** — what you have today (existing investments + emergency savings), and what it's
  projected to grow to.
- **Your wealth over time** — a chart of your total projected wealth at every age from now onward,
  so you can see the growth curve, not just the end number.
- **Your financial foundation** — a quick scorecard (Emergency Fund, Debt Level, Savings Rate,
  Retirement Planning, Insurance Protection, Investment Diversification) and a table of your goals
  with how much each needs, how much is being allocated, and how well-funded it is.
- **Recommended overall mix** — the suggested split across asset classes (liquid funds, debt
  funds, gold, real estate, equity, and large/mid/small/flexi-cap mutual funds), as a chart and a
  table.
- **Why this fits you** — short, plain-English reasoning connecting your specific situation (your
  goals' timelines, your risk comfort, your financial picture) to the recommendation.
- **Expected results** — for each goal, a weak-case, expected, and optimistic outcome, so you can
  see the range of what might actually happen, not just one number.
- **Compare alternatives** — the same plan under a more conservative or more aggressive risk
  profile, side by side, so you can see the trade-off.
- **Action plan** — concrete next steps if any goal isn't fully funded yet.

At the bottom, four tabs give you more to explore:
- **Goal tracker** — the chance of reaching each goal, visualised.
- **What-if** — test a different amount or risk profile instantly, without changing your actual plan.
- **Ask the advisor** — ask questions about your plan in plain language.
- **Download** — save your plan as a file.

## A note on accuracy

This is an educational planning tool, not personalised financial advice. All figures are estimates
based on stated assumptions (shown in the "Assumptions & methodology" panel in the app) and are not
guaranteed. Please consult a SEBI-registered advisor before making investment decisions.
