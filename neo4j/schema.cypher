// Supply Chain Digital Twin — Neo4j constraints & indexes
// Run this once against an empty AuraDB (or local) instance before seed_data.cypher.

CREATE CONSTRAINT facility_id IF NOT EXISTS FOR (n:Facility) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT warehouse_id IF NOT EXISTS FOR (n:Warehouse) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT region_id IF NOT EXISTS FOR (n:Region) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT dealer_id IF NOT EXISTS FOR (n:Dealer) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT product_id IF NOT EXISTS FOR (n:Product) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT intermediate_part_id IF NOT EXISTS FOR (n:IntermediatePart) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT raw_material_id IF NOT EXISTS FOR (n:RawMaterial) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT supplier_id IF NOT EXISTS FOR (n:Supplier) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT vendor_id IF NOT EXISTS FOR (n:ThirdPartyVendor) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT contract_id IF NOT EXISTS FOR (n:Contract) REQUIRE n.contract_id IS UNIQUE;

CREATE INDEX supplier_name IF NOT EXISTS FOR (n:Supplier) ON (n.name);
CREATE INDEX vendor_name IF NOT EXISTS FOR (n:ThirdPartyVendor) ON (n.name);
CREATE INDEX product_name IF NOT EXISTS FOR (n:Product) ON (n.name);
CREATE INDEX contract_status IF NOT EXISTS FOR (n:Contract) ON (n.status);
