"""agent/llm_client.py: the provider fallback chain. All three provider functions are
mocked - these tests are about the *fallback/retry control flow* (order, same-provider
retry on empty content, giving up), not about any real provider's API.

Patches go through `_PROVIDER_FNS` (via patch.dict), not the `_call_*` names directly:
`complete()` looks up `_PROVIDER_FNS[provider]`, a module-level dict built once at
import time with direct references to the (already `@traceable`-decorated) functions -
patching `agent.llm_client._call_groq` rebinds the module attribute but does nothing to
that dict's already-captured reference, so the real function (and a real network call)
would run right past a patch aimed at the name instead of the dict entry.
"""
from unittest.mock import MagicMock, patch

import pytest

from agent import llm_client
from agent.llm_client import ProviderError


@pytest.fixture(autouse=True)
def provider_order():
    with patch("agent.config.LLM_PROVIDER_ORDER", ["groq", "openrouter", "anthropic"]):
        yield


class TestComplete:
    def test_returns_first_provider_result_on_success(self):
        mock_or = MagicMock()
        with patch.dict(llm_client._PROVIDER_FNS, {
            "groq": lambda *a, **k: ("hello", "model-a"),
            "openrouter": mock_or,
        }):
            result = llm_client.complete("system", "user")
            assert result.content == "hello"
            assert result.provider == "groq"
            assert result.model == "model-a"
            mock_or.assert_not_called()

    def test_falls_back_to_next_provider_on_error(self):
        def failing_groq(*a, **k):
            raise ProviderError("no key")

        with patch.dict(llm_client._PROVIDER_FNS, {
            "groq": failing_groq,
            "openrouter": lambda *a, **k: ("hi from openrouter", "model-b"),
        }):
            result = llm_client.complete("system", "user")
            assert result.provider == "openrouter"
            assert result.content == "hi from openrouter"

    def test_falls_back_through_all_three_in_order(self):
        def failing(*a, **k):
            raise ProviderError("fail")

        with patch.dict(llm_client._PROVIDER_FNS, {
            "groq": failing,
            "openrouter": failing,
            "anthropic": lambda *a, **k: ("final answer", "claude"),
        }):
            result = llm_client.complete("system", "user")
            assert result.provider == "anthropic"

    def test_raises_runtime_error_when_all_providers_fail(self):
        def failing(*a, **k):
            raise ProviderError("fail")

        with patch.dict(llm_client._PROVIDER_FNS, {"groq": failing, "openrouter": failing, "anthropic": failing}):
            with pytest.raises(RuntimeError, match="All LLM providers failed"):
                llm_client.complete("system", "user")

    def test_empty_content_is_treated_as_a_provider_failure(self):
        with patch.dict(llm_client._PROVIDER_FNS, {
            "groq": lambda *a, **k: ("   ", "model-a"),
            "openrouter": lambda *a, **k: ("real content", "model-b"),
        }):
            result = llm_client.complete("system", "user")
            assert result.provider == "openrouter"

    def test_retries_same_provider_once_on_empty_content_before_falling_through(self):
        calls = {"groq": 0}

        def flaky_groq(*args, **kwargs):
            calls["groq"] += 1
            if calls["groq"] == 1:
                return "", "model-a"
            return "recovered on retry", "model-a"

        with patch.dict(llm_client._PROVIDER_FNS, {"groq": flaky_groq}):
            result = llm_client.complete("system", "user")
            assert calls["groq"] == 2
            assert result.content == "recovered on retry"
            assert result.provider == "groq"

    def test_non_empty_content_error_does_not_retry_same_provider(self):
        calls = {"groq": 0}

        def always_fails(*args, **kwargs):
            calls["groq"] += 1
            raise ProviderError("rate limited")

        with patch.dict(llm_client._PROVIDER_FNS, {
            "groq": always_fails,
            "openrouter": lambda *a, **k: ("ok", "model-b"),
        }):
            llm_client.complete("system", "user")
            assert calls["groq"] == 1  # no retry for a non-empty-content error

    def test_unknown_provider_in_order_is_skipped_gracefully(self):
        with patch("agent.config.LLM_PROVIDER_ORDER", ["not_a_real_provider", "groq"]), \
             patch.dict(llm_client._PROVIDER_FNS, {"groq": lambda *a, **k: ("ok", "model-a")}):
            result = llm_client.complete("system", "user")
            assert result.provider == "groq"


class TestManualOverride:
    """The sidebar's model picker (ui/sidebar.py) forces a single provider/model via
    set_override() - deliberately no cross-provider fallback when a specific model is
    manually chosen, unlike the normal Auto chain above."""

    def teardown_method(self):
        # Guard against a test failure leaving the contextvar set and bleeding into a
        # later test - set_override's own docstring warns about exactly this class of bug.
        llm_client.reset_override(llm_client.set_override(None))

    def test_override_forces_the_chosen_provider_even_when_earlier_in_chain_would_win(self):
        groq_call = MagicMock()
        with patch.dict(llm_client._PROVIDER_FNS, {
            "groq": groq_call,
            "gemini": lambda *a, **k: ("from gemini", "gemini-3.6-flash"),
        }):
            token = llm_client.set_override("gemini")
            try:
                result = llm_client.complete("system", "user")
            finally:
                llm_client.reset_override(token)
            assert result.provider == "gemini"
            assert result.model == "gemini-3.6-flash"
            groq_call.assert_not_called()  # Auto would have tried groq first; override must not

    def test_override_passes_the_chosen_model_through_to_the_provider_fn(self):
        seen = {}

        def fake_groq(system, user, max_tokens, model=None):
            seen["model"] = model
            return "ok", model

        with patch.dict(llm_client._PROVIDER_FNS, {"groq": fake_groq}):
            token = llm_client.set_override("groq", "qwen/qwen3.8-27b")
            try:
                llm_client.complete("system", "user")
            finally:
                llm_client.reset_override(token)
        assert seen["model"] == "qwen/qwen3.8-27b"

    def test_override_does_not_fall_back_to_other_providers_on_failure(self):
        def failing_gemini(*a, **k):
            raise llm_client.ProviderError("rate limited")

        openrouter_call = MagicMock()
        with patch.dict(llm_client._PROVIDER_FNS, {"gemini": failing_gemini, "openrouter": openrouter_call}):
            token = llm_client.set_override("gemini")
            try:
                with pytest.raises(RuntimeError, match="Manually selected gemini failed"):
                    llm_client.complete("system", "user")
            finally:
                llm_client.reset_override(token)
        openrouter_call.assert_not_called()

    def test_no_override_uses_the_normal_auto_chain(self):
        with patch.dict(llm_client._PROVIDER_FNS, {"groq": lambda *a, **k: ("auto works", "model-a")}):
            token = llm_client.set_override(None)
            try:
                result = llm_client.complete("system", "user")
            finally:
                llm_client.reset_override(token)
            assert result.provider == "groq"


class TestKnownModels:
    def test_every_provider_fn_has_at_least_one_known_model(self):
        for provider in llm_client._PROVIDER_FNS:
            assert llm_client.KNOWN_MODELS.get(provider), f"{provider} has no KNOWN_MODELS entry"

    def test_every_known_models_provider_is_a_real_provider_fn(self):
        for provider in llm_client.KNOWN_MODELS:
            assert provider in llm_client._PROVIDER_FNS


class TestCallGemini:
    def test_raises_when_no_api_key(self):
        with patch("agent.config.GEMINI_API_KEY", ""):
            with pytest.raises(llm_client.ProviderError, match="GEMINI_API_KEY"):
                llm_client._call_gemini("system", "user", 100)
