"""Schema context injected into LLM prompts for Cypher/SQL generation.

POSTGRES_SCHEMA is read live from postgres/schema.sql so it can never drift
from the actual DDL. NEO4J_SCHEMA is hand-written (the graph's relationship
shape isn't fully captured by schema.cypher, which only holds constraints).
"""
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

POSTGRES_SCHEMA = (_ROOT / "postgres" / "schema.sql").read_text()

NEO4J_SCHEMA = """
Node labels and key properties:
  Facility {id, name, city, state}
  Warehouse {id, name, city, state}
  Region {id, name}
  Dealer {id, name, city, state, buyer_type}   // buyer_type is 'dealer' (smaller
    // regional reseller) or 'distributor' (larger wholesale reseller) - both buy
    // finished Products from us and resell downstream to end customers; only the
    // scale/tier differs. Revenue/payment data for what they buy lives in
    // PostgreSQL's sales_records table (joined via dealer_orders.dealer_id).
  Product {id, name, category}
  IntermediatePart {id, name}
  RawMaterial {id, name, category, unit_of_measure}
  Supplier {id, name, city, state, lat, long}          // raw-material suppliers
  ThirdPartyVendor {id, name, city, state, lat, long}   // intermediate-part vendors
  Contract {contract_id, start_date, end_date, status, contract_value,
            renewal_notice_days, penalty_clause}

Relationships:
  (RawMaterial)-[:SOURCED_FROM {lead_time_days, cost_per_unit, currency, is_primary}]->(Supplier)
  (backupSupplier:Supplier)-[:BACKUP_FOR]->(primarySupplier:Supplier)
    // direction matters: the SOURCE node of this edge is the backup/secondary supplier,
    // the TARGET node is the primary supplier it backs up. To find "the backup supplier
    // for material X", first find X's primary supplier via SOURCED_FROM {is_primary:true},
    // then MATCH (primary)<-[:BACKUP_FOR]-(backup) — i.e. backup points INTO primary.
  (RawMaterial)-[:USED_IN {quantity_required, unit_of_measure}]->(IntermediatePart)
  (IntermediatePart)-[:PURCHASED_FROM]->(ThirdPartyVendor)
  (IntermediatePart)-[:USED_IN {quantity_required}]->(Product)
  (Product)-[:MANUFACTURED_AT]->(Facility)
  (Product)-[:STORED_IN]->(Warehouse)
  (Warehouse)-[:SUPPLIES]->(Dealer)
  (Dealer)-[:SERVICES]->(Region)
  (Supplier)-[:HAS_CONTRACT]->(Contract)             // active contracts only
  (Supplier)-[:PREVIOUSLY_CONTRACTED]->(Contract)    // expired contracts
  (Contract)-[:COVERS]->(RawMaterial)

ID conventions (also used as foreign-key-style identifiers in PostgreSQL —
item_id/material_id/product_id/supplier_id/dealer_id columns there hold these
same values, though the two databases are queried separately, never joined
live):
  F# = Facility, WH# = Warehouse, R# = Region, D# = Dealer, P# = Product,
  IP# = IntermediatePart, RM# = RawMaterial, S# = Supplier (raw materials),
  V# = ThirdPartyVendor (intermediate parts), C# = Contract.

"Where are we selling" / revenue-by-region questions need BOTH stores: Dealer->Region
only exists here (Dealer.SERVICES), while revenue/units/payment-status only exists in
PostgreSQL's sales_records (joined to dealer_orders by order_id) - resolve the
Dealer/Region side here first, then filter PostgreSQL by those dealer_id values.
"""
