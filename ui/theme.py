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
MUTED_EDGE_COLOR = "#E2E8F0"


def inject_css() -> None:
    st.markdown(
        f"""
        <style>
        .stApp {{ background-color: {NEUTRAL_100}; }}
        h1, h2, h3 {{ color: {NEUTRAL_900}; }}
        .scdt-badge {{
            display: inline-block; padding: 2px 10px; border-radius: 999px;
            font-size: 0.8rem; font-weight: 600; margin-left: 8px;
        }}
        .scdt-card {{
            background: {NEUTRAL_0}; border: 1px solid {NEUTRAL_200}; border-radius: 12px;
            padding: 1.25rem 1.5rem; margin-bottom: 1rem;
        }}
        .scdt-answer-text {{ font-size: 1.05rem; line-height: 1.55; color: {NEUTRAL_900}; }}
        .scdt-empty-state {{
            text-align: center; padding: 2.5rem 1rem; color: {NEUTRAL_600};
            border: 1px dashed {NEUTRAL_400}; border-radius: 12px; background: {NEUTRAL_0};
        }}
        section[data-testid="stSidebar"] {{ background-color: {NEUTRAL_900}; }}
        section[data-testid="stSidebar"] * {{ color: {NEUTRAL_100} !important; }}
        div[data-testid="stButton"] button {{
            border-radius: 8px; border: 1px solid {NEUTRAL_200};
        }}
        div[data-testid="stButton"] button:hover {{
            border-color: {ACCENT}; color: {ACCENT};
        }}
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
