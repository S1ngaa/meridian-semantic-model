# Relationships

## Role-playing date dimension (requirement #2)

`Fact Sales` has three date foreign keys but relates to a **single physical** `Dim Date`
table three times:

```
Fact Sales[OrderDateKey]   -> Dim Date[DateKey]   ACTIVE
Fact Sales[ShipDateKey]    -> Dim Date[DateKey]   INACTIVE
Fact Sales[InvoiceDateKey] -> Dim Date[DateKey]   INACTIVE
```

Why not three separate date tables (`Dim Order Date`, `Dim Ship Date`, `Dim Invoice Date`)?
Because then a slicer on fiscal year has to be built three times, time-intelligence
calculation groups have to be applied three times, and "this month" can silently mean
three different things depending which copy a report author dragged in. One date table,
one relationship active by default (order date — matches the most common slicing need),
and the other two activated explicitly inside a measure via `USERELATIONSHIP`:

```DAX
Net Revenue (Ship Date) =
CALCULATE (
    [Net Revenue],
    USERELATIONSHIP ( 'Fact Sales'[ShipDateKey], 'Dim Date'[DateKey] )
)
```

Sales VP's default reports use `[Net Revenue]` (order date, active relationship).
Finance's default reports use `[Net Revenue (Ship Date)]`. Same measure logic underneath
— only the date context differs. See [dax/measures_date_roles.dax](../dax/measures_date_roles.dax).

## Fact Budget to Fact Sales: no direct relationship

Budget and Actuals are never related to each other directly — they're both related to
the *same conformed dimensions* at whatever grain each supports:

```
Fact Budget[FiscalMonthKey]     -> Dim Date[DateKey]            (month-level keys only)
Fact Budget[ProductCategoryKey] -> Dim Product[ProductCategoryKey]
Fact Budget[RegionKey]          -> Dim Geography[RegionKey]

Fact Sales[OrderDateKey]  -> Dim Date[DateKey]
Fact Sales[ProductKey]    -> Dim Product[ProductKey]
Fact Sales[CustomerKey]   -> Dim Customer[CustomerSK] -> Dim Customer[TerritoryKey] -> Dim Geography
```

Comparing them is done in DAX at query time (`TREATAS`), not via a modeled relationship —
see [dax/measures_budget_vs_actual.dax](../dax/measures_budget_vs_actual.dax). A physical
relationship would force a fake shared grain (e.g. duplicating budget down to SKU level),
which fabricates precision the budget never had.

## Dim Customer: Fact Sales joins on the surrogate key, never the business key

```
Fact Sales[CustomerKey] -> Dim Customer[CustomerSK]   ACTIVE, single relationship
```

There's exactly one active relationship here. The Type-2 SCD logic is resolved once,
at ETL/load time, by stamping each sales row with the `CustomerSK` that was `IsCurrent`
on the order date — not resolved per-query. This keeps the model fast (no date-ranged
join logic at query time) and keeps "which territory did this sale belong to" a stable,
auditable fact rather than something that could be recomputed differently in different
reports.

## Dim Employee: self-join, not modeled as a relationship

The manager hierarchy (`ManagerKey -> EmployeeKey`) is a **self-referencing relationship
inside one table** — Tabular doesn't support this as an active model relationship for
filtering, so it's resolved with `PATH()` inside DAX measures instead. See
[dax/hierarchy_parent_child.dax](../dax/hierarchy_parent_child.dax).
