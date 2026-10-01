# Meridian Appliances — Governed Semantic Model

## The problem

Meridian sells through ~400 distributors and its own online store in 5 countries (US, UK,
Germany, India, UAE). Sales and Finance each built their own Power BI file with their own
revenue logic:

- **Sales**: gross order value, by order date, converted at *today's* FX rate
- **Finance**: net invoiced revenue (after returns/rebates), by ship date, at the
  *monthly average* FX rate

Result: 12% vs 7% YoY growth reported in the same meeting, from the same 60M-row table.
Nobody can trust a number because every report contains its own business logic.

## The fix

One governed semantic model (SSAS Tabular / shared Power BI semantic model). Reports are
thin — they drag in published measures, no DAX of their own. Every requirement below maps
to a specific modeling pattern; the point of this repo is to make each pattern explicit and
reusable rather than reinvented per report.

## Map of requirements → patterns

| # | Stakeholder ask | Pattern | Where |
|---|---|---|---|
| 1 | One revenue number, defined once | Central measure table, documented + folder-organized | [dax/measures_core.dax](dax/measures_core.dax) |
| 2 | Order date vs. ship date | Role-playing date dimension, inactive relationships + `USERELATIONSHIP` | [model/relationships.md](model/relationships.md), [dax/measures_date_roles.dax](dax/measures_date_roles.dax) |
| 3 | Fiscal Apr–Mar, YTD/PY/YoY/R12 | Custom fiscal calendar + time-intelligence calculation group | [dax/calc_group_time.dax](dax/calc_group_time.dax) |
| 4 | Local currency vs. USD, avg vs. month-end rate | Exchange-rate fact + currency calculation group | [dax/calc_group_currency.dax](dax/calc_group_currency.dax) |
| 5 | Actuals vs. budget, mismatched grain | Mixed-grain fact design, `TREATAS` + `ISINSCOPE` allocation | [model/tables.md](model/tables.md), [dax/measures_budget_vs_actual.dax](dax/measures_budget_vs_actual.dax) |
| 6 | Quarter-end stock, days of cover | Semi-additive measures (`CLOSINGBALANCE`) | [dax/measures_inventory.dax](dax/measures_inventory.dax) |
| 7 | Distributor moves territory | Type-2 slowly changing dimension on Customer | [model/tables.md](model/tables.md) |
| 8 | Rep performance roll-up | Ragged parent-child hierarchy, flattened with `PATH` | [dax/hierarchy_parent_child.dax](dax/hierarchy_parent_child.dax) |
| 9 | Row-level + object-level security | Dynamic RLS via `USERPRINCIPALNAME()` + mapping table; OLS on cost/margin | [security/rls_roles.md](security/rls_roles.md), [security/ols_notes.md](security/ols_notes.md) |
| 10 | 60M rows, 2-hr window, <3s dashboards | Monthly partitions, incremental refresh, VertiPaq tuning | [refresh/partitioning_strategy.md](refresh/partitioning_strategy.md) |

## How to use this repo

1. Read [model/tables.md](model/tables.md) first — it defines the star schema every measure
   and relationship below assumes.
2. [model/relationships.md](model/relationships.md) explains which relationships are active
   vs. inactive and why.
3. The `dax/` files are meant to be pasted into Tabular Editor or a Power BI semantic model
   against tables matching the schema in `model/tables.md`. They're real DAX, not pseudocode,
   but column/table names will need to match your actual source once real data is connected.
4. `security/` and `refresh/` are operational design docs, not code — RLS roles and
   partition/refresh policy are configured in the service, not written as DAX.

## Design principles this model follows

- **No logic in reports.** Every number a report shows is a published measure. A report
  that computes "Revenue - Cost" inline is a bug, not a convenience.
- **One fact, many roles.** Don't duplicate fact tables to get "order date view" vs "ship
  date view" — one relationship is active, the rest are activated per-measure.
- **Calculation groups over measure explosion.** 5 base measures × (YTD, PY, YoY%, R12) ×
  (local, USD) should not become 50+ physical measures. Two calculation groups collapse
  that combinatorial growth to ~10 measures total.
- **History is immutable.** A distributor's past sales stay attributed to the territory
  they were in at the time (Type-2 SCD), not retroactively reassigned.
- **Grain mismatches are made visible, not hidden.** Budget-vs-actual blanks out below
  budget's native grain unless an explicit allocation rule is defined — it never silently
  divides budget evenly across SKUs.
