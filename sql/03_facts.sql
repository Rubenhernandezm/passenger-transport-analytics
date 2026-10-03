/* ==========================================================================
   03_facts.sql — fact views of the star schema (schema dw)
   ========================================================================== */

/* ------------------------------------------------------------- fact_sales
   Grain: one service line of a delivery note.

   Scope rules, each one found by profiling the source:
     - company_id = 1        the ERP also holds two test companies and a frozen
                             copy of company 1 taken before a year-end close
     - accounting_group 1,4  groups 5-7 are commissions, VAT-included services
                             and premises rental, not transport
     - product_id <> 3       used-vehicle sales share accounting group 1 with
                             transport, so the group filter alone lets them in
     - service_date >= 2024  scope of the analysis

   Business date: service_date. posting_date is a copy of the delivery-note
   header and differs from the real service date on most lines.            */
CREATE OR ALTER VIEW dw.fact_sales AS
SELECT
    l.line_id,
    l.line_no,
    CAST(l.service_date AS date)                                  AS service_date,
    CAST(l.posting_date AS date)                                  AS posting_date,
    l.delivery_note_id,
    n.customer_id,
    l.product_id,
    CASE WHEN l.product_id = 1 THEN 'National charter'
         WHEN l.product_id = 2 THEN 'International charter'
         ELSE 'Regular line' END                                  AS service_type,
    l.description,                                                -- route as free text (not parsed yet)
    l.quantity,
    l.amount,
    CASE WHEN l.product_id NOT IN (1, 2) THEN 1 ELSE 0 END        AS is_regular_line,
    -- zero-amount reference lines required by public-sector contracts: not services
    CASE WHEN l.amount = 0 THEN 1 ELSE 0 END                      AS is_administrative_line,
    -- kept visible instead of filtered out, so it can be reviewed as an incident
    CASE WHEN l.service_date > CAST(GETDATE() AS date) THEN 1 ELSE 0 END AS is_future_date
FROM src.sales_lines AS l
JOIN src.products AS p
     ON p.company_id = l.company_id
    AND p.product_id = l.product_id
LEFT JOIN src.delivery_notes AS n
     ON n.company_id = l.company_id
    AND n.delivery_note_id = l.delivery_note_id
WHERE l.company_id = 1
  AND p.accounting_group IN (1, 4)
  AND l.product_id <> 3
  AND l.service_date >= '2024-01-01';
GO

/* ----------------------------------------------------- fact_fleet_expense
   Grain: one fuel-card transaction.

   The provider prints product names as free text with many spellings
   (DIESEL E+, DIE E+, DSL, GASOLEO AÇ, BLUE+GRANE, ADB+GRN...). They are
   mapped to five expense types. Refunds keep their negative sign so totals
   net out, and are flagged for review.                                     */
CREATE OR ALTER VIEW dw.fact_fleet_expense AS
SELECT
    t.transaction_id,
    d.operation_date,
    t.plate                                                       AS vehicle_id,
    t.card_id,
    t.station_name,
    t.station_province,
    t.product_desc                                                AS product_raw,
    e.expense_type,
    CASE WHEN e.expense_type <> 'Fuel' THEN NULL
         WHEN t.product_desc LIKE 'EFI%' THEN 'Petrol'
         ELSE 'Diesel' END                                        AS fuel_kind,
    t.litres,
    t.unit_price,
    t.amount,
    NULLIF(t.odometer_km, 0)                                      AS odometer_km,
    CASE WHEN t.operation_type = 'R' THEN 1 ELSE 0 END            AS is_refund,
    CASE WHEN v.vehicle_id IS NULL THEN 1 ELSE 0 END              AS is_unknown_vehicle,
    CASE WHEN v.vehicle_id IS NOT NULL
          AND (d.operation_date < v.fleet_start_date
               OR d.operation_date > v.fleet_end_date) THEN 1 ELSE 0 END AS is_outside_fleet_period,
    -- missing reading (0) or an impossible value (an extra digit typed)
    CASE WHEN t.odometer_km = 0 OR t.odometer_km > 2000000 THEN 1 ELSE 0 END AS is_odometer_suspect
FROM src.fuel_card_transactions AS t
CROSS APPLY (SELECT TRY_CONVERT(date, CONVERT(char(8), t.operation_date), 112) AS operation_date) AS d
CROSS APPLY (
    SELECT CASE
               WHEN t.product_desc LIKE '%BLUE%' OR t.product_desc LIKE 'ADB%'      THEN 'AdBlue'
               WHEN t.product_desc IN ('AUTOPISTAS', 'PEAJE')                       THEN 'Toll'
               WHEN t.product_desc LIKE 'LAVADO%'                                   THEN 'Wash'
               WHEN t.product_desc IN ('TALLER', 'LUBRICANTE')                      THEN 'Lubricant & workshop'
               WHEN t.product_desc LIKE 'DIE%' OR t.product_desc LIKE 'DSL%'
                 OR t.product_desc LIKE 'GASOLEO%' OR t.product_desc LIKE 'EFI%'    THEN 'Fuel'
               ELSE 'Other'
           END AS expense_type
) AS e
LEFT JOIN src.vehicles AS v
       ON v.vehicle_id = t.plate
WHERE t.operation_date >= 20240101;
GO

/* -------------------------------------------------------- fact_telematics
   Grain: one vehicle and month. Related to the calendar through month_start
   (first day of the month), so it can be sliced by month, quarter or year.  */
CREATE OR ALTER VIEW dw.fact_telematics AS
SELECT
    tm.telematics_id,
    v.vehicle_id,
    tm.month_end,
    DATEFROMPARTS(YEAR(tm.month_end), MONTH(tm.month_end), 1)    AS month_start,
    tm.max_speed,
    tm.avg_speed,
    tm.monthly_km,
    tm.cumulative_km,
    -- GPS glitches: a coach does not reach 130 km/h
    CASE WHEN tm.max_speed > 130 THEN 1 ELSE 0 END                AS is_speed_outlier,
    -- the counter went backwards: usually a replaced device
    CASE WHEN tm.cumulative_km < LAG(tm.cumulative_km)
                OVER (PARTITION BY tm.telematics_id ORDER BY tm.month_end)
         THEN 1 ELSE 0 END                                        AS is_cumulative_km_drop,
    CASE WHEN v.vehicle_id IS NULL THEN 1 ELSE 0 END              AS is_unmatched_device
FROM src.telematics_monthly AS tm
LEFT JOIN src.vehicles AS v
       ON v.telematics_id = tm.telematics_id;
GO
