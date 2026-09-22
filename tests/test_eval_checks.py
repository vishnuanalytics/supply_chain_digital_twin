"""eval/run_eval.py: the answer-checking logic itself. This is the harness that grades
every LLM answer, so a bug here silently makes the eval numbers meaningless - worth
testing directly, especially the word-boundary matching (this project's ID scheme,
e.g. "RM1"/"RM10", makes plain substring matching actively wrong).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))

from run_eval import _contains, check_answer  # noqa: E402


class TestContains:
    def test_finds_a_present_word(self):
        assert _contains("The backup supplier is S6.", "S6") is True

    def test_is_case_insensitive(self):
        assert _contains("the answer is HIGH confidence", "high") is True

    def test_respects_word_boundaries_for_overlapping_ids(self):
        # "RM1" is a substring of "RM10" - naive substring matching would wrongly
        # report a match for RM1 when only RM10 is actually mentioned.
        assert _contains("Affects RM10 only.", "RM1") is False
        assert _contains("Affects RM1 only.", "RM1") is True

    def test_contract_id_boundary_case(self):
        assert _contains("See contract C10 for terms.", "C1") is False
        assert _contains("See contract C1 for terms.", "C1") is True

    def test_returns_false_when_absent(self):
        assert _contains("Nothing relevant here.", "RM3") is False


class TestCheckAnswer:
    def test_passes_with_no_checks_defined(self):
        assert check_answer("any answer", "high", {}) == []

    def test_confidence_in_check_passes(self):
        failures = check_answer("answer", "high", {"confidence_in": ["high", "estimated"]})
        assert failures == []

    def test_confidence_in_check_fails(self):
        failures = check_answer("answer", "low", {"confidence_in": ["high"]})
        assert len(failures) == 1
        assert "confidence" in failures[0]

    def test_must_include_all_requires_every_item(self):
        failures = check_answer("Supplier S1 has RM1.", None, {"must_include_all": ["S1", "RM1"]})
        assert failures == []

    def test_must_include_all_fails_if_one_missing(self):
        failures = check_answer("Supplier S1 only.", None, {"must_include_all": ["S1", "RM1"]})
        assert len(failures) == 1
        assert "RM1" in failures[0]

    def test_must_include_any_passes_with_one_match(self):
        failures = check_answer(
            "Margin % is not modeled in this system.", None,
            {"must_include_any": ["not modeled", "cannot compute"]},
        )
        assert failures == []

    def test_must_include_any_fails_with_no_matches(self):
        failures = check_answer(
            "Here is a definitive number.", None,
            {"must_include_any": ["not modeled", "cannot compute"]},
        )
        assert len(failures) == 1

    def test_must_exclude_fails_when_forbidden_text_present(self):
        failures = check_answer("The warehouse is WH1.", None, {"must_exclude": ["DEALS_WITH"]})
        assert failures == []
        failures = check_answer("Routed via DEALS_WITH relation.", None, {"must_exclude": ["DEALS_WITH"]})
        assert len(failures) == 1

    def test_handles_none_answer_gracefully(self):
        # synthesize can fail to produce any text - the checker must not crash on it.
        failures = check_answer(None, "low", {"must_include_all": ["RM1"]})
        assert len(failures) == 1

    def test_multiple_check_types_combine(self):
        failures = check_answer(
            "Low confidence, no data found.", "high",
            {"confidence_in": ["low", "estimated"], "must_include_all": ["RM1"]},
        )
        # confidence_in passes (high not in [low, estimated] -> fails), must_include_all fails (no RM1)
        assert len(failures) == 2
