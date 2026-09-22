"""agent/nodes/simulate.py: the deterministic what-if math (disruption/capacity/cost
impact) - hand-coded specifically because it needs reliable arithmetic, so it's the
part of the agent most worth unit-testing directly rather than only through the LLM-
dependent eval harness. All DB calls are mocked - these are pure logic tests.
"""
from unittest.mock import patch

from agent.nodes.simulate import (
    resolve_entity,
    simulate_capacity,
    simulate_cost_impact,
    simulate_disruption,
)


class TestResolveEntity:
    def test_returns_empty_for_no_name(self):
        assert resolve_entity(None, ["Supplier"]) == []
        assert resolve_entity("", ["Supplier"]) == []

    def test_strips_role_stopwords_from_keywords(self):
        with patch("agent.nodes.simulate.db.run_cypher") as mock_cypher:
            mock_cypher.return_value = []
            resolve_entity("our aluminum supplier", ["Supplier"])
            keywords = mock_cypher.call_args[0][1]["keywords"]
            assert "aluminum" in keywords
            assert "supplier" not in keywords
            assert "our" not in keywords

    def test_exact_match_ranks_above_partial_match(self):
        with patch("agent.nodes.simulate.db.run_cypher") as mock_cypher:
            mock_cypher.return_value = [
                {"label": "Product", "id": "P3", "name": "Sedan Suspension Kit"},
                {"label": "Product", "id": "P4", "name": "SUV Suspension Kit"},
            ]
            results = resolve_entity("SUV Suspension Kit", ["Product"])
            assert results[0]["id"] == "P4"  # exact match must sort first

    def test_entity_type_hint_prefers_matching_label(self):
        with patch("agent.nodes.simulate.db.run_cypher") as mock_cypher:
            mock_cypher.return_value = [
                {"label": "ThirdPartyVendor", "id": "V1", "name": "Precision Electronics Corp"},
                {"label": "Supplier", "id": "S1", "name": "Precision Metals Co"},
            ]
            results = resolve_entity("Precision", ["Supplier", "ThirdPartyVendor"], entity_type="supplier")
            assert results[0]["label"] == "Supplier"


class TestSimulateDisruption:
    def test_returns_error_when_entity_not_found(self):
        with patch("agent.nodes.simulate.resolve_entity", return_value=[]):
            result = simulate_disruption("Nonexistent Co", 21)
            assert "error" in result

    def test_defaults_delay_to_21_days_when_unspecified(self):
        with patch("agent.nodes.simulate.resolve_entity", return_value=[
            {"label": "Supplier", "id": "S1", "name": "Great Lakes Steel Co"}
        ]), patch("agent.nodes.simulate.db.run_cypher") as mock_cypher, \
             patch("agent.nodes.simulate.db.run_sql", return_value=[]):
            mock_cypher.return_value = []
            result = simulate_disruption("Great Lakes Steel Co", None)
            assert result["delay_days"] == 21

    def test_risk_level_high_when_at_or_below_reorder_point(self):
        with patch("agent.nodes.simulate.resolve_entity", return_value=[
            {"label": "Supplier", "id": "S1", "name": "Great Lakes Steel Co"}
        ]), patch("agent.nodes.simulate.db.run_cypher") as mock_cypher, \
             patch("agent.nodes.simulate.db.run_sql") as mock_sql:
            mock_cypher.side_effect = [
                [{"id": "RM1", "name": "Hot-Rolled Steel Sheet", "lead_time_days": 25, "is_primary": True}],
                [],  # affected_products query for RM1
            ]
            mock_sql.return_value = [{"quantity_on_hand": 100, "reorder_point": 500, "unit_of_measure": "kg"}]
            result = simulate_disruption("Great Lakes Steel Co", 21)
            assert result["affected_materials"][0]["risk_level"] == "high"

    def test_risk_level_low_with_healthy_buffer(self):
        with patch("agent.nodes.simulate.resolve_entity", return_value=[
            {"label": "Supplier", "id": "S1", "name": "Great Lakes Steel Co"}
        ]), patch("agent.nodes.simulate.db.run_cypher") as mock_cypher, \
             patch("agent.nodes.simulate.db.run_sql") as mock_sql:
            mock_cypher.side_effect = [
                [{"id": "RM1", "name": "Hot-Rolled Steel Sheet", "lead_time_days": 25, "is_primary": True}],
                [],
            ]
            mock_sql.return_value = [{"quantity_on_hand": 5000, "reorder_point": 500, "unit_of_measure": "kg"}]
            result = simulate_disruption("Great Lakes Steel Co", 21)
            assert result["affected_materials"][0]["risk_level"] == "low"

    def test_effective_lead_time_adds_delay_to_normal(self):
        with patch("agent.nodes.simulate.resolve_entity", return_value=[
            {"label": "Supplier", "id": "S1", "name": "Great Lakes Steel Co"}
        ]), patch("agent.nodes.simulate.db.run_cypher") as mock_cypher, \
             patch("agent.nodes.simulate.db.run_sql", return_value=[]):
            mock_cypher.side_effect = [
                [{"id": "RM1", "name": "Hot-Rolled Steel Sheet", "lead_time_days": 25, "is_primary": True}],
                [],
            ]
            result = simulate_disruption("Great Lakes Steel Co", 21)
            assert result["affected_materials"][0]["effective_lead_time_days"] == 46


class TestSimulateCapacity:
    def test_returns_error_when_product_not_found(self):
        with patch("agent.nodes.simulate.resolve_entity", return_value=[]):
            result = simulate_capacity("Nonexistent Product", 500, 30)
            assert "error" in result

    def test_returns_error_when_no_capacity_data(self):
        with patch("agent.nodes.simulate.resolve_entity", return_value=[
            {"label": "Product", "id": "P1", "name": "Standard Brake System"}
        ]), patch("agent.nodes.simulate.db.run_sql", return_value=[]):
            result = simulate_capacity("Standard Brake System", 500, 30)
            assert "error" in result

    def test_feasible_when_capacity_exceeds_request_plus_backlog(self):
        with patch("agent.nodes.simulate.resolve_entity", return_value=[
            {"label": "Product", "id": "P1", "name": "Standard Brake System"}
        ]), patch("agent.nodes.simulate.db.run_sql") as mock_sql:
            mock_sql.side_effect = [
                [{"max_units_per_week": 1000.0}],
                [{"backlog": 200}],
            ]
            result = simulate_capacity("Standard Brake System", 500, 7)
            # theoretical = 1000 * 1 week = 1000; available = 1000 - 200 = 800 >= 500
            assert result["feasible"] is True
            assert result["available_capacity"] == 800.0

    def test_infeasible_when_backlog_plus_request_exceeds_capacity(self):
        with patch("agent.nodes.simulate.resolve_entity", return_value=[
            {"label": "Product", "id": "P1", "name": "Standard Brake System"}
        ]), patch("agent.nodes.simulate.db.run_sql") as mock_sql:
            mock_sql.side_effect = [
                [{"max_units_per_week": 100.0}],
                [{"backlog": 50}],
            ]
            result = simulate_capacity("Standard Brake System", 500, 7)
            # theoretical = 100; available = 100 - 50 = 50 < 500
            assert result["feasible"] is False


class TestSimulateCostImpact:
    def test_returns_error_when_material_not_found(self):
        with patch("agent.nodes.simulate.resolve_entity", return_value=[]):
            result = simulate_cost_impact("Unobtainium", 15)
            assert "error" in result

    def test_returns_error_when_no_primary_sourcing(self):
        with patch("agent.nodes.simulate.resolve_entity", return_value=[
            {"label": "RawMaterial", "id": "RM1", "name": "Hot-Rolled Steel Sheet"}
        ]), patch("agent.nodes.simulate.db.run_cypher", return_value=[]):
            result = simulate_cost_impact("Hot-Rolled Steel Sheet", 15)
            assert "error" in result

    def test_computes_new_cost_per_unit_correctly(self):
        with patch("agent.nodes.simulate.resolve_entity", return_value=[
            {"label": "RawMaterial", "id": "RM1", "name": "Hot-Rolled Steel Sheet"}
        ]), patch("agent.nodes.simulate.db.run_cypher") as mock_cypher:
            mock_cypher.side_effect = [
                [{"cost_per_unit": 1.0, "currency": "USD", "supplier_name": "Great Lakes Steel Co"}],
                [],  # no BOM usage rows
            ]
            result = simulate_cost_impact("Hot-Rolled Steel Sheet", 15)
            assert result["new_cost_per_unit"] == 1.15

    def test_aggregates_multiple_paths_to_the_same_product(self):
        with patch("agent.nodes.simulate.resolve_entity", return_value=[
            {"label": "RawMaterial", "id": "RM1", "name": "Hot-Rolled Steel Sheet"}
        ]), patch("agent.nodes.simulate.db.run_cypher") as mock_cypher:
            mock_cypher.side_effect = [
                [{"cost_per_unit": 2.0, "currency": "USD", "supplier_name": "Great Lakes Steel Co"}],
                [
                    {"product_id": "P1", "product_name": "Standard Brake System",
                     "rm_qty_per_part": 1.0, "part_qty_per_product": 2.0},
                    {"product_id": "P1", "product_name": "Standard Brake System",
                     "rm_qty_per_part": 0.5, "part_qty_per_product": 1.0},
                ],
            ]
            result = simulate_cost_impact("Hot-Rolled Steel Sheet", 10)
            # two paths to P1: 1.0*2.0=2.0 and 0.5*1.0=0.5 -> aggregated qty 2.5/unit
            assert len(result["product_impacts"]) == 1
            assert result["product_impacts"][0]["material_qty_per_unit"] == 2.5
