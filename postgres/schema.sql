-- Supply Chain Digital Twin — PostgreSQL schema
-- Transactional / time-series tables that complement the Neo4j structural graph.
-- item_id / material_id / product_id / supplier_id / dealer_id values match the
-- IDs used in Neo4j (see docs/data_reference.md) so the two stores can be
-- cross-referenced by ID during agent development.

-- Optional (build step 8 extension): semantic search over free-text supplier notes.
-- Skips cleanly if the pgvector extension isn't available on this Postgres instance -
-- everything else in this schema has no dependency on it.
CREATE EXTENSION IF NOT EXISTS vector;

DROP TABLE IF EXISTS chat_history CASCADE;
DROP TABLE IF EXISTS supplier_notes CASCADE;
DROP TABLE IF EXISTS action_log CASCADE;
DROP TABLE IF EXISTS sales_records CASCADE;
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
    penalty_terms     TEXT,
    -- Who to actually call about this contract, and whether expiry needs a manual
    -- decision or just renews on its own - both real fields a procurement user
    -- immediately wants once they've clicked into a contract, neither derivable from
    -- anything else already in this schema.
    account_manager   VARCHAR(60),
    auto_renew        BOOLEAN NOT NULL DEFAULT false
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
    status            VARCHAR(15) NOT NULL CHECK (status IN ('in_transit', 'delivered', 'delayed')),
    -- "What's actually happening with this shipment" fields a logistics/procurement
    -- user expects and previously had no way to see at all - who's carrying it, how,
    -- and (only ever populated when status='delayed') why it's late. freight_mode
    -- correlates with the material's own category in the generator (bulk steel/
    -- aluminum skew rail, everything else skews truck) for realism, not randomly.
    carrier           VARCHAR(50),
    freight_mode      VARCHAR(20) CHECK (freight_mode IN ('truck', 'rail', 'ocean', 'air')),
    tracking_number   VARCHAR(30),
    delay_reason      TEXT
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

-- The commercial/revenue counterpart to dealer_orders (which only tracks what/how much
-- was ordered and its fulfillment status), mirroring how invoices is the money-side
-- counterpart to purchase_orders on the buy side. One sales_record per dealer_order
-- that actually shipped (a still-backordered order has nothing to invoice yet) - the
-- quantity/dealer/product dimensions live on dealer_orders and are reached via
-- order_id, not duplicated here, same normalization choice invoices already makes for
-- supplier_id/material_id. "Where we're selling" (by region) isn't a Postgres column at
-- all - Dealer->Region only exists in Neo4j (Dealer.SERVICES), so a region breakdown
-- crosses both stores by dealer_id, same cross-database-by-ID pattern used everywhere
-- else in this app (see docs/data_reference.md's header note).
CREATE TABLE sales_records (
    sale_id           VARCHAR(20) PRIMARY KEY,
    order_id          VARCHAR(20) NOT NULL REFERENCES dealer_orders(order_id),
    unit_price        NUMERIC(12, 4) NOT NULL,
    currency          VARCHAR(3) NOT NULL DEFAULT 'USD',
    revenue           NUMERIC(14, 2) NOT NULL,
    sale_date         DATE NOT NULL,
    channel           VARCHAR(20) NOT NULL CHECK (channel IN ('direct', 'distributor', 'online')),
    payment_status    VARCHAR(15) NOT NULL CHECK (payment_status IN ('paid', 'pending', 'overdue'))
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

-- Written by agent/nodes/approval.py (build step 8's human_approval_gate) when a
-- disruption's recommended reorder-from-backup-supplier action is approved or rejected.
-- Not seeded - starts empty, populated live by the app.
CREATE TABLE action_log (
    action_id     SERIAL PRIMARY KEY,
    action_type   VARCHAR(50) NOT NULL,
    description   TEXT NOT NULL,
    status        VARCHAR(20) NOT NULL CHECK (status IN ('approved', 'rejected')),
    note          TEXT,
    decided_at    TIMESTAMP NOT NULL DEFAULT now()
);

-- Persists every answered question, grouped by browser session, so conversation
-- history survives a page refresh or a server restart - st.session_state alone is
-- purely in-memory and both of those wipe it. state_json is the same
-- answer_card.render_answer_card()-renderable state dict the live UI already builds
-- (answer, confidence, neo4j_result/postgres_result/semantic_result, reasoning_log,
-- etc.), stored as-is, so reloading a past session renders an identical answer card,
-- not just the question/answer text. Only successful turns are logged (a question that
-- errored out isn't meaningful conversation memory).
CREATE TABLE chat_history (
    turn_id       SERIAL PRIMARY KEY,
    session_id    VARCHAR(36) NOT NULL,
    question      TEXT NOT NULL,
    state_json    JSONB NOT NULL,
    created_at    TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX idx_chat_history_session ON chat_history(session_id);
CREATE INDEX idx_chat_history_created ON chat_history(created_at DESC);

-- Free-text audit/quality/risk notes per supplier or third-party vendor (supplier_id
-- matches the Neo4j Supplier/ThirdPartyVendor id) - the one genuinely unstructured
-- content in this otherwise fully-structured schema, and the only thing here that
-- benefits from semantic search rather than an exact Cypher/SQL filter. Embeddings are
-- generated locally (sentence-transformers' all-MiniLM-L6-v2, 384 dims) - no LLM API
-- call, no quota - see postgres/generate_supplier_notes.py. No vector index: at this
-- table's real size (well under 100 rows) a brute-force cosine scan is instant: an
-- ivfflat/hnsw index would only start earning its keep at a much larger scale.
CREATE TABLE supplier_notes (
    note_id       SERIAL PRIMARY KEY,
    supplier_id   VARCHAR(10) NOT NULL,
    note_type     VARCHAR(30) NOT NULL,  -- quality | compliance | risk | sustainability
    note_text     TEXT NOT NULL,
    noted_date    DATE NOT NULL,
    embedding     vector(384)
);

CREATE INDEX idx_po_material ON purchase_orders(material_id);
CREATE INDEX idx_po_supplier ON purchase_orders(supplier_id);
CREATE INDEX idx_billing_contract ON monthly_billing(contract_id);
CREATE INDEX idx_shipments_contract ON shipments(contract_id);
CREATE INDEX idx_invoices_contract ON invoices(contract_id);
CREATE INDEX idx_dealer_orders_dealer ON dealer_orders(dealer_id);
CREATE INDEX idx_dealer_orders_product ON dealer_orders(product_id);
CREATE INDEX idx_sales_records_order ON sales_records(order_id);
CREATE INDEX idx_sales_records_date ON sales_records(sale_date DESC);
CREATE INDEX idx_supplier_notes_supplier ON supplier_notes(supplier_id);
