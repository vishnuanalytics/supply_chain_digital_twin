"""agent/db.py: the safety guards that keep LLM-generated queries read-only, and the
validation in the deliberate write path (upsert_node/upsert_edge) added for JSON graph
import. No live database needed - these are the pure checks that run before any query
ever reaches Neo4j/Postgres.
"""
from unittest.mock import patch

import pytest

from agent import db


class TestAssertReadOnly:
    @pytest.mark.parametrize("query", [
        "MATCH (n) RETURN n",
        "MATCH (n:Supplier) WHERE n.id = 'S1' RETURN n.name",
        "SELECT * FROM contracts WHERE renewal_status != 'expired'",
        "MATCH (a)-[r]->(b) RETURN type(r)",
    ])
    def test_allows_read_only_queries(self, query):
        db._assert_read_only(query)  # should not raise

    @pytest.mark.parametrize("query", [
        "MATCH (n) DETACH DELETE n",
        "CREATE (n:Supplier {id: 'X'})",
        "MERGE (n:Supplier {id: 'X'})",
        "MATCH (n) SET n.name = 'hacked'",
        "DROP TABLE contracts",
        "DELETE FROM contracts",
        "UPDATE contracts SET contract_value = 0",
        "INSERT INTO contracts VALUES (1)",
        "MATCH (n) CALL apoc.create.setProperty(n, 'x', 1)",
    ])
    def test_blocks_write_queries(self, query):
        with pytest.raises(db.QuerySafetyError):
            db._assert_read_only(query)

    def test_is_case_insensitive(self):
        with pytest.raises(db.QuerySafetyError):
            db._assert_read_only("match (n) detach delete n")

    def test_does_not_false_positive_on_substrings(self):
        # "created_at" contains "create" but isn't the CREATE keyword - word boundaries
        # must be respected, or every column named like this would be wrongly blocked.
        db._assert_read_only("SELECT created_at FROM invoices")


class TestPromptInjectionResilience:
    """agent/db.py's _assert_read_only is the last line of defense if an LLM node ever
    gets tricked (via a crafted question, or - the subtler threat - via injected text
    sitting in retrieved DATA that later gets fed back into a prompt) into generating a
    destructive query. These payloads model realistic ways a confused or jailbroken LLM
    might phrase a write, not just the straightforward cases above - see
    docs/security_notes.md for the live, full-pipeline version of this test.
    """

    @pytest.mark.parametrize("query", [
        # Semicolon-chained: a legitimate-looking read followed by a write - the regex
        # is a global search, not anchored to the first statement, so this must still block.
        "MATCH (n:Supplier) RETURN n; MATCH (m) DETACH DELETE m",
        "SELECT * FROM contracts; DROP TABLE contracts;",
        # The write keyword mid-query, after real-looking read clauses - a jailbroken
        # LLM asked to "also fix the data while you're there" would plausibly write this.
        "MATCH (s:Supplier {id: 'S1'}) SET s.risk_rating = 'trusted' RETURN s",
        "MATCH (n:Supplier) WHERE n.id = 'S1' WITH n MERGE (n)-[:TRUSTED]->(n) RETURN n",
        # Mixed case / whitespace tricks - a naive keyword-list check that assumed
        # exact-case or single-space formatting would miss these.
        "MaTcH (n) DeTaCh DeLeTe n",
        "MATCH (n)\nDETACH\nDELETE n",
        # Comment-prefixed - trying to look like an aside rather than an instruction.
        "MATCH (n:Supplier) RETURN n // then CREATE (m:Backdoor)",
    ])
    def test_blocks_realistic_injection_style_payloads(self, query):
        with pytest.raises(db.QuerySafetyError):
            db._assert_read_only(query)

    def test_deliberate_over_blocking_tradeoff_documented_here(self):
        # A real company literally named "Create Corp" would trip this guard on a
        # perfectly innocent read query - \bCREATE\b matches "Create" as a standalone
        # word regardless of surrounding context. This is accepted as the right
        # tradeoff: the failure mode is "can't search for a name containing a SQL/Cypher
        # keyword" (a rare, recoverable annoyance), not "a write silently executes" (a
        # real incident) - full query parsing to disambiguate would be real complexity
        # for a portfolio-scale project's safety guard to carry. Documented, not "fixed".
        with pytest.raises(db.QuerySafetyError):
            db._assert_read_only("MATCH (n) WHERE n.name CONTAINS 'Create Corp' RETURN n")


class TestToNative:
    def test_passes_through_plain_values(self):
        assert db._to_native("hello") == "hello"
        assert db._to_native(42) == 42
        assert db._to_native(None) is None

    def test_recurses_into_nested_dicts_and_lists(self):
        nested = {"a": [{"b": 1}, {"c": 2}]}
        assert db._to_native(nested) == nested

    def test_converts_neo4j_temporal_types(self):
        import datetime

        import neo4j.time

        result = db._to_native(neo4j.time.Date(2026, 3, 1))
        assert result == datetime.date(2026, 3, 1)
        assert isinstance(result, datetime.date)

    def test_converts_temporal_types_nested_in_a_dict(self):
        import datetime

        import neo4j.time

        result = db._to_native({"start_date": neo4j.time.Date(2026, 3, 1)})
        assert result == {"start_date": datetime.date(2026, 3, 1)}


class TestIdPropertyForLabel:
    def test_contract_uses_contract_id(self):
        assert db.id_property_for_label("Contract") == "contract_id"

    @pytest.mark.parametrize("label", [
        "Facility", "Warehouse", "Region", "Dealer", "Product",
        "IntermediatePart", "RawMaterial", "Supplier", "ThirdPartyVendor",
    ])
    def test_everything_else_uses_id(self, label):
        assert db.id_property_for_label(label) == "id"


class TestUpsertNodeValidation:
    def test_rejects_unknown_label_without_touching_the_driver(self):
        with patch("agent.db.get_neo4j_driver") as mock_driver:
            with pytest.raises(ValueError, match="Unknown node label"):
                db.upsert_node("NotARealLabel", {"id": "X1"})
            mock_driver.assert_not_called()

    def test_rejects_missing_id_property(self):
        with patch("agent.db.get_neo4j_driver"):
            with pytest.raises(ValueError, match="'id'"):
                db.upsert_node("Supplier", {"name": "No ID here"})

    def test_rejects_missing_contract_id_for_contract_label(self):
        with patch("agent.db.get_neo4j_driver"):
            with pytest.raises(ValueError, match="'contract_id'"):
                db.upsert_node("Contract", {"status": "active"})

    def test_valid_node_reaches_the_driver(self):
        with patch("agent.db.get_neo4j_driver") as mock_driver:
            session = mock_driver.return_value.session.return_value.__enter__.return_value
            node_id = db.upsert_node("Supplier", {"id": "S99", "name": "New Co"})
            assert node_id == "S99"
            session.run.assert_called_once()
            query = session.run.call_args[0][0]
            assert "Supplier" in query
            assert "MERGE" in query


class TestUpsertEdgeValidation:
    def test_rejects_unknown_relationship_type_without_touching_the_driver(self):
        with patch("agent.db.get_neo4j_driver") as mock_driver:
            with pytest.raises(ValueError, match="Unknown relationship type"):
                db.upsert_edge("RM1", "S1", "NOT_A_REAL_TYPE", {})
            mock_driver.assert_not_called()

    def test_raises_when_endpoints_not_found(self):
        with patch("agent.db.get_neo4j_driver") as mock_driver:
            session = mock_driver.return_value.session.return_value.__enter__.return_value
            session.run.return_value.single.return_value = None
            with pytest.raises(ValueError, match="Couldn't find both"):
                db.upsert_edge("RM1", "MISSING", "SOURCED_FROM", {})

    def test_valid_edge_reaches_the_driver(self):
        with patch("agent.db.get_neo4j_driver") as mock_driver:
            session = mock_driver.return_value.session.return_value.__enter__.return_value
            session.run.return_value.single.return_value = {"matched": "RM1"}
            db.upsert_edge("RM1", "S1", "SOURCED_FROM", {"cost_per_unit": 1.5})
            query = session.run.call_args[0][0]
            params = session.run.call_args[0][1]
            assert "SOURCED_FROM" in query
            assert params["source_id"] == "RM1"
            assert params["properties"]["cost_per_unit"] == 1.5
