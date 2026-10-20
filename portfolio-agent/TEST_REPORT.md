# Test Report

Three layers of testing, re-run fresh for this submission after the move to the real 9-asset-class
data model, the SIP step-up toggle, income/expense-growth projection, and the net-worth / wealth-
over-time additions.

## 1. Automated logic tests — `python test_engine.py`

Ten test cases (TC1–TC10) exercise the deterministic engine directly, independent of the UI:
minimal defaults, emergency-fund shortfall sizing, high EMI burden + SIP-exceeds-income warnings,
existing-portfolio tilt, priority-based funding order, step-up vs flat SIP (via the new
`sip_step_up_enabled` toggle), goal-specific inflation, near-retirement aggressive-equity flag,
Sharpe/stress-decline sanity (now across all nine asset classes), and lumpsum mode.

```
=== TC1 minimal defaults === through === TC10 lumpsum mode ===
...
ALL CHECKS PASSED.
```

**Result: all 25 checks passed.** Full console output is in `test_engine_output.txt` alongside
this report.

## 2. End-to-end UI tests — Streamlit `AppTest`

Two personas are driven through the *actual app*, not just the logic, via Streamlit's testing
framework (`streamlit.testing.v1.AppTest`), which runs the real `app.py` headlessly and checks for
exceptions plus the expected conditional UI:

- **`apptest_smoke.py`** — has dependents, SIP with the step-up toggle turned on, high EMI burden,
  no health insurance: checks that the sole-earner/life-insurance checkboxes appear (dependents >
  0), the EMI high-interest checkbox appears (EMI > 0), the "Increase my SIP every year" checkbox
  appears in SIP mode and that ticking it reveals the step-up slider, the review page surfaces the
  emergency-fund-shortfall and no-insurance warnings, and the results page (including the new
  Portfolio-at-a-glance, net-worth, and wealth-over-time sections) renders with no exception.
  ```
  PASS: initial load, title: Build your plan around your life.
  PASS: moved to About you
  PASS: moved to Financial life
  PASS: moved to Money & goals
  PASS: moved to Risk comfort
  PASS: moved to Review
  PASS: moved to Results (final plan page)
  ALL APPTEST STEPS COMPLETED WITHOUT EXCEPTION.
  ```
- **`apptest_smoke2.py`** — no dependents, Lumpsum, Student: checks the *opposite* conditional
  branches are correctly hidden (no sole-earner/life-insurance checkboxes, no EMI checkbox, no
  step-up checkbox/slider for Lumpsum mode) and the results page still renders cleanly with a very
  different profile (High risk, short horizon).
  ```
  Checkboxes with 0 dependents (expect NO w_sole): ['w_has_ret']
  Checkboxes with EMI=0 (expect NO w_emi_high): []
  Sliders with Lumpsum mode (expect NO w_stepup): []
  PASS: branch 2 (no dependents, lumpsum, student) reached Results cleanly.
  ```

**Result: both branches pass, all conditional fields behave correctly, no exceptions.** Full
console output for both runs is in `apptest_output.txt`.

## 3. Manual / visual walkthrough — real screenshots

Captured from the actual running app (`streamlit run app.py`), driven with Playwright against a
live headless browser, not mocked up. Persona: 32-year-old, 1 dependent, salaried, Rs 80,000/month
income, Rs 40,000/month expenses, Rs 2,00,000 already in an emergency fund, Rs 15,000/month SIP
with the step-up toggle on, a "Vacation" goal plus retirement.

| # | Screenshot | What it shows |
|---|---|---|
| 1 | `screenshots/01_intro.png` | Landing step — the 5-step overview and "Build my plan" entry point, navy/blue theme |
| 2 | `screenshots/02_about_you.png` | Age, dependents, retirement goal toggle |
| 3 | `screenshots/03_financial_life.png` | Income/expenses, the new "Expected annual increase in your income" slider and its auto-computed expense-growth explanation, EMI, existing holdings, emergency fund |
| 4 | `screenshots/04_money_goals.png` | SIP/Lumpsum choice, amount, the new "Increase my SIP every year" toggle (step-up slider only appears once checked), the goals editor |
| 5 | `screenshots/05_risk_comfort.png` | Stated risk + the 3-question scenario quiz |
| 6 | `screenshots/06_review.png` | Final check before generating the plan |
| 7 | `screenshots/07_results_top.png` | Risk score, "Portfolio at a glance" headline metrics, **net worth today / projected net worth**, and the new **wealth-over-time line chart by age** |
| 8 | `screenshots/08_financial_foundation.png` | Financial-health scorecard, goals & timeline table (now with 9-asset-class equity share per goal) |
| 9 | `screenshots/09_allocation_mix.png` | Recommended overall mix — donut chart and table across all nine asset classes |
| 10 | `screenshots/10_why_this_fits.png` | Reasoning chips explaining the recommendation in plain English (bold text rendering verified) |
| 11 | `screenshots/11_expected_results_chart.png` | Per-goal weak/expected/optimistic scenario bar chart, action-plan tips |
| 12 | `screenshots/12_compare_alternatives.png` | Conservative / Moderate / Aggressive side-by-side with the allocation bar |
| 13 | `screenshots/13_tabs_goal_tracker.png` | "Goal tracker" tab — chance-of-reaching-target chart and the full scenario comparison table |

### A real bug found and fixed (earlier pass, still verified fixed)

While reviewing an earlier screenshot of the "Why this fits you" chips, they showed literal
`**double asterisks**` instead of bold text. Cause: `render_reasoning_chips()` in `app.py` wrapped
the fallback explanation's markdown bullets directly in HTML (`unsafe_allow_html=True`) without
converting `**bold**` markdown into `<b>` tags — and without escaping the text first, which was
also a latent HTML-injection risk if a user typed `<`/`>`/`&` into a goal name. Fixed by escaping
the bullet text and then converting `**bold**` to real `<b>` tags. Screenshot 10 above (re-captured
for this submission) confirms bold text still renders correctly after all the subsequent asset-
model and UI changes.

This is the kind of issue pure logic tests can't catch (the numbers behind `**bold**` were always
correct) and the automated `AppTest` checks didn't either (they check for exceptions and widget
presence, not rendered markup) — it only surfaced by actually looking at a screenshot, which is
exactly why this report includes real ones rather than a description of what the UI "should" show.

## 4. Live-demo artifact (bonus build)

The JS port (`logic.js`) was separately tested with 23 checks mirroring the Python test cases
(including a determinism check: identical inputs produce bit-identical output across repeated
runs), and the assembled wizard UI was smoke-tested end-to-end with jsdom across two branches (29
checks, covering every conditional field — including the SIP step-up toggle and income-growth
slider — plus the free-text AI agent's fallback path) — see the artifact's own `test_logic.js` /
`smoke_test.js` for that report, summarized in `AI_USE_DECLARATION.md`.
