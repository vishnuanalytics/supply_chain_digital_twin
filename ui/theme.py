"""Shared visual palette + CSS injection. One accent color, neutral grays — no default
Streamlit theme, per the spec's visual polish requirements."""
import streamlit as st

ACCENT = "#4F6EF7"
ACCENT_DARK = "#3B54D6"
ACCENT_LIGHT = "#E8ECFE"

NEUTRAL_900 = "#0F172A"
NEUTRAL_600 = "#475569"
NEUTRAL_400 = "#94A3B8"
NEUTRAL_200 = "#E2E8F0"
NEUTRAL_100 = "#F1F5F9"
NEUTRAL_0 = "#FFFFFF"

CONFIDENCE_COLORS = {"high": "#22C55E", "estimated": "#F59E0B", "low": "#EF4444"}
CONFIDENCE_ICONS = {"high": "🟢", "estimated": "🟡", "low": "🔴"}

# Node colors by Neo4j label, used consistently across Graph Explorer and per-answer traces
LABEL_COLORS = {
    "Facility": "#0EA5E9",
    "Warehouse": ACCENT,
    "Region": NEUTRAL_400,
    "Dealer": "#EC4899",
    "Product": "#22C55E",
    "IntermediatePart": "#F59E0B",
    "RawMaterial": "#EF4444",
    "Supplier": "#8B5CF6",
    "ThirdPartyVendor": "#14B8A6",
    "Contract": "#F97316",
}

MUTED_NODE_COLOR = "#CBD5E1"
# Deliberately very pale - only meant for the *de-emphasized* edges/nodes behind a
# vividly-colored highlighted path (ui/answer_card.py's graph trace). Using this as a
# graph's only/default edge color (as the Graph Explorer briefly did) makes edges nearly
# invisible against a white canvas - see EDGE_COLOR below for that case.
MUTED_EDGE_COLOR = "#E2E8F0"
EDGE_COLOR = "#94A3B8"


def inject_css() -> None:
    st.markdown(
        f"""
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
        <style>
        html, body, [class*="css"], .stApp, button, input, textarea {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        }}
        .stApp {{ background-color: {NEUTRAL_100}; }}
        h1, h2, h3 {{ color: {NEUTRAL_900}; font-weight: 700; letter-spacing: -0.01em; }}
        p, .stMarkdown, .stCaption {{ color: {NEUTRAL_600}; }}
        .scdt-badge {{
            display: inline-block; padding: 3px 12px; border-radius: 999px;
            font-size: 0.78rem; font-weight: 700; letter-spacing: 0.02em; margin-left: 8px;
            vertical-align: middle;
        }}
        .scdt-card {{
            background: {NEUTRAL_0}; border: 1px solid {NEUTRAL_200}; border-radius: 14px;
            padding: 1.4rem 1.6rem; margin-bottom: 1.1rem;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04), 0 4px 12px rgba(15, 23, 42, 0.05);
            transition: box-shadow 0.15s ease;
        }}
        .scdt-card:hover {{
            box-shadow: 0 2px 4px rgba(15, 23, 42, 0.05), 0 8px 20px rgba(15, 23, 42, 0.07);
        }}
        .scdt-answer-text {{ font-size: 1.06rem; line-height: 1.6; color: {NEUTRAL_900}; }}
        .scdt-empty-state {{
            text-align: center; padding: 2.75rem 1.5rem; color: {NEUTRAL_600};
            border: 1.5px dashed {NEUTRAL_400}; border-radius: 14px;
            background: linear-gradient(180deg, {NEUTRAL_0} 0%, {NEUTRAL_100} 100%);
        }}
        /* Sidebar */
        section[data-testid="stSidebar"] {{
            background: linear-gradient(180deg, {NEUTRAL_900} 0%, #131c33 100%);
        }}
        section[data-testid="stSidebar"] * {{ color: {NEUTRAL_100} !important; }}
        section[data-testid="stSidebar"] hr {{ border-color: rgba(255,255,255,0.12); margin: 1.1rem 0; }}
        section[data-testid="stSidebar"] [data-testid="stMetricValue"] {{
            font-size: 1.6rem; font-weight: 700; color: #FFFFFF !important;
        }}
        section[data-testid="stSidebar"] [data-testid="stMetricLabel"] {{
            color: {NEUTRAL_400} !important; text-transform: uppercase;
            font-size: 0.72rem; letter-spacing: 0.06em;
        }}
        section[data-testid="stSidebar"] h3 {{
            font-size: 0.82rem; text-transform: uppercase; letter-spacing: 0.06em;
            color: {NEUTRAL_400} !important; margin-top: 1.4rem; margin-bottom: 0.5rem;
        }}
        /* The blanket `* {{ color: NEUTRAL_100 }}` above is correct for plain text sitting
        directly on the sidebar's dark background, but buttons (New chat, past-session
        list) and the model picker's selectbox both keep their own white/light control
        background even inside the sidebar - inheriting near-white text on top of that
        made them unreadable (white-on-white). A button's visible label isn't text
        directly on <button> though - Streamlit nests it several levels deep (button >
        div > span > span > div.stMarkdownContainer > p), and the blanket rule's `*`
        matches each of those elements DIRECTLY (not just via inheritance), so styling
        only the outer <button> was not enough - the `!important` on that inner <p>
        still won. Every rule below ends in its own `*` for the same reason: to reach
        past the blanket rule's direct match, not just override inherited color. */
        section[data-testid="stSidebar"] div[data-testid="stButton"] button,
        section[data-testid="stSidebar"] div[data-testid="stButton"] button * {{
            color: {NEUTRAL_900} !important;
        }}
        section[data-testid="stSidebar"] div[data-testid="stButton"] button:hover,
        section[data-testid="stSidebar"] div[data-testid="stButton"] button:hover * {{
            color: {ACCENT} !important;
        }}
        /* The model picker selectbox: this Streamlit version renders it as a
        react-aria ComboBox (a plain <input> carrying the displayed value as its
        `value` attribute, not textContent) rather than a BaseWeb [data-baseweb="select"]
        element - inspected the real DOM directly rather than assuming the older
        structure, since guessing wrong here would silently match nothing. */
        section[data-testid="stSidebar"] div[data-testid="stSelectbox"] input {{
            color: {NEUTRAL_900} !important;
        }}
        /* Buttons - example questions, actions */
        div[data-testid="stButton"] button {{
            border-radius: 10px; border: 1px solid {NEUTRAL_200}; background: {NEUTRAL_0};
            transition: all 0.15s ease; box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);
        }}
        div[data-testid="stButton"] button:hover {{
            border-color: {ACCENT}; color: {ACCENT}; background: {ACCENT_LIGHT};
            box-shadow: 0 2px 6px rgba(79, 110, 247, 0.15); transform: translateY(-1px);
        }}
        div[data-testid="stButton"] button:active {{ transform: translateY(0); }}
        /* Pills (used for the Graph Explorer type filter) */
        div[data-testid="stPills"] button {{ border-radius: 999px !important; font-weight: 600; }}
        /* Top navigation (st.navigation(position="top"), replacing the old st.tabs() -
        real testid confirmed live, not the st.tabs()-era selectors this replaced) */
        [data-testid="stTopNavLink"] {{ font-weight: 600; font-size: 0.95rem; }}
        /* Chat input + text areas */
        [data-testid="stChatInput"] {{
            border-radius: 12px; box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
        }}
        /* Dataframes */
        [data-testid="stDataFrame"] {{ border-radius: 10px; overflow: hidden; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def confidence_badge_html(confidence: str | None) -> str:
    confidence = confidence or "low"
    color = CONFIDENCE_COLORS.get(confidence, CONFIDENCE_COLORS["low"])
    icon = CONFIDENCE_ICONS.get(confidence, "🔴")
    return (
        f'<span class="scdt-badge" style="background:{color}22; color:{color};">'
        f'{icon} {confidence.upper()}</span>'
    )
