"""ui/sidebar.py's manual model picker: which (provider, model) choices get offered
(only for providers with a configured API key) and how the selected choice is decoded
back into an llm_client.set_override() call. Pure logic, no live provider calls -
st.session_state works as a plain dict outside a real `streamlit run` (confirmed:
Streamlit only warns about this, it doesn't actually block get/set), which is enough
to exercise current_llm_override() without needing AppTest here.
"""
from unittest.mock import patch

import streamlit as st

from ui import sidebar


class TestAvailableModelChoices:
    def test_includes_only_providers_with_a_configured_key(self):
        with patch("agent.config.GROQ_API_KEY", "gsk_real"), \
             patch("agent.config.OPENROUTER_API_KEY", ""), \
             patch("agent.config.ANTHROPIC_API_KEY", ""), \
             patch("agent.config.GEMINI_API_KEY", ""):
            choices = sidebar._available_model_choices()
        providers = {provider for _, provider, _ in choices}
        assert providers == {"groq"}

    def test_includes_all_configured_providers(self):
        with patch("agent.config.GROQ_API_KEY", "gsk_real"), \
             patch("agent.config.OPENROUTER_API_KEY", "sk-or-real"), \
             patch("agent.config.ANTHROPIC_API_KEY", "sk-ant-real"), \
             patch("agent.config.GEMINI_API_KEY", "AQ.real"):
            choices = sidebar._available_model_choices()
        providers = {provider for _, provider, _ in choices}
        assert providers == {"groq", "openrouter", "anthropic", "gemini"}

    def test_no_keys_configured_yields_no_choices(self):
        with patch("agent.config.GROQ_API_KEY", ""), \
             patch("agent.config.OPENROUTER_API_KEY", ""), \
             patch("agent.config.ANTHROPIC_API_KEY", ""), \
             patch("agent.config.GEMINI_API_KEY", ""):
            assert sidebar._available_model_choices() == []

    def test_labels_are_human_readable(self):
        with patch("agent.config.GROQ_API_KEY", "gsk_real"), \
             patch("agent.config.OPENROUTER_API_KEY", ""), \
             patch("agent.config.ANTHROPIC_API_KEY", ""), \
             patch("agent.config.GEMINI_API_KEY", ""):
            choices = sidebar._available_model_choices()
        labels = [label for label, _, _ in choices]
        assert any("Groq" in label and "openai/gpt-oss-120b" in label for label in labels)


class TestCurrentLlmOverride:
    def test_auto_choice_returns_none_none(self):
        st.session_state["llm_choice"] = sidebar.AUTO_CHOICE
        assert sidebar.current_llm_override() == (None, None)

    def test_missing_choice_defaults_to_auto(self):
        st.session_state.pop("llm_choice", None)
        assert sidebar.current_llm_override() == (None, None)

    def test_specific_choice_decodes_provider_and_model(self):
        st.session_state["llm_choice"] = "groq::qwen/qwen3.8-27b"
        assert sidebar.current_llm_override() == ("groq", "qwen/qwen3.8-27b")

    def test_openrouter_model_id_containing_colon_still_decodes_correctly(self):
        # OpenRouter's own model IDs end in ":free" - partition on the FIRST "::"
        # separator must not get confused by that second colon.
        st.session_state["llm_choice"] = "openrouter::nvidia/nemotron-3-super-120b-a12b:free"
        assert sidebar.current_llm_override() == ("openrouter", "nvidia/nemotron-3-super-120b-a12b:free")
