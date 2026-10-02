# Loading the practice dataset into Power BI Desktop

This folder has synthetic CSVs matching the schema in
[../model/tables.md](../model/tables.md) — small enough to practice with
(6,000 sales rows, 2 fiscal years) but deliberately engineered so every
pattern in the case study has a real scenario to test against:

| File | What's engineered into it |
|---|---|
| `dim_customer.csv` | `DIST-007` has two rows, same business key, non-overlapping date ranges — North until 2025-06-30, South from 2025-07-01. This is your Type-2 SCD test case. |
| `fact_sales.csv` | Each order's `CustomerKey` already resolves to whichever SCD row was current on the order date — confirm this yourself (see "Things to verify" below) rather than trusting it blindly. |
| `fact_inventory_snapshot.csv` | A visible sawtooth (replenish monthly, drawn down daily). `SUM(QuantityOnHand)` across a year is nonsense; `CLOSINGBALANCE` on the last date is correct. |
| `dim_employee.csv` | A deliberately ragged hierarchy: one branch is Director → Regional Mgr → Team Lead → Rep (4 levels), the other is Director → Regional Mgr → Rep (3 levels, skips Team Lead). |
| `fact_budget.csv` | Fiscal-month × category × region grain — coarser than `fact_sales` (day × SKU × customer). Drilling to a single SKU should blank out, not fabricate a number. |
| `fact_exchangerate.csv` | Monthly-average and month-end rates deliberately diverge (sinusoidal drift) so the two currency calc-group items give visibly different answers, not near-identical ones. |
| `security_userregion.csv` | Three test identities: a Regional Manager (North only), a Key Account Manager (one distributor only), a Director (unrestricted). |

Regenerate anytime with `python generate_data.py` (uses a fixed random seed,
so output is reproducible unless you change the script).

## 1. Import

Power BI Desktop → **Get Data → Folder** → point at this `data/` folder →
**Transform Data**, then in Power Query confirm each file loaded with the
right types (dates as Date, keys as Whole Number) before loading into the
model. Loading each CSV as its own query (not combined into one table) is
what you want — Folder import sometimes tries to auto-combine same-shaped
files; decline that and load them as separate tables.

## 2. Mark the date table

`Dim Date` → Table Tools → **Mark as Date Table** → key column `Date`.
Without this, `DATESYTD`, `DATEADD`, `CLOSINGBALANCE` etc. either error or
silently misbehave.

## 3. Build relationships

Follow [../model/relationships.md](../model/relationships.md) exactly —
in particular:
- `Fact Sales[OrderDateKey] -> Dim Date[DateKey]` **active**;
  `ShipDateKey`/`InvoiceDateKey` relationships **inactive** (Power BI
  defaults a table's 2nd+ relationship to the same column as inactive
  automatically — just confirm it, don't delete it).
- `Fact Sales[CustomerKey] -> Dim Customer[CustomerSK]` (the surrogate key,
  **not** `CustomerBK`).
- No relationship between `Fact Budget` and `Fact Sales` directly — both
  relate independently to `Dim Date`, `Dim Product`, `Dim Geography`.

## 4. Paste in the measures

Paste each file under `../dax/` in as a New Measure, in this order (later
ones reference earlier ones):
1. `measures_core.dax`
2. `measures_date_roles.dax`
3. `measures_inventory.dax`
4. `measures_budget_vs_actual.dax`

## 5. Calculation groups (requires Tabular Editor)

Power BI Desktop's own UI doesn't expose calculation groups — use the free
**Tabular Editor 2** (community edition, via External Tools ribbon once
installed) to add them from `calc_group_time.dax` and
`calc_group_currency.dax`. Each file's comments tell you the calculation
items to create and their DAX expressions.

## 6. Parent-child hierarchy

`hierarchy_parent_child.dax` has calculated *columns* (not measures) — add
`EmployeePath`, `EmployeePathLength`, `Level 1 (Top)` through `Level 4` as
new columns on `Dim Employee`, then build a Hierarchy in the field list from
those four Level columns. The `Team Net Revenue` measure goes in afterward.

## 7. RLS roles

Modeling → **Manage Roles** → create `Regional Manager`, `Key Account
Manager`, `Director` exactly as described in
[../security/rls_roles.md](../security/rls_roles.md), referencing
`security_userregion.csv`. Test with **View As** using the three UPNs in
that CSV. OLS (hiding Cost/Margin) needs Tabular Editor — see
[../security/ols_notes.md](../security/ols_notes.md).

## Things to verify yourself (don't take the generator's word for it)

This is the point of practicing with real data instead of just reading the
DAX — go confirm these rather than assuming the dataset is correct:

1. Filter `Dim Customer` to `DIST-007`, add `[Net Revenue]` sliced by
   fiscal month. Confirm sales in May 2025 attribute to **North**
   and sales in August 2025 attribute to **South** — i.e. the Type-2 SCD
   actually changes which territory a rep's sales roll up into, at the
   right point in time.
2. Put `[Closing Stock (CLOSINGBALANCE)]` next to a plain
   `SUM(QuantityOnHand)` on a visual for one product/warehouse, filtered to
   a full fiscal year. Confirm they're wildly different and explain *why*
   in your own words.
3. Build a matrix: Budget Amount (Grain-Safe) and Actuals, rows = Product
   Category, then drill rows down to individual Product (SKU). Confirm
   Budget blanks out at SKU level instead of showing a number.
4. Build the Management Chain hierarchy on rows, `[Team Net Revenue]` as
   the measure. Confirm the 3-level branch (Rep C, Rep D under Sam
   directly) and the 4-level branch (Rep A, Rep B under Tina under Raj)
   both roll up correctly despite different depths.
5. **View As** each of the three RLS roles and confirm what each one can
   and can't see — including that Cost/Margin disappear once OLS is wired
   up, not just that rows are filtered.
