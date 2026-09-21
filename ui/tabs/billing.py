"""Contracts & Billing Dashboard tab: active contracts with color-coded expiry
warnings, this month's billing summary, a per-contract shipment timeline, and a
row-click drill-down that reuses the same 3-layer answer card as the chat tab.
"""
import pandas as pd
import plotly.express as px
import streamlit as st

from agent import config, db
from ui.agent_runner import render_error_card, run_question
from ui.answer_card import render_answer_card
from ui.theme import CONFIDENCE_COLORS

_EXPIRY_RED_DAYS = 30
_EXPIRY_YELLOW_DAYS = 90


def _expiry_badge(days: int) -> str:
    if days < _EXPIRY_RED_DAYS:
        return "🔴 " + str(days)
    if days < _EXPIRY_YELLOW_DAYS:
        return "🟡 " + str(days)
    return "🟢 " + str(days)


@st.cache_data(ttl=60, show_spinner=False)
def _fetch_contracts() -> pd.DataFrame:
    rows = db.run_sql(
        """
        SELECT contract_id, supplier_id, start_date, end_date, contract_value, payment_terms,
               renewal_status, penalty_clause, (end_date - %s) AS days_until_expiry
        FROM contracts
        WHERE renewal_status != 'expired'
        ORDER BY end_date ASC
        """,
        (config.DEMO_REFERENCE_DATE,),
    )
    return pd.DataFrame(rows)


@st.cache_data(ttl=60, show_spinner=False)
def _fetch_billing_summary() -> dict:
    rows = db.run_sql(
        """
        SELECT COALESCE(SUM(amount_due), 0) AS total_due,
               COALESCE(SUM(amount_paid), 0) AS total_paid,
               COALESCE(SUM(amount_due - amount_paid) FILTER (WHERE status = 'overdue'), 0) AS total_overdue
        FROM monthly_billing
        WHERE billing_month = DATE_TRUNC('month', %s)
        """,
        (config.DEMO_REFERENCE_DATE,),
    )
    return rows[0] if rows else {"total_due": 0, "total_paid": 0, "total_overdue": 0}


@st.cache_data(ttl=60, show_spinner=False)
def _fetch_shipment_timeline() -> pd.DataFrame:
    rows = db.run_sql(
        """
        SELECT s.contract_id, s.shipment_id, s.ship_date,
               COALESCE(s.received_date, %s) AS effective_end, s.status
        FROM shipments s
        JOIN contracts c ON s.contract_id = c.contract_id
        WHERE c.renewal_status != 'expired'
        ORDER BY s.contract_id, s.ship_date
        """,
        (config.DEMO_REFERENCE_DATE,),
    )
    return pd.DataFrame(rows)


def _render_metrics(summary: dict) -> None:
    col1, col2, col3 = st.columns(3)
    col1.metric("Total due this month", f"${float(summary['total_due']):,.2f}")
    col2.metric("Total paid this month", f"${float(summary['total_paid']):,.2f}")
    col3.metric("Total overdue this month", f"${float(summary['total_overdue']):,.2f}")


def _render_contracts_table(contracts: pd.DataFrame) -> str | None:
    st.markdown("**Active contracts** — 🔴 expires in <30 days · 🟡 <90 days · 🟢 further out")
    display_df = contracts.copy()
    display_df["expiry"] = display_df["days_until_expiry"].apply(_expiry_badge)
    display_df["contract_value"] = display_df["contract_value"].apply(lambda v: f"${float(v):,.2f}")
    display_df = display_df[
        ["contract_id", "supplier_id", "expiry", "end_date", "contract_value", "payment_terms", "penalty_clause"]
    ].rename(columns={
        "contract_id": "Contract", "supplier_id": "Supplier", "expiry": "Days until expiry",
        "end_date": "End date", "contract_value": "Value", "payment_terms": "Terms", "penalty_clause": "Penalty clause",
    })

    event = st.dataframe(
        display_df, width="stretch", hide_index=True,
        on_select="rerun", selection_mode="single-row", key="contracts_table",
    )
    selected_rows = event.selection.rows if event and event.selection else []
    if selected_rows:
        return contracts.iloc[selected_rows[0]]["contract_id"]
    return None


def _render_gantt(timeline: pd.DataFrame) -> None:
    st.markdown("**Shipment timeline by contract**")
    if timeline.empty:
        st.markdown(
            '<div class="scdt-empty-state">No shipment history for these contracts yet.</div>',
            unsafe_allow_html=True,
        )
        return
    fig = px.timeline(
        timeline, x_start="ship_date", x_end="effective_end", y="contract_id", color="status",
        hover_name="shipment_id",
        color_discrete_map={"delivered": CONFIDENCE_COLORS["high"], "delayed": CONFIDENCE_COLORS["low"],
                             "in_transit": CONFIDENCE_COLORS["estimated"]},
    )
    fig.update_yaxes(autorange="reversed", title="")
    fig.update_layout(height=420, margin=dict(t=20, b=10, l=10, r=10), plot_bgcolor="white")
    st.plotly_chart(fig, width="stretch")


def render_billing_tab() -> None:
    st.markdown("### Contracts & Billing Dashboard")
    st.caption("Click a contract row for its full detail card - same format as the Ask a Question tab.")

    try:
        contracts = _fetch_contracts()
        summary = _fetch_billing_summary()
        timeline = _fetch_shipment_timeline()
    except Exception as exc:  # noqa: BLE001 - a broken DB connection shouldn't blank the whole tab
        st.markdown(
            '<div class="scdt-empty-state">🔴 Couldn\'t load billing data right now - '
            "the database may be unreachable.</div>",
            unsafe_allow_html=True,
        )
        with st.expander("Technical details"):
            st.code(str(exc))
        return

    _render_metrics(summary)
    st.markdown("<br>", unsafe_allow_html=True)

    if contracts.empty:
        st.markdown('<div class="scdt-empty-state">No active contracts on file.</div>', unsafe_allow_html=True)
        return

    selected_contract = _render_contracts_table(contracts)
    st.markdown("<br>", unsafe_allow_html=True)
    _render_gantt(timeline)

    if selected_contract and st.session_state.get("billing_selected_contract") != selected_contract:
        st.session_state["billing_selected_contract"] = selected_contract
        question = (
            f"Show the contract details, billing status, and shipment history for contract {selected_contract}."
        )
        result = run_question(question)
        st.session_state["billing_drilldown"] = {"question": question, **result}
        if "state" in result:
            st.session_state["last_reasoning_log"] = result["state"].get("reasoning_log")

    drilldown = st.session_state.get("billing_drilldown")
    if drilldown:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(f"#### Contract detail: {st.session_state.get('billing_selected_contract')}")
        if "error" in drilldown:
            render_error_card(drilldown["question"], drilldown["error"])
        else:
            render_answer_card(drilldown["state"])
