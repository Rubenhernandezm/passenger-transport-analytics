/* ==========================================================================
   04_checks.sql — validation queries, run at the end of every load
   ========================================================================== */

-- 1. Size of every view of the model
SELECT 'dim_calendar' AS view_name, COUNT(*) AS row_count FROM dw.dim_calendar
UNION ALL SELECT 'dim_product',        COUNT(*) FROM dw.dim_product
UNION ALL SELECT 'dim_customer',       COUNT(*) FROM dw.dim_customer
UNION ALL SELECT 'dim_vehicle',        COUNT(*) FROM dw.dim_vehicle
UNION ALL SELECT 'fact_sales',         COUNT(*) FROM dw.fact_sales
UNION ALL SELECT 'fact_fleet_expense', COUNT(*) FROM dw.fact_fleet_expense
UNION ALL SELECT 'fact_telematics',    COUNT(*) FROM dw.fact_telematics;
GO

-- 2. What each scope rule removes from the raw sales lines
SELECT
    SUM(CASE WHEN l.company_id <> 1 THEN 1 ELSE 0 END)                                   AS lines_other_companies,
    SUM(CASE WHEN l.company_id = 1 AND p.accounting_group NOT IN (1, 4) THEN 1 ELSE 0 END) AS lines_non_transport_groups,
    SUM(CASE WHEN l.company_id = 1 AND l.product_id = 3 THEN 1 ELSE 0 END)               AS lines_vehicle_sales,
    SUM(CASE WHEN l.company_id = 1 AND l.product_id = 3 THEN l.amount ELSE 0 END)        AS amount_vehicle_sales
FROM src.sales_lines AS l
JOIN src.products AS p
  ON p.company_id = l.company_id AND p.product_id = l.product_id;
GO

-- 3. Why service_date and not posting_date: how often they match
SELECT
    COUNT(*)                                                             AS lines,
    CAST(100.0 * SUM(CASE WHEN service_date = posting_date THEN 1 ELSE 0 END)
         / COUNT(*) AS DECIMAL(5,1))                                     AS pct_same_date
FROM dw.fact_sales;
GO

-- 4. Sales by service type, with the flagged rows shown apart
SELECT
    service_type,
    COUNT(*)                                                  AS lines,
    SUM(is_administrative_line)                               AS administrative_lines,
    SUM(is_future_date)                                       AS future_date_lines,
    SUM(CASE WHEN is_future_date = 0 THEN amount ELSE 0 END)  AS amount
FROM dw.fact_sales
GROUP BY service_type
ORDER BY amount DESC;
GO

-- 5. Fleet expense by type, with data quality flags
SELECT
    expense_type,
    COUNT(*)                        AS transactions,
    SUM(amount)                     AS amount,
    SUM(is_refund)                  AS refunds,
    SUM(is_unknown_vehicle)         AS unknown_vehicle,
    SUM(is_outside_fleet_period)    AS outside_fleet_period,
    SUM(is_odometer_suspect)        AS suspect_odometer
FROM dw.fact_fleet_expense
GROUP BY expense_type
ORDER BY amount DESC;
GO

-- 6. Telematics incidents
SELECT
    COUNT(*)                        AS vehicle_months,
    SUM(monthly_km)                 AS km,
    SUM(is_speed_outlier)           AS speed_outliers,
    SUM(is_cumulative_km_drop)      AS cumulative_km_drops,
    SUM(is_unmatched_device)        AS unmatched_devices
FROM dw.fact_telematics;
GO

-- 7. Customers by derived type
SELECT customer_type, COUNT(*) AS customers
FROM dw.dim_customer
GROUP BY customer_type
ORDER BY customers DESC;
GO
