# Data quality and design decisions

The generator plants the kind of problems that appear when an ERP and
third-party exports are used for analytics they were not designed for.
Each one is handled in the SQL layer in one of three ways:

- **Scope filter**: the rows are not part of the business being analysed.
- **Normalise**: the value is right but written inconsistently.
- **Flag**: the row is doubtful. It stays visible with an `is_*` column, the
  KPIs exclude it, and the data quality page lists it for review.

The rule of thumb: a flag is preferred over a filter whenever the row could
be a real event. Deleting it would hide the problem from the people who can fix it.

## Sales (ERP)

| Problem in the source | Handling | Where |
| --- | --- | --- |
| Two test companies and a frozen copy of the real company (same tax ID, data cut at a past date) live in the same tables | Scope filter `company_id = 1` | `fact_sales`, dims |
| Commissions, VAT-included services and premises rental share the sales table | Scope filter on `accounting_group IN (1, 4)` | `fact_sales`, `dim_product` |
| Used-vehicle sales share accounting group 1 with transport, so the group filter alone lets them in | Extra scope filter `product_id <> 3` | `fact_sales`, `dim_product` |
| `posting_date` is a copy of the delivery-note header, not the service date | Business date = `service_date` (check 3 in `04_checks.sql` shows how often they differ) | `fact_sales` |
| Zero-amount reference lines required by public-sector contracts | Flag `is_administrative_line`; excluded from service counts | `fact_sales` |
| A service date typed with the wrong year (2052) | Flag `is_future_date`; excluded from sales KPIs | `fact_sales` |
| Most regular lines have the code as their name | Flag `is_name_only_code` | `dim_product` |
| A regular line with no tariff in the catalogue | Flag `is_zero_tariff` (only for regular lines: charters are priced line by line) | `dim_product` |
| The customer master has no usable segment field; the country field is almost always empty | `customer_type` derived from the tax ID format; "Foreign" labelled as probable | `dim_customer` |
| The `cost_amount` field exists but is always 0 | Not used: there is no cost data in the ERP | — |

## Fleet (fuel card, telematics, fleet register)

| Problem in the source | Handling | Where |
| --- | --- | --- |
| Dates delivered as `YYYYMMDD` integers | Converted with `TRY_CONVERT` | `fact_fleet_expense` |
| Product names in free text with many spellings, in two languages | Mapped to five expense types | `fact_fleet_expense` |
| Refunds as negative rows | Kept with their sign (totals net out); flag `is_refund` | `fact_fleet_expense` |
| Odometer missing (0) or with an extra digit | Flag `is_odometer_suspect`; 0 turned into NULL | `fact_fleet_expense` |
| A hired coach refuelled with a company card: plate not in the fleet register | Flag `is_unknown_vehicle` | `fact_fleet_expense` |
| A fuel card still used after its coach was retired | Flag `is_outside_fleet_period` | `fact_fleet_expense` |
| Brand written in several ways (MAN, Man, MAN / IRIZAR, MERCEDES BENZ...) | Normalised; raw value kept | `dim_vehicle` |
| GPS spike in maximum speed | Flag `is_speed_outlier` | `fact_telematics` |
| Cumulative km going backwards after a device change | Flag `is_cumulative_km_drop` | `fact_telematics` |

## Known limitation

The ERP does not record which vehicle performed each service, so sales and
fleet costs only meet at company level (for example cost per km against
revenue per month), not per vehicle or per route. Building a vehicle-level
margin would need a planning or dispatch source that this model does not have.
It is documented here instead of being approximated.

## Layers

| Layer | Holds | Why there |
| --- | --- | --- |
| SQL views (`dw`) | Scope rules, joins, normalisation, flags | Business logic in one place, testable with SQL, reusable by any tool |
| Power Query | Table names and types only | Keeps the report thin |
| DAX measures | KPIs and which flags enter them | Analysis decisions stay visible in the report |
