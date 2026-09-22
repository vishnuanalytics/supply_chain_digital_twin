"""Sales Dashboard tab: the outbound mirror of Contracts & Billing - revenue and unit
volume for what dealers/distributors buy from us and resell to end customers, where
we're selling by region, and a row-click drill-down reusing the same 3-layer answer
card as the chat tab.

Postgres has no dealer/product name or region columns (see agent/prompts.py's
SQL_SYSTEM note), and Dealer -[:SERVICES]-> Region only exists in Neo4j - so this tab's
own fetch functions cross both stores directly (not through the LLM agent) and join by
dealer_id in Python, the same cross-database-by-ID pattern the rest of the app uses.
"""
import pandas as pd
import plotly.express as px
import streamlit as st

from agent import config, db
from ui.agent_runner import render_error_card, run_question
from ui.answer_card import render_answer_card
from ui.theme import ACCENT


@st.cache_data(ttl=60, show_spinner=False)
def _fetch_dealer_directory() -> pd.DataFrame:
    rows = db.run_cypher(
        "MATCH (d:Dealer)-[:SERVICES]->(r:Region) "
        "RETURN d.id AS dealer_id, d.name AS dealer_name, d.buyer_type AS buyer_type, r.name AS region_name"
    )
    return pd.DataFrame(rows)


@st.cache_data(ttl=60, show_spinner=False)
def _fetch_revenue_summary() -> dict:
    rows = db.run_sql(
        """
        SELECT COALESCE(SUM(revenue), 0) AS total_revenue,
               COALESCE(SUM(revenue) FILTER (WHERE payment_status != 'paid'), 0) AS outstanding
        FROM sales_records
        WHERE sale_date >= %s - INTERVAL '30 days'
        """,
        (config.DEMO_REFERENCE_DATE,),
    )
    summary = rows[0] if rows else {"total_revenue": 0, "outstanding": 0}

    units = db.run_sql(
        """
        SELECT COALESCE(SUM(o.quantity), 0) AS total_units
        FROM sales_records s JOIN dealer_orders o ON s.order_id = o.order_id
        WHERE s.sale_date >= %s - INTERVAL '30 days'
        """,
        (config.DEMO_REFERENCE_DATE,),
    )
    summary["total_units"] = units[0]["total_units"] if units else 0
    return summary


@st.cache_data(ttl=60, show_spinner=False)
def _fetch_monthly_revenue() -> pd.DataFrame:
    rows = db.run_sql(
        """
        SELECT DATE_TRUNC('month', sale_date) AS month, SUM(revenue) AS revenue
        FROM sales_records
        WHERE sale_date >= %s - INTERVAL '6 months'
        GROUP BY 1
        ORDER BY 1
        """,
        (config.DEMO_REFERENCE_DATE,),
    )
    return pd.DataFrame(rows)


@st.cache_data(ttl=60, show_spinner=False)
def _fetch_recent_sales() -> pd.DataFrame:
    rows = db.run_sql(
        """
        SELECT s.sale_id, o.dealer_id, o.product_id, o.quantity, s.unit_price,
               s.revenue, s.sale_date, s.channel, s.payment_status
        FROM sales_records s JOIN dealer_orders o ON s.order_id = o.order_id
        WHERE s.sale_date >= %s - INTERVAL '90 days'
        ORDER BY s.sale_date DESC
        """,
        (config.DEMO_REFERENCE_DATE,),
    )
    return pd.DataFrame(rows)


def _render_metrics(summary: dict) -> None:
    col1, col2, col3 = st.columns(3)
    col1.metric("Revenue (last 30 days)", f"${float(summary['total_revenue']):,.2f}")
    col2.metric("Units sold (last 30 days)", f"{float(summary['total_units']):,.0f}")
    col3.metric("Outstanding (unpaid + overdue)", f"${float(summary['outstanding']):,.2f}")


def _render_revenue_trend(monthly: pd.DataFrame) -> None:
    st.markdown("**Revenue trend (last 6 months)**")
    if monthly.empty:
        st.markdown('<div class="scdt-empty-state">No sales in this window.</div>', unsafe_allow_html=True)
        return
    fig = px.bar(monthly, x="month", y="revenue", color_discrete_sequence=[ACCENT])
    fig.update_layout(
        height=320, margin=dict(t=20, b=10, l=10, r=10), plot_bgcolor="white",
        yaxis_title="Revenue (USD)", xaxis_title="",
    )
    st.plotly_chart(fig, width="stretch")


def _render_revenue_by_region(sales: pd.DataFrame, directory: pd.DataFrame) -> None:
    st.markdown("**Where we're selling — revenue by region**")
    if sales.empty or directory.empty:
        st.markdown('<div class="scdt-empty-state">No sales in this window.</div>', unsafe_allow_html=True)
        return
    merged = sales.merge(directory, on="dealer_id", how="left")
    by_region = merged.groupby("region_name", as_index=False)["revenue"].sum().sort_values("revenue", ascending=False)
    fig = px.bar(by_region, x="region_name", y="revenue", color_discrete_sequence=[ACCENT])
    fig.update_layout(
        height=320, margin=dict(t=20, b=10, l=10, r=10), plot_bgcolor="white",
        yaxis_title="Revenue (USD)", xaxis_title="",
    )
    st.plotly_chart(fig, width="stretch")


def _render_sales_table(sales: pd.DataFrame, directory: pd.DataFrame) -> tuple[str | None, str | None]:
    st.markdown("**Recent sales** (last 90 days) — click a row for full detail")
    merged = sales.merge(directory, on="dealer_id", how="left")
    display_df = merged.copy()
    display_df["unit_price"] = display_df["unit_price"].apply(lambda v: f"${float(v):,.2f}")
    display_df["revenue"] = display_df["revenue"].apply(lambda v: f"${float(v):,.2f}")
    display_df["payment_status"] = display_df["payment_status"].map({
        "paid": "🟢 paid", "pending": "🟡 pending", "overdue": "🔴 overdue",
    }).fillna(display_df["payment_status"])
    display_df = display_df[
        ["sale_date", "dealer_id", "buyer_type", "region_name", "product_id",
         "quantity", "unit_price", "revenue", "channel", "payment_status"]
    ].rename(columns={
        "sale_date": "Date", "dealer_id": "Dealer/Distributor", "buyer_type": "Type",
        "region_name": "Region", "product_id": "Product", "quantity": "Qty",
        "unit_price": "Unit price", "revenue": "Revenue", "channel": "Channel",
        "payment_status": "Payment",
    })

    event = st.dataframe(
        display_df, width="stretch", hide_index=True,
        on_select="rerun", selection_mode="single-row", key="sales_table",
    )
    selected_rows = event.selection.rows if event and event.selection else []
    if selected_rows:
        row = merged.iloc[selected_rows[0]]
        return row["sale_id"], row["dealer_id"]
    return None, None


def render_sales_tab() -> None:
    st.markdown("### Sales Dashboard")
    st.caption(
        "Revenue, units, and where we're selling - the outbound mirror of Contracts & "
        "Billing. Click a sale row for its full detail card, same format as the Ask a Question tab."
    )

    try:
        directory = _fetch_dealer_directory()
        summary = _fetch_revenue_summary()
        monthly = _fetch_monthly_revenue()
        sales = _fetch_recent_sales()
    except Exception as exc:  # noqa: BLE001 - a broken DB connection shouldn't blank the whole tab
        st.markdown(
            '<div class="scdt-empty-state">🔴 Couldn\'t load sales data right now - '
            "the database may be unreachable.</div>",
            unsafe_allow_html=True,
        )
        with st.expander("Technical details"):
            st.code(str(exc))
        return

    _render_metrics(summary)
    st.markdown("<br>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        _render_revenue_trend(monthly)
    with col2:
        _render_revenue_by_region(sales, directory)

    st.markdown("<br>", unsafe_allow_html=True)

    if sales.empty:
        st.markdown('<div class="scdt-empty-state">No sales on file in this window.</div>', unsafe_allow_html=True)
        return

    selected_sale, selected_dealer = _render_sales_table(sales, directory)

    if selected_sale and st.session_state.get("sales_selected_sale") != selected_sale:
        st.session_state["sales_selected_sale"] = selected_sale
        question = (
            f"Show the full sales history, revenue, and region for dealer/distributor {selected_dealer}."
        )
        result = run_question(question)
        st.session_state["sales_drilldown"] = {"question": question, **result}
        if "state" in result:
            st.session_state["last_reasoning_log"] = result["state"].get("reasoning_log")

    drilldown = st.session_state.get("sales_drilldown")
    if drilldown:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(f"#### Sale detail: {st.session_state.get('sales_selected_sale')}")
        if "error" in drilldown:
            render_error_card(drilldown["question"], drilldown["error"])
        elif "interrupt" in drilldown:
            st.caption("⚠️ This lookup unexpectedly needs approval - use the Ask a Question tab to resolve it.")
        else:
            render_answer_card(drilldown["state"], card_key="sales_drilldown")
