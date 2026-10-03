# Power BI report layout

The `.pbix` is built in Power BI Desktop on top of the synthetic database
(see `measures.dax` for the setup and the measures). Three pages:

## 1. Sales (since 2024)

| Visual | Fields |
| --- | --- |
| Card | `Total Sales` |
| Card | `Sales YoY %` |
| Card | `Sales PY` |
| Line chart | `Total Sales` by `dim_calendar[date]` |
| Bar chart (top 20) | `Total Sales` by `dim_customer[name]` |
| Donut | `Total Sales` by `dim_product[service_type]` |
| Slicer (tiles) | `dim_calendar[year_month]` |

Optional: a slicer on `dim_customer[customer_type]` to compare public-sector
contracts with private charters.

## 2. Fleet costs (since 2024)

| Visual | Fields |
| --- | --- |
| Card | `Fleet Expense` |
| Card | `Fuel Expense` |
| Card | `Km Driven` |
| Card | `Fuel Cost per Km` |
| Donut | `Fleet Expense` by `fact_fleet_expense[expense_type]` |
| Bar chart | `Fleet Expense` by `dim_vehicle[vehicle_id]` |
| Line chart | `Fuel Expense` by `dim_calendar[date]` |
| Slicer (tiles) | `dim_calendar[year_month]` |

## 3. Data quality

| Visual | Fields |
| --- | --- |
| Card | `Data Quality Incidents` |
| Table | `fact_fleet_expense` rows where any `is_*` flag = 1: date, vehicle, product_raw, amount, flags |
| Table | `fact_telematics` rows with `is_speed_outlier` or `is_cumulative_km_drop` |
| Table | `fact_sales` rows with `is_future_date` = 1 |

This page is the point of the flag approach: nothing doubtful is deleted,
and the business gets a list of incidents to review.

## Screenshots

Export each page (File > Export > PDF, or a screenshot) and save them as
`docs/img/sales.png`, `docs/img/fleet.png` and `docs/img/data-quality.png`
so they show up in the README.
