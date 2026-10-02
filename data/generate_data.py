"""
Generates a small synthetic dataset for the Meridian semantic model, sized for
practice (not the real 60M rows) but deliberately engineered so every pattern
in the model has something real to bite into:

  - a distributor that changes territory mid-year   -> Type-2 SCD test
  - sales that cross the Apr-Mar fiscal year boundary -> fiscal calendar test
  - multiple currencies with diverging avg vs EOD rates -> currency calc group test
  - budget at month x category x region, actuals at day x SKU x customer -> grain mismatch test
  - a ragged 2-4 level management hierarchy -> parent-child PATH test
  - inventory snapshots with a clear "stock went up then down" curve -> semi-additive test
  - three RLS test users at different access levels -> RLS/OLS test

Run:  python generate_data.py
Output: CSVs in ./  (dim_*.csv, fact_*.csv) ready to import into Power BI
        Desktop via Get Data > Folder, or into SQLite for querying.
"""

import numpy as np
import pandas as pd

rng = np.random.default_rng(42)

# ---------------------------------------------------------------- Dim Date
dates = pd.date_range("2024-04-01", "2026-03-31", freq="D")  # 2 full fiscal years
dim_date = pd.DataFrame({"Date": dates})
dim_date["DateKey"] = dim_date["Date"].dt.strftime("%Y%m%d").astype(int)
dim_date["CalendarYear"] = dim_date["Date"].dt.year
dim_date["CalendarMonth"] = dim_date["Date"].dt.month
dim_date["CalendarMonthName"] = dim_date["Date"].dt.strftime("%B")
dim_date["CalendarQuarter"] = dim_date["Date"].dt.quarter


def fiscal_year(d):
    # FY2025 = Apr 2024 - Mar 2025
    return d.year if d.month >= 4 else d.year - 1


def fiscal_month_number(d):
    # 1 = April ... 12 = March
    return ((d.month - 4) % 12) + 1


dim_date["FiscalYear"] = dim_date["Date"].apply(lambda d: fiscal_year(d) + 1)
dim_date["FiscalMonthNumber"] = dim_date["Date"].apply(fiscal_month_number)
dim_date["FiscalQuarter"] = ((dim_date["FiscalMonthNumber"] - 1) // 3) + 1
dim_date["IsFiscalYearEnd"] = (dim_date["Date"].dt.month == 3) & (dim_date["Date"].dt.day == 31)
dim_date.to_csv("dim_date.csv", index=False)

# ------------------------------------------------------------- Dim Currency
dim_currency = pd.DataFrame(
    {
        "CurrencyKey": [1, 2, 3, 4, 5],
        "CurrencyCode": ["USD", "GBP", "EUR", "INR", "AED"],
        "CurrencyName": ["US Dollar", "British Pound", "Euro", "Indian Rupee", "UAE Dirham"],
    }
)
dim_currency.to_csv("dim_currency.csv", index=False)

# ---------------------------------------------------------- Fact ExchangeRate
# Deliberately divergent avg-vs-EOD rates mid-period so the currency calc
# group items produce visibly different numbers, not near-identical ones.
base_rate = {1: 1.00, 2: 1.27, 3: 1.08, 4: 0.012, 5: 0.272}  # to USD
rows = []
for d in dates:
    for ck, base in base_rate.items():
        drift = 1 + 0.08 * np.sin((d - dates[0]).days / 45.0)  # wobble over ~quarter cycles
        eod = base * drift
        rows.append({"RateDateKey": int(d.strftime("%Y%m%d")), "CurrencyKey": ck, "RateToUSD_EOD": round(eod, 5)})
fact_fx = pd.DataFrame(rows)
# monthly average = mean of EOD within each (currency, month)
fact_fx["ym"] = fact_fx["RateDateKey"] // 100
monthly_avg = fact_fx.groupby(["CurrencyKey", "ym"])["RateToUSD_EOD"].transform("mean")
fact_fx["RateToUSD_MonthAvg"] = monthly_avg.round(5)
fact_fx = fact_fx.drop(columns="ym")
fact_fx.to_csv("fact_exchangerate.csv", index=False)

# --------------------------------------------------------- Dim Geography
dim_geo = pd.DataFrame(
    {
        "RegionKey": [1, 2, 3, 4, 5],
        "RegionName": ["North", "South", "East", "West", "International"],
        "Country": ["US", "US", "UK", "Germany", "UAE"],
    }
)
dim_geo.to_csv("dim_geography.csv", index=False)

# ---------------------------------------------------------- Dim Product
categories = ["Refrigerators", "Ovens", "Dishwashers", "Washing Machines", "Small Appliances"]
products = []
pk = 1
for cat in categories:
    for i in range(1, 9):  # 8 SKUs per category = 40 SKUs
        products.append({"ProductKey": pk, "ProductCategoryKey": categories.index(cat) + 1,
                          "ProductCategory": cat, "ProductName": f"{cat[:-1]} Model {i}", "SKU": f"{cat[:3].upper()}-{i:03d}"})
        pk += 1
dim_product = pd.DataFrame(products)
dim_product.to_csv("dim_product.csv", index=False)

# --------------------------------------------------------- Dim Employee
# Ragged parent-child: a Director, under them 2 Regional Managers, one of
# whom has Team Leads with Reps underneath (deep branch), the other has
# Reps reporting directly (shallow branch) -- that raggedness is the point.
employees = [
    {"EmployeeKey": 1, "ManagerKey": None, "EmployeeName": "Dana Director", "Title": "Director"},
    {"EmployeeKey": 2, "ManagerKey": 1, "EmployeeName": "Raj RegionalMgr (Deep Branch)", "Title": "Regional Manager"},
    {"EmployeeKey": 3, "ManagerKey": 1, "EmployeeName": "Sam RegionalMgr (Shallow Branch)", "Title": "Regional Manager"},
    {"EmployeeKey": 4, "ManagerKey": 2, "EmployeeName": "Tina TeamLead", "Title": "Team Lead"},
    {"EmployeeKey": 5, "ManagerKey": 4, "EmployeeName": "Rep A", "Title": "Sales Rep"},
    {"EmployeeKey": 6, "ManagerKey": 4, "EmployeeName": "Rep B", "Title": "Sales Rep"},
    {"EmployeeKey": 7, "ManagerKey": 3, "EmployeeName": "Rep C (reports direct to Regional Mgr)", "Title": "Sales Rep"},
    {"EmployeeKey": 8, "ManagerKey": 3, "EmployeeName": "Rep D (reports direct to Regional Mgr)", "Title": "Sales Rep"},
]
dim_employee = pd.DataFrame(employees)
dim_employee.to_csv("dim_employee.csv", index=False)

# --------------------------------------------------------- Dim Customer (Type-2 SCD)
# 30 distributors. Distributor #7 ("Distributor_07") explicitly changes
# territory mid-year (North -> South) on 2025-07-01, producing two SCD rows
# with the same business key and non-overlapping Effective/Expiry dates.
customer_rows = []
sk = 1
for i in range(1, 31):
    bk = f"DIST-{i:03d}"
    region = dim_geo["RegionKey"].iloc[(i - 1) % 5]
    if i == 7:
        # original row: North (RegionKey 1), effective from start, expires at the move date
        customer_rows.append({
            "CustomerSK": sk, "CustomerBK": bk, "CustomerName": f"Distributor_{i:02d}",
            "TerritoryKey": 1, "AccountManagerKey": 5, "EffectiveDate": "2024-04-01",
            "ExpiryDate": "2025-06-30", "IsCurrent": False,
        })
        sk += 1
        # new row: moved to South (RegionKey 2), current from the move date onward
        customer_rows.append({
            "CustomerSK": sk, "CustomerBK": bk, "CustomerName": f"Distributor_{i:02d}",
            "TerritoryKey": 2, "AccountManagerKey": 7, "EffectiveDate": "2025-07-01",
            "ExpiryDate": "2099-12-31", "IsCurrent": True,
        })
        sk += 1
    else:
        customer_rows.append({
            "CustomerSK": sk, "CustomerBK": bk, "CustomerName": f"Distributor_{i:02d}",
            "TerritoryKey": int(region), "AccountManagerKey": int(rng.choice([5, 6, 7, 8])),
            "EffectiveDate": "2024-04-01", "ExpiryDate": "2099-12-31", "IsCurrent": True,
        })
        sk += 1
dim_customer = pd.DataFrame(customer_rows)
dim_customer.to_csv("dim_customer.csv", index=False)

# --------------------------------------------------------- Dim Warehouse
dim_warehouse = pd.DataFrame({"WarehouseKey": [1, 2, 3], "WarehouseName": ["US-East DC", "EU DC", "Gulf DC"]})
dim_warehouse.to_csv("dim_warehouse.csv", index=False)

# ----------------------------------------------------- Security_UserRegion
security = pd.DataFrame([
    {"UserPrincipalName": "regionalmanager.north@meridian.com", "RegionKey": 1, "AccountKey": None, "Role": "RegionalManager"},
    {"UserPrincipalName": "keyaccount.manager@meridian.com", "RegionKey": None, "AccountKey": "DIST-003", "Role": "KeyAccountManager"},
    {"UserPrincipalName": "director@meridian.com", "RegionKey": None, "AccountKey": None, "Role": "Director"},
])
security.to_csv("security_userregion.csv", index=False)

# --------------------------------------------------------------- Fact Sales
# One row per order line. Each order gets an order date, a ship date
# (+1 to +5 days later) and an invoice date (+1 further day) so the
# role-playing date measures produce genuinely different period totals.
current_customer_by_bk = {}  # resolve which CustomerSK is "current" on a given order date
cust_lookup = dim_customer.copy()
cust_lookup["EffectiveDate"] = pd.to_datetime(cust_lookup["EffectiveDate"])
cust_lookup["ExpiryDate"] = pd.to_datetime(cust_lookup["ExpiryDate"])


def resolve_customer_sk(bk, order_date):
    rows = cust_lookup[cust_lookup["CustomerBK"] == bk]
    match = rows[(rows["EffectiveDate"] <= order_date) & (order_date <= rows["ExpiryDate"])]
    return int(match.iloc[0]["CustomerSK"])


n_orders = 6000
order_dates = rng.choice(dates[:-7], size=n_orders)  # leave room for ship/invoice offsets
customer_bks = rng.choice(dim_customer["CustomerBK"].unique(), size=n_orders)
product_keys = rng.choice(dim_product["ProductKey"].values, size=n_orders)
employee_keys = rng.choice([5, 6, 7, 8], size=n_orders)  # reps only, not managers
currency_keys = rng.choice(dim_currency["CurrencyKey"].values, size=n_orders, p=[0.35, 0.15, 0.15, 0.25, 0.10])

sales_rows = []
for i in range(n_orders):
    order_date = pd.Timestamp(order_dates[i])
    ship_date = order_date + pd.Timedelta(days=int(rng.integers(1, 6)))
    invoice_date = ship_date + pd.Timedelta(days=int(rng.integers(1, 3)))
    bk = customer_bks[i]
    customer_sk = resolve_customer_sk(bk, order_date)
    qty = int(rng.integers(1, 20))
    unit_price = round(float(rng.uniform(80, 1200)), 2)
    gross = round(qty * unit_price, 2)
    returns = round(gross * rng.choice([0, 0, 0, 0.05, 0.1]), 2)
    rebates = round(gross * rng.uniform(0.01, 0.04), 2)
    cost = round(gross * rng.uniform(0.55, 0.7), 2)
    sales_rows.append({
        "OrderLineKey": i + 1,
        "OrderDateKey": int(order_date.strftime("%Y%m%d")),
        "ShipDateKey": int(ship_date.strftime("%Y%m%d")),
        "InvoiceDateKey": int(invoice_date.strftime("%Y%m%d")),
        "CustomerKey": customer_sk,
        "ProductKey": int(product_keys[i]),
        "EmployeeKey": int(employee_keys[i]),
        "CurrencyKey": int(currency_keys[i]),
        "GrossAmountLocal": gross,
        "ReturnsAmountLocal": returns,
        "RebatesAmountLocal": rebates,
        "Quantity": qty,
        "CostLocal": cost,
    })
fact_sales = pd.DataFrame(sales_rows)
fact_sales.to_csv("fact_sales.csv", index=False)

# ------------------------------------------------------- Fact Budget
# Deliberately coarse grain: fiscal month x category x region, in USD only.
# Covers the same 2 fiscal years as Fact Sales.
budget_rows = []
fiscal_months = dim_date[["FiscalYear", "FiscalMonthNumber"]].drop_duplicates().reset_index(drop=True)
# map each fiscal month back to a representative DateKey (first day of that fiscal month)
fm_to_datekey = (
    dim_date.sort_values("DateKey")
    .drop_duplicates(subset=["FiscalYear", "FiscalMonthNumber"])
    .set_index(["FiscalYear", "FiscalMonthNumber"])["DateKey"]
)
for _, fm in fiscal_months.iterrows():
    datekey = int(fm_to_datekey.loc[(fm["FiscalYear"], fm["FiscalMonthNumber"])])
    for cat_key in range(1, 6):
        for region_key in dim_geo["RegionKey"]:
            budget_rows.append({
                "FiscalMonthKey": datekey,
                "ProductCategoryKey": cat_key,
                "RegionKey": int(region_key),
                "BudgetAmountUSD": round(float(rng.uniform(15000, 60000)), 2),
            })
fact_budget = pd.DataFrame(budget_rows)
fact_budget.to_csv("fact_budget.csv", index=False)

# ------------------------------------------------ Fact Inventory Snapshot
# Daily snapshot per product x warehouse, with a visible seasonal sawtooth
# (stock replenished monthly, drawn down daily) so SUM-across-dates is
# obviously wrong and CLOSINGBALANCE is obviously right.
inv_rows = []
for wk in dim_warehouse["WarehouseKey"]:
    for pk_ in dim_product["ProductKey"].sample(15, random_state=wk):  # subset of SKUs per warehouse
        stock = int(rng.integers(200, 500))
        for d in dates:
            if d.day == 1:
                stock += int(rng.integers(150, 300))  # monthly replenishment
            draw = int(rng.integers(0, 12))
            stock = max(stock - draw, 0)
            inv_rows.append({
                "SnapshotDateKey": int(d.strftime("%Y%m%d")),
                "ProductKey": int(pk_),
                "WarehouseKey": int(wk),
                "QuantityOnHand": stock,
            })
fact_inventory = pd.DataFrame(inv_rows)
fact_inventory.to_csv("fact_inventory_snapshot.csv", index=False)

print("Generated:")
for name, df in [
    ("dim_date", dim_date), ("dim_currency", dim_currency), ("dim_geography", dim_geo),
    ("dim_product", dim_product), ("dim_employee", dim_employee), ("dim_customer", dim_customer),
    ("dim_warehouse", dim_warehouse), ("security_userregion", security),
    ("fact_exchangerate", fact_fx), ("fact_sales", fact_sales), ("fact_budget", fact_budget),
    ("fact_inventory_snapshot", fact_inventory),
]:
    print(f"  {name:28s} {len(df):>8,} rows")
