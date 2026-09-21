-- Supply Chain Digital Twin — PostgreSQL schema
-- Transactional / time-series tables that complement the Neo4j structural graph.
-- item_id / material_id / product_id / supplier_id / dealer_id values match the
-- IDs used in Neo4j (see docs/data_reference.md) so the two stores can be
-- cross-referenced by ID during agent development.

DROP TABLE IF EXISTS invoices CASCADE;
DROP TABLE IF EXISTS shipments CASCADE;
DROP TABLE IF EXISTS monthly_billing CASCADE;
DROP TABLE IF EXISTS contracts CASCADE;
DROP TABLE IF EXISTS purchase_orders CASCADE;
DROP TABLE IF EXISTS price_calibration CASCADE;
DROP TABLE IF EXISTS dealer_orders CASCADE;
DROP TABLE IF EXISTS production_capacity CASCADE;
DROP TABLE IF EXISTS supplier_performance CASCADE;
DROP TABLE IF EXISTS inventory_levels CASCADE;

CREATE TABLE inventory_levels (
    item_id           VARCHAR(20) NOT NULL,
    item_type         VARCHAR(20) NOT NULL CHECK (item_type IN ('raw_material', 'intermediate_part', 'product')),
    warehouse_id      VARCHAR(10) NOT NULL,
    quantity_on_hand  NUMERIC(12, 2) NOT NULL,
    unit_of_measure   VARCHAR(20) NOT NULL,
    reorder_point     NUMERIC(12, 2) NOT NULL,
    last_updated      TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (item_id, warehouse_id)
);

CREATE TABLE contracts (
    contract_id       VARCHAR(10) PRIMARY KEY,
    supplier_id       VARCHAR(10) NOT NULL,
    start_date        DATE NOT NULL,
    end_date          DATE NOT NULL,
    contract_value    NUMERIC(14, 2) NOT NULL,
    payment_terms     VARCHAR(50) NOT NULL,
    renewal_status    VARCHAR(20) NOT NULL CHECK (renewal_status IN ('active', 'expiring_soon', 'expired')),
    penalty_clause    BOOLEAN NOT NULL DEFAULT false,
    penalty_terms     TEXT
);

CREATE TABLE purchase_orders (
    po_id             VARCHAR(20) PRIMARY KEY,
    material_id       VARCHAR(20) NOT NULL,
    supplier_id       VARCHAR(10) NOT NULL,
    quantity          NUMERIC(12, 2) NOT NULL,
    unit_of_measure   VARCHAR(20) NOT NULL,
    price_per_unit    NUMERIC(12, 4) NOT NULL,
    currency          VARCHAR(3) NOT NULL DEFAULT 'USD',
    order_date        DATE NOT NULL
);

CREATE TABLE price_calibration (
    material_id       VARCHAR(20) NOT NULL,
    currency          VARCHAR(3) NOT NULL,
    price_per_unit    NUMERIC(12, 4) NOT NULL,
    unit_of_measure   VARCHAR(20) NOT NULL,
    effective_date    DATE NOT NULL,
    PRIMARY KEY (material_id, currency, effective_date)
);

CREATE TABLE monthly_billing (
    billing_id        VARCHAR(20) PRIMARY KEY,
    contract_id       VARCHAR(10) NOT NULL REFERENCES contracts(contract_id),
    billing_month      DATE NOT NULL,
    amount_due        NUMERIC(12, 2) NOT NULL,
    amount_paid       NUMERIC(12, 2) NOT NULL DEFAULT 0,
    status            VARCHAR(10) NOT NULL CHECK (status IN ('paid', 'pending', 'overdue'))
);

CREATE TABLE shipments (
    shipment_id       VARCHAR(20) PRIMARY KEY,
    contract_id       VARCHAR(10) REFERENCES contracts(contract_id),
    po_id             VARCHAR(20) REFERENCES purchase_orders(po_id),
    ship_date         DATE NOT NULL,
    received_date     DATE,
    quantity          NUMERIC(12, 2) NOT NULL,
    status            VARCHAR(15) NOT NULL CHECK (status IN ('in_transit', 'delivered', 'delayed'))
);

CREATE TABLE invoices (
    invoice_id        VARCHAR(20) PRIMARY KEY,
    contract_id       VARCHAR(10) REFERENCES contracts(contract_id),
    shipment_id       VARCHAR(20) REFERENCES shipments(shipment_id),
    po_id             VARCHAR(20) REFERENCES purchase_orders(po_id),
    amount            NUMERIC(12, 2) NOT NULL,
    currency          VARCHAR(3) NOT NULL DEFAULT 'USD',
    due_date          DATE NOT NULL,
    status            VARCHAR(15) NOT NULL CHECK (status IN ('paid', 'pending', 'overdue', 'mismatch'))
);

CREATE TABLE dealer_orders (
    order_id            VARCHAR(20) PRIMARY KEY,
    dealer_id           VARCHAR(10) NOT NULL,
    product_id          VARCHAR(10) NOT NULL,
    quantity            NUMERIC(12, 2) NOT NULL,
    order_date          DATE NOT NULL,
    fulfillment_status  VARCHAR(15) NOT NULL CHECK (fulfillment_status IN ('pending', 'fulfilled', 'partial', 'backordered'))
);

CREATE TABLE production_capacity (
    product_id          VARCHAR(10) PRIMARY KEY,
    max_units_per_week  NUMERIC(10, 2) NOT NULL
);

CREATE TABLE supplier_performance (
    supplier_id       VARCHAR(10) PRIMARY KEY,
    on_time_rate      NUMERIC(5, 2) NOT NULL,
    avg_delay_days    NUMERIC(6, 2) NOT NULL
);

CREATE INDEX idx_po_material ON purchase_orders(material_id);
CREATE INDEX idx_po_supplier ON purchase_orders(supplier_id);
CREATE INDEX idx_billing_contract ON monthly_billing(contract_id);
CREATE INDEX idx_shipments_contract ON shipments(contract_id);
CREATE INDEX idx_invoices_contract ON invoices(contract_id);
CREATE INDEX idx_dealer_orders_dealer ON dealer_orders(dealer_id);
CREATE INDEX idx_dealer_orders_product ON dealer_orders(product_id);
