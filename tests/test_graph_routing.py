"""agent/graph.py's routing functions: pure state-in/string-out logic, no LLM/DB call,
so testable directly. Not previously covered - added alongside the new sales_analysis
query_type to confirm it routes the same way as the other Postgres-only types
(contract_status/inventory_lookup/cost_analysis), which contract_status already
exercises the same code path for.
"""
from agent.graph import POSTGRES_ONLY_TYPES, _route_after_classify, _route_after_neo4j, _route_after_validate


class TestRouteAfterClassify:
    def test_requires_simulation_always_wins_regardless_of_query_type(self):
        state = {"requires_simulation": True, "query_type": "sales_analysis"}
        assert _route_after_classify(state) == "simulate_scenario"

    def test_semantic_search_routes_to_query_semantic(self):
        state = {"requires_simulation": False, "query_type": "semantic_search"}
        assert _route_after_classify(state) == "query_semantic"

    def test_sales_analysis_routes_straight_to_postgres(self):
        state = {"requires_simulation": False, "query_type": "sales_analysis"}
        assert _route_after_classify(state) == "query_postgres"

    def test_every_postgres_only_type_routes_to_postgres(self):
        for query_type in POSTGRES_ONLY_TYPES:
            state = {"requires_simulation": False, "query_type": query_type}
            assert _route_after_classify(state) == "query_postgres", query_type

    def test_graph_traversal_and_compound_multi_hop_start_in_neo4j(self):
        for query_type in ("graph_traversal", "compound_multi_hop"):
            state = {"requires_simulation": False, "query_type": query_type}
            assert _route_after_classify(state) == "query_neo4j", query_type


class TestRouteAfterNeo4j:
    def test_compound_multi_hop_continues_to_postgres(self):
        assert _route_after_neo4j({"query_type": "compound_multi_hop"}) == "query_postgres"

    def test_plain_graph_traversal_goes_straight_to_validate(self):
        assert _route_after_neo4j({"query_type": "graph_traversal"}) == "validate_results"


class TestRouteAfterValidate:
    def test_valid_result_goes_to_synthesize(self):
        assert _route_after_validate({"validation_passed": True, "retry_count": 0}) == "synthesize"

    def test_invalid_result_with_retries_left_goes_back_to_classify(self):
        assert _route_after_validate({"validation_passed": False, "retry_count": 0}) == "classify_query"

    def test_invalid_result_after_retries_exhausted_gives_up_to_synthesize(self):
        from agent.nodes.validate import MAX_RETRIES
        state = {"validation_passed": False, "retry_count": MAX_RETRIES + 1}
        assert _route_after_validate(state) == "synthesize"
