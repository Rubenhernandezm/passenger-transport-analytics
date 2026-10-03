/* ==========================================================================
   02_dimensions.sql — dimension views of the star schema (schema dw)

   Principle used across the model: data that looks wrong is never deleted or
   silently fixed. It stays visible and gets an is_* flag, so Power BI can
   keep it out of the KPIs while the business can still review it.
   ========================================================================== */

/* ---------------------------------------------------------- dim_calendar
   Generated date table, 2024-01-01 to 2027-12-31. A recursive CTE would need
   OPTION (MAXRECURSION), which is not allowed inside a view, so the numbers
   come from a cross join of a system catalogue.                             */
CREATE OR ALTER VIEW dw.dim_calendar AS
WITH numbers AS (
    SELECT TOP (DATEDIFF(DAY, '2024-01-01', '2027-12-31') + 1)
           ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) - 1 AS n
    FROM sys.all_objects AS a
    CROSS JOIN sys.all_objects AS b
),
dates AS (
    SELECT DATEADD(DAY, n, CAST('2024-01-01' AS date)) AS [date]
    FROM numbers
)
SELECT
    [date],
    YEAR([date])                                          AS [year],
    DATEPART(QUARTER, [date])                             AS [quarter],
    MONTH([date])                                         AS [month],
    CONVERT(char(7), [date], 126)                         AS year_month,     -- 'YYYY-MM'
    DATEPART(ISO_WEEK, [date])                            AS iso_week,
    DAY([date])                                           AS [day],
    -- 1 = Monday ... 7 = Sunday, independent of the server's DATEFIRST setting
    ((DATEPART(WEEKDAY, [date]) + @@DATEFIRST - 2) % 7) + 1 AS weekday_number,
    CASE WHEN ((DATEPART(WEEKDAY, [date]) + @@DATEFIRST - 2) % 7) + 1 IN (6, 7)
         THEN 1 ELSE 0 END                                AS is_weekend,
    CASE WHEN MONTH([date]) IN (7, 8) THEN 0 ELSE 1 END   AS is_school_period
FROM dates;
GO

/* ----------------------------------------------------------- dim_product
   Same scope as the sales fact: transport accounting groups only (1 and 4),
   and product 3 (used-vehicle sales) excluded although it shares group 1.   */
CREATE OR ALTER VIEW dw.dim_product AS
SELECT
    p.product_id,
    p.code,
    p.description                                         AS product_name,
    CASE WHEN p.product_id = 1 THEN 'National charter'
         WHEN p.product_id = 2 THEN 'International charter'
         ELSE 'Regular line' END                          AS service_type,
    p.price                                               AS list_price,
    -- most regular lines only carry their code as a name: not usable as a visible label
    CASE WHEN p.description = p.code THEN 1 ELSE 0 END    AS is_name_only_code,
    -- a zero tariff is expected for the generic charter products (priced line by line);
    -- it is only an anomaly on a regular line
    CASE WHEN p.price = 0 AND p.product_id NOT IN (1, 2)
         THEN 1 ELSE 0 END                                AS is_zero_tariff
FROM src.products AS p
WHERE p.company_id = 1
  AND p.accounting_group IN (1, 4)
  AND p.product_id <> 3;
GO

/* ---------------------------------------------------------- dim_customer
   The customer master has no usable segmentation field, so customer_type is
   derived from the first character of the Spanish tax ID, following the
   public composition rules of the NIF/CIF.                                  */
CREATE OR ALTER VIEW dw.dim_customer AS
SELECT
    c.customer_id,
    c.code,
    c.name,
    c.legal_name,
    c.tax_id,
    c.city,
    c.province,
    t.customer_type,
    CASE WHEN t.clean_tax_id = '' THEN 1 ELSE 0 END                         AS is_missing_tax_id,
    CASE WHEN t.clean_tax_id <> '' AND LEN(t.clean_tax_id) <> 9 THEN 1 ELSE 0 END AS is_non_spanish_tax_id
FROM src.customers AS c
CROSS APPLY (SELECT LTRIM(RTRIM(ISNULL(c.tax_id, ''))) AS clean_tax_id) AS x
CROSS APPLY (
    SELECT x.clean_tax_id,
           CASE
               WHEN x.clean_tax_id = ''                                   THEN 'No tax ID'
               -- inferred from the format, not confirmed: the country field is empty
               WHEN LEN(x.clean_tax_id) <> 9                              THEN 'Foreign (probable)'
               WHEN LEFT(x.clean_tax_id, 1) BETWEEN '0' AND '9'
                 OR LEFT(x.clean_tax_id, 1) IN ('X', 'Y', 'Z')            THEN 'Individual'
               WHEN LEFT(x.clean_tax_id, 1) = 'P'                         THEN 'Local government'
               WHEN LEFT(x.clean_tax_id, 1) = 'Q'                         THEN 'Public body / education'
               WHEN LEFT(x.clean_tax_id, 1) = 'S'                         THEN 'Regional / state government'
               WHEN LEFT(x.clean_tax_id, 1) = 'R'                         THEN 'Religious entity'
               WHEN LEFT(x.clean_tax_id, 1) = 'G'                         THEN 'Association / club'
               ELSE 'Company'
           END AS customer_type
) AS t
WHERE c.company_id = 1;
GO

/* ----------------------------------------------------------- dim_vehicle
   Brand spelling is normalised here (MAN / Man / MAN / IRIZAR -> MAN, etc.);
   the raw value is kept next to it.                                        */
CREATE OR ALTER VIEW dw.dim_vehicle AS
SELECT
    v.vehicle_id,
    v.vehicle_type,
    v.brand                                                AS brand_raw,
    CASE
        WHEN UPPER(v.brand) LIKE 'MERCEDES%' THEN 'MERCEDES-BENZ'
        WHEN UPPER(v.brand) LIKE 'MAN%'      THEN 'MAN'
        ELSE UPPER(LTRIM(RTRIM(v.brand)))
    END                                                    AS brand,
    v.status,
    CASE WHEN v.status = 'Active' THEN 1 ELSE 0 END        AS is_active,
    v.first_registration_date,
    v.fleet_start_date,
    v.fleet_end_date,
    DATEDIFF(YEAR, v.first_registration_date,
             COALESCE(v.fleet_end_date, CAST(GETDATE() AS date)))  AS age_years,
    CASE WHEN v.telematics_id IS NULL THEN 1 ELSE 0 END    AS is_missing_telematics,
    CASE WHEN v.fuel_card_id IS NULL THEN 1 ELSE 0 END     AS is_missing_fuel_card
FROM src.vehicles AS v;
GO
