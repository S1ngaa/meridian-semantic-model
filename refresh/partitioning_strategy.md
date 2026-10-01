# Partitioning, Incremental Refresh, and VertiPaq Tuning (requirement #10)

Constraints: 60M rows today, +1.5M/month, a 2-hour nightly refresh window,
dashboards must load in under 3 seconds.

## Partitioning

`Fact Sales` is partitioned **monthly** by `OrderDateKey`. At 1.5M rows/month, each
partition is small enough to process independently and in parallel.

```
Fact Sales_202401, Fact Sales_202402, ... Fact Sales_202510 (current month)
```

`Fact Inventory Snapshot` likewise partitions monthly by `SnapshotDateKey` — it grows
daily (product x warehouse x day) and old snapshots never change once the day has
closed.

## Incremental refresh policy

Only recent partitions are reprocessed nightly; history is "frozen" and skipped:

```
Refresh rows from the last:      3 months   (RangeStart)
Archive/retain rows from:        all history (RangeEnd = far future)
Detect data changes column:      Fact Sales[LastModifiedDate] (if source exposes it)
```

- **Current + prior 2 months**: fully reprocessed every night. Covers late order
  corrections, returns posted against last month's orders, rebate adjustments.
- **Everything older**: never touched by the nightly job. A 60M-row table with monthly
  partitions means a nightly refresh only ever touches ~3 of ~60+ partitions —
  independent of total history size, which is what keeps the refresh bounded as the
  table keeps growing past 60M rows.
- If source data is ever corrected further back than 3 months (rare: an audit
  adjustment), that's a manual, logged full-partition reprocess of the specific
  affected month(s) — not a nightly behavior.

This is the only way a fixed 2-hour window survives +1.5M rows/month forever: refresh
cost is bounded by "recent months," not by "total table size."

## VertiPaq tuning checklist

- **Cardinality**: `CustomerBK` (natural key, long alphanumeric) is never used in
  relationships — only the compact integer `CustomerSK` is. High-cardinality text
  columns used in relationships are the single biggest VertiPaq compression killer.
- **Unused columns dropped**: don't import source columns "just in case." Every column
  in `Fact Sales` must be either a key, a measure input, or explicitly requested by a
  stakeholder. Columns like free-text order notes stay in the source system, not the
  model.
- **Integer surrogate keys everywhere**: all fact-to-dimension joins use integer
  surrogate keys (`CustomerSK`, `ProductKey`, `EmployeeKey`, `DateKey` as `yyyymmdd`
  int), never GUIDs or strings — integers compress and join far better in VertiPaq.
- **Sort order on load**: source extract sorted by the column with the most repeated
  consecutive values (commonly `ProductKey` or `DateKey`) before load — VertiPaq's
  run-length encoding compresses much better on pre-sorted data.
- **No bi-directional relationships** on the high-volume fact tables — bi-directional
  filtering is a common cause of slow queries and ambiguous filter propagation at this
  scale; every `Fact Sales` relationship is single-direction.
- **Avoid calculated columns on the fact table** — `EmployeePath`/`PathLength`/`Level N`
  are calculated columns on `Dim Employee` (small table, fine). Nothing equivalent is
  ever added to `Fact Sales` — calculated columns on a 60M-row table bloat processing
  time and storage; push any such logic to the ETL layer or to measures instead.
- **Aggregations table** (if <3s is still not met after the above): a pre-aggregated
  `Fact Sales_Agg` at month x category x region grain, set as a Power BI aggregation
  behind the detail table — dashboards hitting summary-level visuals hit the small
  aggregation table transparently; only drill-to-detail hits the 60M-row table.

## Load window budget (illustrative)

```
00:00  Nightly job starts
00:00-00:10  Process 3 recent monthly partitions, Fact Sales      (parallel)
00:10-00:15  Process current partition, Fact Inventory Snapshot
00:15-00:20  Process Fact ExchangeRate, Fact Budget (small, full reload — low volume)
00:20-00:25  Process Type-2 SCD updates to Dim Customer
00:25-00:30  Recalculate affected aggregation tables
00:30        Done — well inside the 2-hour window, with headroom as volume grows
```
