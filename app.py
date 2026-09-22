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
from ui.tabs.architecture import render_architecture_tab
from ui.tabs.ask import render_ask_tab
from ui.tabs.billing import render_billing_tab
from ui.tabs.graph_explorer import render_graph_explorer_tab
from ui.tabs.sales import render_sales_tab
from ui.theme import inject_css

st.set_page_config(page_title="Supply Chain Digital Twin", page_icon="🔗", layout="wide")
inject_css()

# Real per-tab URLs (e.g. /graph-explorer, /sales) instead of one flat URL with no
# sub-paths - replaces the previous st.tabs() layout. position="top" keeps the same
# horizontal-bar-of-icons-and-labels look tabs had, just now backed by actual routing
# (bookmarkable, shareable, browser back/forward all work). Query params survive within
# a page but are dropped by Streamlit's own nav on every page switch - render_sidebar()
# below re-asserts the ?session=... deep-link param on every single page (it always
# runs, regardless of which page is active), so it reads as "persists across tabs" even
# though it's technically cleared-then-immediately-restored on each switch.
#
# Known platform quirk, not a bug in this app: the *default* page's own declared
# url_path ("ask") shows a harmless "Page not found, running the app's main page" toast
# if visited directly - only "/" (not "/ask") is that page's real canonical URL.
# Confirmed live: content still renders correctly either way, and every OTHER page's
# url_path works with zero issue. Documented in docs/development_log.md.
pg = st.navigation(
    [
        st.Page(render_ask_tab, title="Ask a Question", icon="💬", url_path="ask", default=True),
        st.Page(render_graph_explorer_tab, title="Graph Explorer", icon="🕸️", url_path="graph-explorer"),
        st.Page(render_billing_tab, title="Contracts & Billing", icon="📄", url_path="billing"),
        st.Page(render_sales_tab, title="Sales", icon="📈", url_path="sales"),
        st.Page(render_architecture_tab, title="Architecture", icon="ℹ️", url_path="architecture"),
    ],
    position="top",
)
render_sidebar()
pg.run()
