"""Streamlit entrypoint. Run with: streamlit run app.py"""
import streamlit as st

from ui.sidebar import render_sidebar
from ui.tabs.about import render_about_tab
from ui.tabs.ask import render_ask_tab
from ui.tabs.billing import render_billing_tab
from ui.tabs.graph_explorer import render_graph_explorer_tab
from ui.theme import inject_css

st.set_page_config(page_title="Supply Chain Digital Twin", page_icon="🔗", layout="wide")
inject_css()
render_sidebar()

tab_ask, tab_graph, tab_billing, tab_about = st.tabs(
    ["💬 Ask a Question", "🕸️ Graph Explorer", "📄 Contracts & Billing", "ℹ️ About / Architecture"]
)

with tab_ask:
    render_ask_tab()

with tab_graph:
    render_graph_explorer_tab()

with tab_billing:
    render_billing_tab()

with tab_about:
    render_about_tab()
