// Supply Chain Digital Twin — Neo4j seed data
// Run schema.cypher first. Safe to re-run (uses MERGE throughout).
// ID scheme and rationale documented in docs/data_reference.md.

// ---------------------------------------------------------------------------
// Facility
// ---------------------------------------------------------------------------
MERGE (f:Facility {id: 'F1'})
SET f.name = 'Riverside Manufacturing Plant', f.city = 'Columbus', f.state = 'OH';

// ---------------------------------------------------------------------------
// Warehouses
// ---------------------------------------------------------------------------
MERGE (w:Warehouse {id: 'WH1'}) SET w.name = 'North Distribution Center', w.city = 'Chicago', w.state = 'IL';
MERGE (w:Warehouse {id: 'WH2'}) SET w.name = 'Central Distribution Center', w.city = 'Columbus', w.state = 'OH';
MERGE (w:Warehouse {id: 'WH3'}) SET w.name = 'South Distribution Center', w.city = 'Dallas', w.state = 'TX';

// ---------------------------------------------------------------------------
// Regions
// ---------------------------------------------------------------------------
MERGE (r:Region {id: 'R1'}) SET r.name = 'Midwest';
MERGE (r:Region {id: 'R2'}) SET r.name = 'Northeast';
MERGE (r:Region {id: 'R3'}) SET r.name = 'South';
MERGE (r:Region {id: 'R4'}) SET r.name = 'West';
MERGE (r:Region {id: 'R5'}) SET r.name = 'Southwest';

// ---------------------------------------------------------------------------
// Dealers
// ---------------------------------------------------------------------------
MERGE (d:Dealer {id: 'D1'}) SET d.name = 'Great Lakes Auto Parts', d.city = 'Chicago', d.state = 'IL';
MERGE (d:Dealer {id: 'D2'}) SET d.name = 'Atlantic Motors Supply', d.city = 'Boston', d.state = 'MA';
MERGE (d:Dealer {id: 'D3'}) SET d.name = 'Lone Star Auto Distributors', d.city = 'Dallas', d.state = 'TX';
MERGE (d:Dealer {id: 'D4'}) SET d.name = 'Pacific Coast Parts', d.city = 'Los Angeles', d.state = 'CA';
MERGE (d:Dealer {id: 'D5'}) SET d.name = 'Desert Auto Wholesale', d.city = 'Phoenix', d.state = 'AZ';

// ---------------------------------------------------------------------------
// Finished Products
// ---------------------------------------------------------------------------
MERGE (p:Product {id: 'P1'}) SET p.name = 'Standard Brake System', p.category = 'Brake System';
MERGE (p:Product {id: 'P2'}) SET p.name = 'Heavy-Duty Brake System', p.category = 'Brake System';
MERGE (p:Product {id: 'P3'}) SET p.name = 'Sedan Suspension Kit', p.category = 'Suspension Kit';
MERGE (p:Product {id: 'P4'}) SET p.name = 'SUV Suspension Kit', p.category = 'Suspension Kit';
MERGE (p:Product {id: 'P5'}) SET p.name = 'ABS Sensor Module', p.category = 'Sensor Module';
MERGE (p:Product {id: 'P6'}) SET p.name = 'TPMS Sensor Module', p.category = 'Sensor Module';

// ---------------------------------------------------------------------------
// Intermediate Parts
// ---------------------------------------------------------------------------
MERGE (ip:IntermediatePart {id: 'IP1'})  SET ip.name = 'ABS Wheel Speed Sensor';
MERGE (ip:IntermediatePart {id: 'IP2'})  SET ip.name = 'TPMS Sensor';
MERGE (ip:IntermediatePart {id: 'IP3'})  SET ip.name = 'Engine Control Unit (ECU)';
MERGE (ip:IntermediatePart {id: 'IP4'})  SET ip.name = 'Brake Control ECU';
MERGE (ip:IntermediatePart {id: 'IP5'})  SET ip.name = 'Wheel Bearing Assembly';
MERGE (ip:IntermediatePart {id: 'IP6'})  SET ip.name = 'Ball Joint Bearing';
MERGE (ip:IntermediatePart {id: 'IP7'})  SET ip.name = 'Wiring Harness - Brake';
MERGE (ip:IntermediatePart {id: 'IP8'})  SET ip.name = 'Wiring Harness - Suspension';
MERGE (ip:IntermediatePart {id: 'IP9'})  SET ip.name = 'Brake Caliper';
MERGE (ip:IntermediatePart {id: 'IP10'}) SET ip.name = 'Brake Rotor';
MERGE (ip:IntermediatePart {id: 'IP11'}) SET ip.name = 'Brake Pad Set';
MERGE (ip:IntermediatePart {id: 'IP12'}) SET ip.name = 'Coil Spring';
MERGE (ip:IntermediatePart {id: 'IP13'}) SET ip.name = 'Shock Absorber';
MERGE (ip:IntermediatePart {id: 'IP14'}) SET ip.name = 'Sway Bar Link';
MERGE (ip:IntermediatePart {id: 'IP15'}) SET ip.name = 'Pressure Valve Assembly';

// ---------------------------------------------------------------------------
// Raw Materials
// ---------------------------------------------------------------------------
MERGE (rm:RawMaterial {id: 'RM1'})  SET rm.name = 'Hot-Rolled Steel Sheet', rm.category = 'Steel', rm.unit_of_measure = 'kg';
MERGE (rm:RawMaterial {id: 'RM2'})  SET rm.name = 'Steel Rod Stock', rm.category = 'Steel', rm.unit_of_measure = 'kg';
MERGE (rm:RawMaterial {id: 'RM3'})  SET rm.name = 'Aluminum Alloy Billet', rm.category = 'Aluminum', rm.unit_of_measure = 'kg';
MERGE (rm:RawMaterial {id: 'RM4'})  SET rm.name = 'Aluminum Sheet', rm.category = 'Aluminum', rm.unit_of_measure = 'kg';
MERGE (rm:RawMaterial {id: 'RM5'})  SET rm.name = 'Natural Rubber Compound', rm.category = 'Rubber', rm.unit_of_measure = 'kg';
MERGE (rm:RawMaterial {id: 'RM6'})  SET rm.name = 'Synthetic Rubber Compound', rm.category = 'Rubber', rm.unit_of_measure = 'kg';
MERGE (rm:RawMaterial {id: 'RM7'})  SET rm.name = 'Copper Wire', rm.category = 'Copper', rm.unit_of_measure = 'kg';
MERGE (rm:RawMaterial {id: 'RM8'})  SET rm.name = 'Copper Alloy Bar', rm.category = 'Copper', rm.unit_of_measure = 'kg';
MERGE (rm:RawMaterial {id: 'RM9'})  SET rm.name = 'Engineering Plastic Resin (Nylon)', rm.category = 'Plastic', rm.unit_of_measure = 'kg';
MERGE (rm:RawMaterial {id: 'RM10'}) SET rm.name = 'Engineering Plastic Resin (ABS)', rm.category = 'Plastic', rm.unit_of_measure = 'kg';

// ---------------------------------------------------------------------------
// Suppliers (raw materials) — lat/long are static fields for map display, no geocoding API
// ---------------------------------------------------------------------------
MERGE (s:Supplier {id: 'S1'}) SET s.name = 'Great Lakes Steel Co', s.city = 'Cleveland', s.state = 'OH', s.lat = 41.4993, s.long = -81.6944;
MERGE (s:Supplier {id: 'S2'}) SET s.name = 'Titan Aluminum Works', s.city = 'Pittsburgh', s.state = 'PA', s.lat = 40.4406, s.long = -79.9959;
MERGE (s:Supplier {id: 'S3'}) SET s.name = 'Continental Rubber Industries', s.city = 'Akron', s.state = 'OH', s.lat = 41.0814, s.long = -81.5190;
MERGE (s:Supplier {id: 'S4'}) SET s.name = 'Copperline Metals Inc', s.city = 'Phoenix', s.state = 'AZ', s.lat = 33.4484, s.long = -112.0740;
MERGE (s:Supplier {id: 'S5'}) SET s.name = 'PolyForm Plastics Ltd', s.city = 'Houston', s.state = 'TX', s.lat = 29.7604, s.long = -95.3698;
MERGE (s:Supplier {id: 'S6'}) SET s.name = 'Diversified Metals & Materials Inc', s.city = 'Indianapolis', s.state = 'IN', s.lat = 39.7684, s.long = -86.1581;

// ---------------------------------------------------------------------------
// Third-Party Vendors (intermediate parts)
// ---------------------------------------------------------------------------
MERGE (v:ThirdPartyVendor {id: 'V1'}) SET v.name = 'Precision Electronics Corp', v.city = 'San Jose', v.state = 'CA', v.lat = 37.3382, v.long = -121.8863;
MERGE (v:ThirdPartyVendor {id: 'V2'}) SET v.name = 'Midwest Bearing & Motion Co', v.city = 'Detroit', v.state = 'MI', v.lat = 42.3314, v.long = -83.0458;
MERGE (v:ThirdPartyVendor {id: 'V3'}) SET v.name = 'National Harness & Assembly Inc', v.city = 'Toledo', v.state = 'OH', v.lat = 41.6528, v.long = -83.5379;

// ---------------------------------------------------------------------------
// SOURCED_FROM (RawMaterial -> Supplier)
// ---------------------------------------------------------------------------
MATCH (rm:RawMaterial {id: 'RM1'}), (s:Supplier {id: 'S1'})
MERGE (rm)-[r:SOURCED_FROM]->(s) SET r.is_primary = true, r.lead_time_days = 21, r.cost_per_unit = 0.85, r.currency = 'USD';
MATCH (rm:RawMaterial {id: 'RM1'}), (s:Supplier {id: 'S6'})
MERGE (rm)-[r:SOURCED_FROM]->(s) SET r.is_primary = false, r.lead_time_days = 35, r.cost_per_unit = 0.95, r.currency = 'USD';

MATCH (rm:RawMaterial {id: 'RM2'}), (s:Supplier {id: 'S1'})
MERGE (rm)-[r:SOURCED_FROM]->(s) SET r.is_primary = true, r.lead_time_days = 18, r.cost_per_unit = 1.10, r.currency = 'USD';

MATCH (rm:RawMaterial {id: 'RM3'}), (s:Supplier {id: 'S2'})
MERGE (rm)-[r:SOURCED_FROM]->(s) SET r.is_primary = true, r.lead_time_days = 25, r.cost_per_unit = 2.40, r.currency = 'USD';
MATCH (rm:RawMaterial {id: 'RM3'}), (s:Supplier {id: 'S6'})
MERGE (rm)-[r:SOURCED_FROM]->(s) SET r.is_primary = false, r.lead_time_days = 40, r.cost_per_unit = 2.65, r.currency = 'USD';

MATCH (rm:RawMaterial {id: 'RM4'}), (s:Supplier {id: 'S2'})
MERGE (rm)-[r:SOURCED_FROM]->(s) SET r.is_primary = true, r.lead_time_days = 20, r.cost_per_unit = 2.10, r.currency = 'USD';

MATCH (rm:RawMaterial {id: 'RM5'}), (s:Supplier {id: 'S3'})
MERGE (rm)-[r:SOURCED_FROM]->(s) SET r.is_primary = true, r.lead_time_days = 14, r.cost_per_unit = 3.20, r.currency = 'USD';

MATCH (rm:RawMaterial {id: 'RM6'}), (s:Supplier {id: 'S3'})
MERGE (rm)-[r:SOURCED_FROM]->(s) SET r.is_primary = true, r.lead_time_days = 16, r.cost_per_unit = 3.60, r.currency = 'USD';

MATCH (rm:RawMaterial {id: 'RM7'}), (s:Supplier {id: 'S4'})
MERGE (rm)-[r:SOURCED_FROM]->(s) SET r.is_primary = true, r.lead_time_days = 12, r.cost_per_unit = 8.75, r.currency = 'USD';

MATCH (rm:RawMaterial {id: 'RM8'}), (s:Supplier {id: 'S4'})
MERGE (rm)-[r:SOURCED_FROM]->(s) SET r.is_primary = true, r.lead_time_days = 15, r.cost_per_unit = 9.40, r.currency = 'USD';

MATCH (rm:RawMaterial {id: 'RM9'}), (s:Supplier {id: 'S5'})
MERGE (rm)-[r:SOURCED_FROM]->(s) SET r.is_primary = true, r.lead_time_days = 10, r.cost_per_unit = 1.95, r.currency = 'USD';
MATCH (rm:RawMaterial {id: 'RM9'}), (s:Supplier {id: 'S6'})
MERGE (rm)-[r:SOURCED_FROM]->(s) SET r.is_primary = false, r.lead_time_days = 22, r.cost_per_unit = 2.20, r.currency = 'USD';

MATCH (rm:RawMaterial {id: 'RM10'}), (s:Supplier {id: 'S5'})
MERGE (rm)-[r:SOURCED_FROM]->(s) SET r.is_primary = true, r.lead_time_days = 11, r.cost_per_unit = 2.05, r.currency = 'USD';

// ---------------------------------------------------------------------------
// BACKUP_FOR (Supplier -> Supplier) — S6 is the approved diversified backup
// ---------------------------------------------------------------------------
MATCH (backup:Supplier {id: 'S6'}), (primary:Supplier {id: 'S1'}) MERGE (backup)-[:BACKUP_FOR]->(primary);
MATCH (backup:Supplier {id: 'S6'}), (primary:Supplier {id: 'S2'}) MERGE (backup)-[:BACKUP_FOR]->(primary);
MATCH (backup:Supplier {id: 'S6'}), (primary:Supplier {id: 'S5'}) MERGE (backup)-[:BACKUP_FOR]->(primary);

// ---------------------------------------------------------------------------
// USED_IN (RawMaterial -> IntermediatePart)
// ---------------------------------------------------------------------------
UNWIND [
  {rm: 'RM9',  ip: 'IP1',  qty: 0.15, uom: 'kg'},
  {rm: 'RM7',  ip: 'IP1',  qty: 0.05, uom: 'kg'},
  {rm: 'RM9',  ip: 'IP2',  qty: 0.12, uom: 'kg'},
  {rm: 'RM7',  ip: 'IP2',  qty: 0.04, uom: 'kg'},
  {rm: 'RM9',  ip: 'IP3',  qty: 0.30, uom: 'kg'},
  {rm: 'RM7',  ip: 'IP3',  qty: 0.10, uom: 'kg'},
  {rm: 'RM8',  ip: 'IP3',  qty: 0.08, uom: 'kg'},
  {rm: 'RM9',  ip: 'IP4',  qty: 0.32, uom: 'kg'},
  {rm: 'RM7',  ip: 'IP4',  qty: 0.11, uom: 'kg'},
  {rm: 'RM8',  ip: 'IP4',  qty: 0.09, uom: 'kg'},
  {rm: 'RM1',  ip: 'IP5',  qty: 1.80, uom: 'kg'},
  {rm: 'RM1',  ip: 'IP6',  qty: 0.60, uom: 'kg'},
  {rm: 'RM7',  ip: 'IP7',  qty: 0.35, uom: 'kg'},
  {rm: 'RM10', ip: 'IP7',  qty: 0.20, uom: 'kg'},
  {rm: 'RM7',  ip: 'IP8',  qty: 0.30, uom: 'kg'},
  {rm: 'RM10', ip: 'IP8',  qty: 0.18, uom: 'kg'},
  {rm: 'RM3',  ip: 'IP9',  qty: 1.20, uom: 'kg'},
  {rm: 'RM1',  ip: 'IP10', qty: 2.50, uom: 'kg'},
  {rm: 'RM6',  ip: 'IP11', qty: 0.90, uom: 'kg'},
  {rm: 'RM2',  ip: 'IP12', qty: 1.40, uom: 'kg'},
  {rm: 'RM2',  ip: 'IP13', qty: 1.10, uom: 'kg'},
  {rm: 'RM4',  ip: 'IP13', qty: 0.70, uom: 'kg'},
  {rm: 'RM2',  ip: 'IP14', qty: 0.45, uom: 'kg'},
  {rm: 'RM4',  ip: 'IP15', qty: 0.25, uom: 'kg'},
  {rm: 'RM10', ip: 'IP15', qty: 0.15, uom: 'kg'}
] AS row
MATCH (rm:RawMaterial {id: row.rm}), (ip:IntermediatePart {id: row.ip})
MERGE (rm)-[u:USED_IN]->(ip)
SET u.quantity_required = row.qty, u.unit_of_measure = row.uom;

// ---------------------------------------------------------------------------
// PURCHASED_FROM (IntermediatePart -> ThirdPartyVendor)
// ---------------------------------------------------------------------------
UNWIND [
  {ip: 'IP1',  v: 'V1'}, {ip: 'IP2',  v: 'V1'}, {ip: 'IP3',  v: 'V1'}, {ip: 'IP4', v: 'V1'},
  {ip: 'IP5',  v: 'V2'}, {ip: 'IP6',  v: 'V2'}, {ip: 'IP12', v: 'V2'}, {ip: 'IP13', v: 'V2'}, {ip: 'IP14', v: 'V2'},
  {ip: 'IP7',  v: 'V3'}, {ip: 'IP8',  v: 'V3'}, {ip: 'IP9',  v: 'V3'}, {ip: 'IP10', v: 'V3'}, {ip: 'IP11', v: 'V3'}, {ip: 'IP15', v: 'V3'}
] AS row
MATCH (ip:IntermediatePart {id: row.ip}), (v:ThirdPartyVendor {id: row.v})
MERGE (ip)-[:PURCHASED_FROM]->(v);

// ---------------------------------------------------------------------------
// USED_IN (IntermediatePart -> Product)
// ---------------------------------------------------------------------------
UNWIND [
  {ip: 'IP9',  p: 'P1', qty: 2}, {ip: 'IP10', p: 'P1', qty: 2}, {ip: 'IP11', p: 'P1', qty: 4}, {ip: 'IP7', p: 'P1', qty: 1}, {ip: 'IP1', p: 'P1', qty: 2},
  {ip: 'IP9',  p: 'P2', qty: 2}, {ip: 'IP10', p: 'P2', qty: 2}, {ip: 'IP11', p: 'P2', qty: 4}, {ip: 'IP7', p: 'P2', qty: 1}, {ip: 'IP1', p: 'P2', qty: 2}, {ip: 'IP4', p: 'P2', qty: 1},
  {ip: 'IP12', p: 'P3', qty: 4}, {ip: 'IP13', p: 'P3', qty: 4}, {ip: 'IP6', p: 'P3', qty: 2}, {ip: 'IP14', p: 'P3', qty: 2}, {ip: 'IP8', p: 'P3', qty: 1},
  {ip: 'IP12', p: 'P4', qty: 4}, {ip: 'IP13', p: 'P4', qty: 4}, {ip: 'IP6', p: 'P4', qty: 2}, {ip: 'IP14', p: 'P4', qty: 2}, {ip: 'IP8', p: 'P4', qty: 1}, {ip: 'IP5', p: 'P4', qty: 4},
  {ip: 'IP1', p: 'P5', qty: 1}, {ip: 'IP3', p: 'P5', qty: 1}, {ip: 'IP15', p: 'P5', qty: 1},
  {ip: 'IP2', p: 'P6', qty: 1}, {ip: 'IP3', p: 'P6', qty: 1}
] AS row
MATCH (ip:IntermediatePart {id: row.ip}), (p:Product {id: row.p})
MERGE (ip)-[u:USED_IN]->(p)
SET u.quantity_required = row.qty;

// ---------------------------------------------------------------------------
// MANUFACTURED_AT (Product -> Facility)
// ---------------------------------------------------------------------------
MATCH (p:Product), (f:Facility {id: 'F1'})
MERGE (p)-[:MANUFACTURED_AT]->(f);

// ---------------------------------------------------------------------------
// STORED_IN (Product -> Warehouse)
// ---------------------------------------------------------------------------
UNWIND [
  {p: 'P1', w: 'WH1'}, {p: 'P1', w: 'WH2'},
  {p: 'P2', w: 'WH2'}, {p: 'P2', w: 'WH3'},
  {p: 'P3', w: 'WH1'}, {p: 'P3', w: 'WH2'},
  {p: 'P4', w: 'WH2'}, {p: 'P4', w: 'WH3'},
  {p: 'P5', w: 'WH1'}, {p: 'P5', w: 'WH3'},
  {p: 'P6', w: 'WH1'}, {p: 'P6', w: 'WH2'}, {p: 'P6', w: 'WH3'}
] AS row
MATCH (p:Product {id: row.p}), (w:Warehouse {id: row.w})
MERGE (p)-[:STORED_IN]->(w);

// ---------------------------------------------------------------------------
// SUPPLIES (Warehouse -> Dealer)
// ---------------------------------------------------------------------------
UNWIND [
  {w: 'WH1', d: 'D1'}, {w: 'WH2', d: 'D1'},
  {w: 'WH2', d: 'D2'},
  {w: 'WH2', d: 'D3'}, {w: 'WH3', d: 'D3'},
  {w: 'WH3', d: 'D4'},
  {w: 'WH3', d: 'D5'}
] AS row
MATCH (w:Warehouse {id: row.w}), (d:Dealer {id: row.d})
MERGE (w)-[:SUPPLIES]->(d);

// ---------------------------------------------------------------------------
// SERVICES (Dealer -> Region)
// ---------------------------------------------------------------------------
UNWIND [
  {d: 'D1', r: 'R1'}, {d: 'D2', r: 'R2'}, {d: 'D3', r: 'R3'}, {d: 'D4', r: 'R4'}, {d: 'D5', r: 'R5'}
] AS row
MATCH (d:Dealer {id: row.d}), (r:Region {id: row.r})
MERGE (d)-[:SERVICES]->(r);

// ---------------------------------------------------------------------------
// Contracts + HAS_CONTRACT + COVERS
// Dates are relative to "today" = 2026-09-21 (see docs/data_reference.md).
// ---------------------------------------------------------------------------
UNWIND [
  {id: 'C1',  s: 'S1', rm: 'RM1',  start: '2026-03-01', end: '2027-03-01', status: 'active',  value: 1200000, renewal_notice_days: 60, penalty_clause: true},
  {id: 'C2',  s: 'S1', rm: 'RM2',  start: '2025-10-05', end: '2026-10-05', status: 'active',  value: 450000,  renewal_notice_days: 30, penalty_clause: false},
  {id: 'C3',  s: 'S2', rm: 'RM3',  start: '2025-11-15', end: '2026-11-15', status: 'active',  value: 980000,  renewal_notice_days: 45, penalty_clause: true},
  {id: 'C4',  s: 'S2', rm: 'RM4',  start: '2026-06-01', end: '2027-06-01', status: 'active',  value: 520000,  renewal_notice_days: 30, penalty_clause: false},
  {id: 'C5',  s: 'S3', rm: 'RM5',  start: '2026-01-20', end: '2027-01-20', status: 'active',  value: 610000,  renewal_notice_days: 30, penalty_clause: false},
  {id: 'C6',  s: 'S3', rm: 'RM6',  start: '2025-12-10', end: '2026-12-10', status: 'active',  value: 340000,  renewal_notice_days: 45, penalty_clause: true},
  {id: 'C7',  s: 'S4', rm: 'RM7',  start: '2026-04-15', end: '2027-04-15', status: 'active',  value: 890000,  renewal_notice_days: 60, penalty_clause: true},
  {id: 'C8',  s: 'S4', rm: 'RM8',  start: '2025-08-01', end: '2026-08-01', status: 'expired', value: 410000,  renewal_notice_days: 30, penalty_clause: false},
  {id: 'C9',  s: 'S5', rm: 'RM9',  start: '2026-02-28', end: '2027-02-28', status: 'active',  value: 730000,  renewal_notice_days: 30, penalty_clause: false},
  {id: 'C10', s: 'S5', rm: 'RM10', start: '2025-10-01', end: '2026-10-01', status: 'active',  value: 295000,  renewal_notice_days: 30, penalty_clause: false},
  {id: 'C0a', s: 'S1', rm: 'RM1',  start: '2025-01-01', end: '2025-12-31', status: 'expired', value: 1100000, renewal_notice_days: 30, penalty_clause: false},
  {id: 'C0b', s: 'S4', rm: 'RM8',  start: '2024-08-01', end: '2025-08-01', status: 'expired', value: 395000,  renewal_notice_days: 30, penalty_clause: false}
] AS row
MERGE (c:Contract {contract_id: row.id})
SET c.start_date = date(row.start), c.end_date = date(row.end), c.status = row.status,
    c.contract_value = row.value, c.renewal_notice_days = row.renewal_notice_days,
    c.penalty_clause = row.penalty_clause
WITH c, row
MATCH (s:Supplier {id: row.s}), (rm:RawMaterial {id: row.rm})
MERGE (c)-[:COVERS]->(rm)
FOREACH (_ IN CASE WHEN row.status = 'active' THEN [1] ELSE [] END |
  MERGE (s)-[:HAS_CONTRACT]->(c)
)
FOREACH (_ IN CASE WHEN row.status = 'expired' THEN [1] ELSE [] END |
  MERGE (s)-[:PREVIOUSLY_CONTRACTED]->(c)
);
