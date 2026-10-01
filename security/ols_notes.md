# Object-Level Security (requirement #9, cost/margin clause)

"Nobody below director sees cost or margin" is an **object**-level restriction (hide a
column/measure entirely), which RLS (row filtering) cannot do — RLS can only filter
*rows*, not hide *fields*. A regional manager under RLS alone would still see the `Cost`
and `Margin` measures, just computed over their own region's rows. OLS is required on
top of RLS.

## Implementation

OLS is not available in Power BI Desktop's UI directly — it's set via **Tabular Editor**
(or the XMLA endpoint / TOM) by setting `IsHidden` per-role via a permissions perspective,
or via **Object-Level Security** roles in Tabular Editor's "Roles" pane:

For each role that should NOT see cost/margin (Regional Manager, Key Account Manager —
i.e. everyone except Director+):
```
Table: _Measures
  [Cost]      -> Metadata Permission: None (or IsHidden for that role)
  [Margin]    -> Metadata Permission: None
  [Margin %]  -> Metadata Permission: None

Table: Fact Sales
  [CostLocal] -> Metadata Permission: None
```

With "Metadata Permission: None," the object doesn't just filter to blank — it does not
exist for that role: it's absent from the field list, absent from any visual built with
it (the visual errors/removes the field), and absent from XMLA-level queries (e.g. a
Power BI report connected live, or Excel PivotTable, or a custom app querying the
model). This is stronger than hiding a field in a report's visual — a restricted user
could otherwise just go find the raw field in a different report or in Analyze in Excel.

## Director role

Director (and any role explicitly marked unrestricted in `Security_UserRegion`) has
"Metadata Permission: Read" on Cost/Margin — normal visibility.

## Why not just hide the columns from everyone and expose via a separate "Finance"
model

Considered and rejected: that's two semantic models, which immediately reintroduces the
"two sources of truth" problem this whole project exists to kill. One model, OLS per
role, is the only approach consistent with the CFO's mandate ("one governed semantic
model that every report connects to").
