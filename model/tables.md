# Star Schema

Grain is stated explicitly for every fact table — mismatched grain between Actuals and
Budget is the whole point of requirement #5, so it must be designed in, not discovered late.

## Fact tables

### Fact Sales (grain: one row per order line)
```
OrderLineKey        (surrogate PK)
OrderDateKey         -> Dim Date (role: Order)
ShipDateKey          -> Dim Date (role: Ship)
InvoiceDateKey       -> Dim Date (role: Invoice)
CustomerKey          -> Dim Customer  (Type-2 surrogate key, NOT the natural/business key)
ProductKey           -> Dim Product
EmployeeKey          -> Dim Employee  (sales rep)
CurrencyKey          -> Dim Currency
GrossAmountLocal      decimal   -- gross order value, local currency
ReturnsAmountLocal    decimal
RebatesAmountLocal    decimal
Quantity              int
CostLocal             decimal   -- for margin; subject to OLS
```
~60M rows, +1.5M/month. Partitioned by OrderDateKey (monthly).

### Fact Inventory Snapshot (grain: one row per product × warehouse × day)
```
SnapshotDateKey      -> Dim Date
ProductKey           -> Dim Product
WarehouseKey         -> Dim Warehouse
QuantityOnHand        int   -- semi-additive: sum across products/warehouses OK,
                              sum across dates is NOT (use CLOSINGBALANCE)
```

### Fact Budget (grain: one row per month × category × region — coarser than Actuals)
```
FiscalMonthKey       -> Dim Date (fiscal month grain only, not day)
ProductCategoryKey   -> Dim Product (category level only, not SKU)
RegionKey            -> Dim Geography (region level only, not customer)
BudgetAmountUSD       decimal   -- budget is stored pre-converted; no local-currency budget
```
This table is deliberately NOT at the same grain as Fact Sales. See
[dax/measures_budget_vs_actual.dax](../dax/measures_budget_vs_actual.dax) for how the model
reconciles the two grains instead of forcing a fake common grain.

### Fact ExchangeRate (grain: one row per day × currency)
```
RateDateKey          -> Dim Date
CurrencyKey          -> Dim Currency
RateToUSD_EOD         decimal   -- month-end rate (for stock valuation)
RateToUSD_MonthAvg    decimal   -- monthly average rate (for P&L/sales)
```

## Dimension tables

### Dim Date
Standard date dimension PLUS a custom fiscal calendar (FY = April–March):
```
DateKey (yyyymmdd int, PK)
Date
CalendarYear, CalendarMonth, CalendarMonthName, CalendarQuarter
FiscalYear            -- FY2026 = Apr 2025–Mar 2026
FiscalQuarter         -- FQ1..FQ4, FQ1 starts April
FiscalMonthNumber      1..12, 1 = April
IsFiscalYearEnd
```
One physical Dim Date. Fact Sales relates to it three times (Order/Ship/Invoice) —
see [relationships.md](relationships.md) for why only one is active.

### Dim Customer (Type-2 SCD — see requirement #7)
```
CustomerSK           (surrogate PK, changes on every tracked change)
CustomerBK           (business key, stable — the real-world distributor ID)
CustomerName
TerritoryKey         -> Dim Territory   -- the field that changes (North -> South)
AccountManagerKey    -> Dim Employee
EffectiveDate
ExpiryDate            -- far-future sentinel for the current row (conventionally
                      -- 9999-12-31; the practice dataset in data/ uses 2099-12-31
                      -- since pandas' datetime64[ns] can't represent year 9999 —
                      -- Power BI/DAX itself has no such limit)
IsCurrent             boolean
```
Fact Sales always joins on `CustomerSK`, resolved at load time to whichever surrogate
key was current on the order date. This is what keeps July's North-territory sales in
North even after the distributor moves to South in August.

### Dim Employee (ragged parent-child — see requirement #8)
```
EmployeeKey          (surrogate PK)
EmployeeName
ManagerKey           -> Dim Employee.EmployeeKey (self-referencing, nullable at the top)
Title
```
Hierarchy depth varies by region (ragged) — flattened at query time with `PATH`, not
modeled as fixed Level1/Level2/Level3 columns.

### Dim Product, Dim Geography/Territory, Dim Currency, Dim Warehouse
Standard conformed dimensions. Dim Product includes `ProductCategoryKey` so Fact Budget
(category grain) and Fact Sales (SKU grain) both roll up through the same hierarchy.

### Security_UserRegion (mapping table, not a dimension — see requirement #9)
```
UserPrincipalName     -- matches AD UPN from USERPRINCIPALNAME()
RegionKey             -> Dim Geography   (nullable: NULL = all regions, for directors+)
AccountKey            -> Dim Customer    (nullable: key-account managers scoped to accounts)
Role                  -- 'RegionalManager' | 'KeyAccountManager' | 'Director'
```

## Why Fact Sales stores local-currency amounts, not USD

Converting at load time would hardcode "today's rate" into history, which is exactly the
bug that caused the Sales/Finance mismatch in the first place (requirement description:
Sales converts "at today's exchange rate"). Storing local amounts + a separate rate table
lets the currency calculation group apply the *correct* rate for the context — monthly
average for P&L, month-end for balance-sheet/stock — without ever re-stating a historical
local-currency fact.
