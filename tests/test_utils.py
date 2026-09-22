"""agent/utils.py: parsing LLM output, which is never perfectly clean (code fences,
surrounding prose, occasional junk before/after the actual JSON)."""
import pytest

from agent.utils import extract_json, strip_code_fence


class TestStripCodeFence:
    def test_removes_fenced_json_block(self):
        text = '```json\n{"a": 1}\n```'
        assert strip_code_fence(text) == '{"a": 1}'

    def test_removes_fence_with_no_language_tag(self):
        text = '```\n{"a": 1}\n```'
        assert strip_code_fence(text) == '{"a": 1}'

    def test_leaves_unfenced_text_untouched(self):
        text = '{"a": 1}'
        assert strip_code_fence(text) == '{"a": 1}'

    def test_strips_surrounding_whitespace(self):
        text = '  \n{"a": 1}\n  '
        assert strip_code_fence(text) == '{"a": 1}'


class TestExtractJson:
    def test_parses_clean_json(self):
        assert extract_json('{"query_type": "graph_traversal"}') == {"query_type": "graph_traversal"}

    def test_parses_json_with_surrounding_prose(self):
        text = 'Here is the answer:\n{"query_type": "graph_traversal"}\nHope that helps!'
        assert extract_json(text) == {"query_type": "graph_traversal"}

    def test_parses_fenced_json(self):
        text = '```json\n{"valid": true, "reason": "looks good"}\n```'
        assert extract_json(text) == {"valid": True, "reason": "looks good"}

    def test_parses_nested_objects(self):
        text = '{"query_type": "compound_multi_hop", "simulation_params": {"entity_name": "aluminum"}}'
        result = extract_json(text)
        assert result["simulation_params"]["entity_name"] == "aluminum"

    def test_raises_on_no_json_object(self):
        with pytest.raises(ValueError):
            extract_json("no JSON here at all")

    def test_raises_on_empty_string(self):
        with pytest.raises(ValueError):
            extract_json("")

    def test_uses_first_brace_to_last_brace_span(self):
        # A known limitation, not a bug: text containing two separate JSON objects
        # gets treated as one span from the first "{" to the last "}" - only matters
        # if a real LLM response ever legitimately contains two, which none do today.
        text = '{"a": 1} and also {"b": 2}'
        with pytest.raises(ValueError):
            extract_json(text)  # the combined span isn't valid JSON, so this should fail loudly, not silently pick one
