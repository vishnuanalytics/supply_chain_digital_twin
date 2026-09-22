"""Streamlit entrypoint. Run with: streamlit run app.py"""
import os

import streamlit as st

# Streamlit Community Cloud's "Secrets" UI populates st.secrets, not necessarily
# os.environ - bridge them here, before any other import, since agent.config reads
# env vars at import time via os.getenv(). This makes the exact same config code work
# unchanged both locally (via .env, python-dotenv) and deployed (via Cloud secrets).
# setdefault so a real OS/*.env* value always wins if one is already set. A no-op
# locally, where no secrets.toml exists at all.
try:
    for _key, _value in st.secrets.items():
        os.environ.setdefault(_key, str(_value))
except Exception:  # noqa: BLE001 - no secrets configured is the normal local case
    pass

from ui.sidebar import render_sidebar
from ui.tabs.about import render_about_tab
from ui.tabs.ask import render_ask_tab
from ui.tabs.billing import render_billing_tab
from ui.tabs.graph_explorer import render_graph_explorer_tab
from ui.tabs.sales import render_sales_tab
from ui.theme import inject_css

st.set_page_config(page_title="Supply Chain Digital Twin", page_icon="🔗", layout="wide")
inject_css()
render_sidebar()

tab_ask, tab_graph, tab_billing, tab_sales, tab_about = st.tabs(
    ["💬 Ask a Question", "🕸️ Graph Explorer", "📄 Contracts & Billing", "📈 Sales", "ℹ️ About / Architecture"]
)

with tab_ask:
    render_ask_tab()

with tab_graph:
    render_graph_explorer_tab()

with tab_billing:
    render_billing_tab()

with tab_sales:
    render_sales_tab()

with tab_about:
    render_about_tab()
