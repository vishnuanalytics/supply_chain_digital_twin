"""Contracts & Billing Dashboard tab: active contracts with color-coded expiry
warnings, this month's billing summary, a per-contract shipment timeline, and two
complementary drill-downs - clicking a CONTRACT row asks the LLM agent a natural-
language question (the existing 3-layer answer card), while clicking a TIMELINE point
instantly opens a structured detail dialog (shipment + contract + supplier performance
+ invoice, all pure SQL, no LLM round-trip) with a computed recommended next action.
"""
from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from agent import config, db
from ui.agent_runner import render_error_card, run_question
from ui.answer_card import render_answer_card
from ui.theme import ACCENT, CONFIDENCE_COLORS

_EXPIRY_RED_DAYS = 30
_EXPIRY_YELLOW_DAYS = 90

_STATUS_COLORS = {
    "delivered": CONFIDENCE_COLORS["high"], "delayed": CONFIDENCE_COLORS["low"],
    "in_transit": CONFIDENCE_COLORS["estimated"],
}
_STATUS_LABELS = {"delivered": "Delivered", "delayed": "Delayed", "in_transit": "In transit"}


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
    # material_id/price_per_unit come from purchase_orders (shipments has no material
    # column of its own - see shipments.po_id), and carrier/freight_mode/tracking_number/
    # delay_reason are the logistics fields added directly to shipments so "what's
    # actually happening with this shipment" is answerable without an LLM call.
    rows = db.run_sql(
        """
        SELECT s.contract_id, s.shipment_id, s.ship_date,
               COALESCE(s.received_date, %s) AS effective_end, s.status,
               s.carrier, s.freight_mode, s.tracking_number, s.delay_reason, s.quantity,
               c.supplier_id, po.material_id
        FROM shipments s
        JOIN contracts c ON s.contract_id = c.contract_id
        LEFT JOIN purchase_orders po ON s.po_id = po.po_id
        WHERE c.renewal_status != 'expired'
        ORDER BY s.contract_id, s.ship_date
        """,
        (config.DEMO_REFERENCE_DATE,),
    )
    return pd.DataFrame(rows)


@st.cache_data(ttl=60, show_spinner=False)
def _fetch_shipment_detail(shipment_id: str) -> dict | None:
    """Everything a user needs to decide what to do about one shipment, in a single
    round trip: the shipment itself, its contract and account manager, the supplier's
    track record, the material/price it's carrying, and its related invoice's payment
    status - deliberately NOT routed through the LLM agent, so this dialog opens
    instantly regardless of LLM provider quota."""
    rows = db.run_sql(
        """
        SELECT s.shipment_id, s.contract_id, s.po_id, s.ship_date, s.received_date,
               s.quantity, s.status, s.carrier, s.freight_mode, s.tracking_number, s.delay_reason,
               c.supplier_id, c.contract_value, c.payment_terms, c.renewal_status,
               c.penalty_clause, c.penalty_terms, c.account_manager, c.auto_renew,
               c.end_date AS contract_end_date,
               po.material_id, po.price_per_unit, po.unit_of_measure,
               sp.on_time_rate, sp.avg_delay_days,
               i.status AS invoice_status, i.amount AS invoice_amount, i.due_date AS invoice_due_date
        FROM shipments s
        JOIN contracts c ON s.contract_id = c.contract_id
        LEFT JOIN purchase_orders po ON s.po_id = po.po_id
        LEFT JOIN supplier_performance sp ON c.supplier_id = sp.supplier_id
        LEFT JOIN invoices i ON i.shipment_id = s.shipment_id
        WHERE s.shipment_id = %s
        """,
        (shipment_id,),
    )
    return rows[0] if rows else None


def _recommended_action(detail: dict, today: date) -> tuple[str, str]:
    """A computed (not LLM-generated) next-step recommendation, so a user gets an
    instant, deterministic answer to "does this need my attention, and what do I do
    about it" the moment the dialog opens. Checked roughly in order of real urgency:
    an active penalty beats a plain delay, an overdue payment beats a distant renewal."""
    if detail["status"] == "delayed" and detail["penalty_clause"]:
        return "🔴", (
            f"Penalty clause applies to this delay - confirm the penalty adjustment "
            f"with {detail['account_manager']} before the next invoice goes out."
        )
    if detail["status"] == "delayed":
        return "🟡", (
            f"Delayed ({detail['delay_reason']}) - confirm the new ETA with "
            f"{detail['carrier']}."
        )
    if detail.get("invoice_status") == "overdue":
        amount = float(detail["invoice_amount"]) if detail.get("invoice_amount") is not None else 0.0
        return "🔴", f"The related invoice is overdue (${amount:,.2f}) - follow up on payment."

    days_to_expiry = (detail["contract_end_date"] - today).days
    if not detail["auto_renew"] and days_to_expiry <= _EXPIRY_RED_DAYS:
        return "🔴", (
            f"Contract expires in {days_to_expiry} day(s) and does not auto-renew - "
            f"confirm renewal with {detail['account_manager']} now."
        )
    if not detail["auto_renew"] and days_to_expiry <= _EXPIRY_YELLOW_DAYS:
        return "🟡", (
            f"Contract expires in {days_to_expiry} day(s) and does not auto-renew - "
            f"plan the renewal decision with {detail['account_manager']}."
        )
    return "🟢", "On track - no action needed right now."


@st.dialog("Shipment detail", width="large")
def _render_shipment_dialog(shipment_id: str) -> None:
    try:
        detail = _fetch_shipment_detail(shipment_id)
    except Exception as exc:  # noqa: BLE001 - a broken DB connection shouldn't crash the dialog
        st.markdown(
            '<div class="scdt-empty-state">🔴 Couldn\'t load shipment detail right now.</div>',
            unsafe_allow_html=True,
        )
        with st.expander("Technical details"):
            st.code(str(exc))
        return
    if not detail:
        st.caption("No detail found for this shipment.")
        return

    icon, action = _recommended_action(detail, config.DEMO_REFERENCE_DATE)
    st.markdown(f"#### {icon} {action}")
    st.markdown("<br>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Shipment**")
        qty = float(detail["quantity"])
        uom = detail["unit_of_measure"] or ""
        st.write(f"Material: `{detail['material_id'] or '—'}`")
        st.write(f"Quantity: {qty:,.2f} {uom}")
        st.write(f"Ship date: {detail['ship_date']}")
        st.write(f"Received: {detail['received_date'] or 'Not yet received'}")
        st.write(f"Status: {_STATUS_LABELS.get(detail['status'], detail['status'])}")
        st.write(f"Carrier: {detail['carrier']} ({detail['freight_mode']})")
        st.write(f"Tracking #: `{detail['tracking_number']}`")
        if detail["delay_reason"]:
            st.write(f"Delay reason: {detail['delay_reason']}")

    with col2:
        st.markdown("**Contract & supplier**")
        st.write(f"Contract `{detail['contract_id']}` · Supplier `{detail['supplier_id']}`")
        st.write(f"Value: ${float(detail['contract_value']):,.2f} · {detail['payment_terms']}")
        st.write(f"Account manager: {detail['account_manager']}")
        st.write(f"Auto-renews: {'Yes' if detail['auto_renew'] else 'No'}")
        st.write(f"Penalty clause: {'Yes' if detail['penalty_clause'] else 'No'}")
        if detail["penalty_terms"]:
            st.caption(detail["penalty_terms"])
        if detail["on_time_rate"] is not None:
            st.write(f"Supplier on-time rate: {float(detail['on_time_rate']):.1f}% "
                      f"(avg delay {float(detail['avg_delay_days']):.1f}d)")
        if detail.get("invoice_status"):
            st.write(
                f"Related invoice: {detail['invoice_status']} — "
                f"${float(detail['invoice_amount']):,.2f} due {detail['invoice_due_date']}"
            )


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


def _render_gantt(timeline: pd.DataFrame) -> str | None:
    st.markdown("**Shipment timeline by contract** — click any bar for its full detail")
    if timeline.empty:
        st.markdown(
            '<div class="scdt-empty-state">No shipment history for these contracts yet.</div>',
            unsafe_allow_html=True,
        )
        return None

    display = timeline.copy()
    # "C1 (S1)" instead of a bare contract_id - Postgres has no supplier NAME column,
    # but even the ID gives real context at a glance that a bare "C1" row label didn't.
    display["contract_label"] = display["contract_id"] + " (" + display["supplier_id"] + ")"
    display["status_label"] = display["status"].map(_STATUS_LABELS).fillna(display["status"])

    fig = px.timeline(
        display, x_start="ship_date", x_end="effective_end", y="contract_label", color="status_label",
        custom_data=["shipment_id"],
        hover_data={
            "shipment_id": True, "material_id": True, "quantity": ":,.0f", "carrier": True,
            "tracking_number": True, "delay_reason": True,
            "contract_label": False, "status_label": False,
        },
        color_discrete_map={
            _STATUS_LABELS["delivered"]: _STATUS_COLORS["delivered"],
            _STATUS_LABELS["delayed"]: _STATUS_COLORS["delayed"],
            _STATUS_LABELS["in_transit"]: _STATUS_COLORS["in_transit"],
        },
    )
    fig.update_yaxes(autorange="reversed", title="")
    fig.update_traces(marker_line_width=0, opacity=0.92)
    # A "today" reference line makes it immediately obvious which bars are history vs.
    # still in flight, without having to cross-reference the sidebar's demo-date caption.
    # add_vline's internal annotation-positioning math chokes on a raw datetime.date on
    # a date-typed x-axis (TypeError: unsupported operand type(s) for +: 'int' and
    # 'datetime.date') - found live, not assumed; an ISO string works correctly.
    fig.add_vline(
        x=config.DEMO_REFERENCE_DATE.isoformat(), line_width=2, line_dash="dot", line_color=ACCENT,
        annotation_text="Today", annotation_position="top",
    )
    fig.update_layout(
        height=max(320, 60 * display["contract_label"].nunique() + 100),
        margin=dict(t=30, b=10, l=10, r=10), plot_bgcolor="white",
        legend_title_text="", bargap=0.35,
    )

    event = st.plotly_chart(
        fig, width="stretch", on_select="rerun", selection_mode="points", key="shipment_gantt",
    )
    if event and event.selection and event.selection.points:
        custom = event.selection.points[0].get("customdata")
        if custom:
            return custom[0]
    return None


def render_billing_tab() -> None:
    st.markdown("### Contracts & Billing Dashboard")
    st.caption(
        "Click a contract row for its full detail card (asks the AI). Click a "
        "timeline bar for an instant shipment detail panel - no AI round-trip needed."
    )

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
    selected_shipment = _render_gantt(timeline)

    if selected_shipment and st.session_state.get("billing_selected_shipment") != selected_shipment:
        st.session_state["billing_selected_shipment"] = selected_shipment
        _render_shipment_dialog(selected_shipment)

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
        elif "interrupt" in drilldown:
            # Contract-detail questions never trigger human_approval_gate in practice (that's
            # only reachable via a disruption simulation), but degrade gracefully instead of
            # crashing on a missing "state" key if that ever changes.
            st.caption("⚠️ This lookup unexpectedly needs approval - use the Ask a Question tab to resolve it.")
        else:
            render_answer_card(drilldown["state"])
