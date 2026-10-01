# Row-Level Security (requirement #9)

## Mapping table

`Security_UserRegion` (see [model/tables.md](../model/tables.md)) is the single source
for who sees what. It's maintained by IT/HR process (new hire, role change, departure),
not hardcoded into DAX filters — a DAX filter would need a model redeploy every time
someone changes territory.

```
UserPrincipalName        RegionKey   AccountKey   Role
alice@meridian.com       NA-EAST     NULL         RegionalManager
bob@meridian.com         NULL        ACC-0472     KeyAccountManager
carol@meridian.com       NULL        NULL         Director
```

## Roles (defined in the semantic model, not per-report)

### Role: "Regional Manager"
Filter on `Dim Geography`:
```DAX
[RegionKey] IN
    CALCULATETABLE (
        VALUES ( Security_UserRegion[RegionKey] ),
        Security_UserRegion[UserPrincipalName] = USERPRINCIPALNAME ()
    )
```
Sees only their region's rows, propagated through relationships to Fact Sales via
`Dim Customer -> Dim Geography`.

### Role: "Key Account Manager"
Filter on `Dim Customer`:
```DAX
[CustomerBK] IN
    CALCULATETABLE (
        VALUES ( Security_UserRegion[AccountKey] ),
        Security_UserRegion[UserPrincipalName] = USERPRINCIPALNAME ()
    )
```
Sees only the specific accounts listed for them, regardless of region.

### Role: "Director" (and above)
No row filter — `Security_UserRegion` has `RegionKey = NULL` and `AccountKey = NULL`
for their row, meaning unrestricted. (Implemented as a role with no table filters
applied, rather than a filter that tries to match NULL — simpler and avoids DAX NULL-
comparison edge cases.)

## Why USERPRINCIPALNAME() and not USERNAME()

`USERPRINCIPALNAME()` returns the UPN (`alice@meridian.com`), which matches Azure AD /
Entra ID identities used by Power BI Service row-level security and is stable across
domain-join changes. `USERNAME()` returns `DOMAIN\user` in some contexts and is
inconsistent between Desktop and Service — avoid it for RLS that must work identically
in both.

## Testing

Use "View As Roles" in Power BI Desktop with each role + a specific UPN before every
publish. RLS bugs are invisible to the model author (who usually has full access) and
only surface when an actual restricted user opens the report — test as the restricted
user, not as yourself.
