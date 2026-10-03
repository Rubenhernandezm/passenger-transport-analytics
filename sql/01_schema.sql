/* ==========================================================================
   01_schema.sql — raw source layer (schema src) and analytics layer (schema dw)

   The src tables imitate what the three source systems deliver, warts and
   all: a generic ERP that was never designed for transport analytics, the
   fuel-card provider's monthly export and a telematics export. Nothing here
   is cleaned; cleaning and business rules live in the dw views.
   ========================================================================== */

IF SCHEMA_ID('src') IS NULL EXEC('CREATE SCHEMA src');
GO
IF SCHEMA_ID('dw') IS NULL EXEC('CREATE SCHEMA dw');
GO

DROP TABLE IF EXISTS src.sales_lines, src.delivery_notes, src.products, src.customers,
                     src.companies, src.fuel_card_transactions, src.telematics_monthly, src.vehicles;
GO

/* ---------------------------------------------------------------- ERP ---- */

-- The ERP is multi-company: test environments and a frozen copy live next to the real company.
CREATE TABLE src.companies (
    company_id      SMALLINT       NOT NULL PRIMARY KEY,
    name            NVARCHAR(200)  NOT NULL,
    tax_id          NVARCHAR(20)   NULL
);

CREATE TABLE src.customers (
    company_id      SMALLINT       NOT NULL,
    customer_id     INT            NOT NULL,
    code            NVARCHAR(20)   NOT NULL,
    name            NVARCHAR(200)  NOT NULL,
    legal_name      NVARCHAR(200)  NULL,
    tax_id          NVARCHAR(30)   NULL,
    city            NVARCHAR(100)  NULL,
    province        NVARCHAR(100)  NULL,
    country_code    NVARCHAR(3)    NULL,   -- almost never filled in: not usable as a dimension
    CONSTRAINT pk_customers PRIMARY KEY (company_id, customer_id)
);

-- One catalogue mixes two sales models: generic charter products priced line by line,
-- and regular lines with a fixed tariff. accounting_group also holds non-transport items.
CREATE TABLE src.products (
    company_id        SMALLINT       NOT NULL,
    product_id        INT            NOT NULL,
    code              NVARCHAR(20)   NOT NULL,
    description       NVARCHAR(200)  NOT NULL,
    accounting_group  SMALLINT       NOT NULL,
    price             DECIMAL(12,2)  NOT NULL,
    CONSTRAINT pk_products PRIMARY KEY (company_id, product_id)
);

CREATE TABLE src.delivery_notes (
    company_id        SMALLINT       NOT NULL,
    delivery_note_id  INT            NOT NULL,
    note_date         DATE           NOT NULL,
    customer_id       INT            NOT NULL,
    customer_name     NVARCHAR(200)  NULL,
    CONSTRAINT pk_delivery_notes PRIMARY KEY (company_id, delivery_note_id)
);

-- Generic document-line table reused for transport: one row = one service line.
CREATE TABLE src.sales_lines (
    company_id        SMALLINT       NOT NULL,
    line_id           INT            NOT NULL,
    line_no           SMALLINT       NOT NULL,
    delivery_note_id  INT            NOT NULL,
    product_id        INT            NOT NULL,
    description       NVARCHAR(255)  NULL,      -- free text: the real route lives here for charters
    service_date      DATETIME2(0)   NOT NULL,  -- business date of the service
    posting_date      DATETIME2(0)   NOT NULL,  -- copied from the delivery-note header
    quantity          DECIMAL(10,2)  NOT NULL,
    unit_price        DECIMAL(12,2)  NOT NULL,
    amount            DECIMAL(12,2)  NOT NULL,
    cost_amount       DECIMAL(12,2)  NOT NULL,  -- always 0: field exists but is never used
    CONSTRAINT pk_sales_lines PRIMARY KEY (company_id, line_id)
);

/* -------------------------------------------------------------- fleet ---- */

CREATE TABLE src.vehicles (
    vehicle_id               NVARCHAR(10)  NOT NULL PRIMARY KEY,   -- licence plate
    vehicle_type             NVARCHAR(30)  NOT NULL,
    brand                    NVARCHAR(50)  NULL,                   -- inconsistent spelling and casing
    chassis                  NVARCHAR(20)  NULL,
    fuel_card_id             NVARCHAR(20)  NULL,
    toll_card_id             NVARCHAR(20)  NULL,
    telematics_id            NVARCHAR(20)  NULL,
    first_registration_date  DATE          NULL,
    fleet_start_date         DATE          NULL,
    fleet_end_date           DATE          NULL,
    status                   NVARCHAR(10)  NOT NULL
);

-- Fuel-card provider export: dates as YYYYMMDD integers, free-text product names,
-- refunds as negative rows, odometer typed in by the driver.
CREATE TABLE src.fuel_card_transactions (
    transaction_id    INT            NOT NULL PRIMARY KEY,
    card_id           NVARCHAR(20)   NULL,
    plate             NVARCHAR(10)   NULL,
    operation_date    INT            NOT NULL,
    operation_time    NVARCHAR(5)    NULL,
    station_name      NVARCHAR(100)  NULL,
    station_province  NVARCHAR(50)   NULL,
    odometer_km       INT            NULL,
    product_code      NVARCHAR(10)   NULL,
    product_desc      NVARCHAR(30)   NULL,
    litres            DECIMAL(10,2)  NULL,
    unit_price        DECIMAL(8,3)   NULL,
    amount            DECIMAL(12,2)  NOT NULL,
    operation_type    CHAR(1)        NOT NULL      -- S = sale, R = refund
);

CREATE TABLE src.telematics_monthly (
    telematics_id   NVARCHAR(20)  NOT NULL,
    plate           NVARCHAR(10)  NULL,
    month_end       DATE          NOT NULL,
    max_speed       SMALLINT      NULL,
    avg_speed       SMALLINT      NULL,
    monthly_km      INT           NULL,
    cumulative_km   INT           NULL,
    CONSTRAINT pk_telematics_monthly PRIMARY KEY (telematics_id, month_end)
);
GO
