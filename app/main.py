"""
Nidhi's Budget Tracker — Streamlit Dashboard
"""

import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from app.database import Database

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Nidhi's Budget Tracker",
    page_icon="💸",
    layout="wide",
    initial_sidebar_state="expanded",
)

CURRENCY = "₹"

DEFAULT_CATEGORIES = [
    "Food", "Education", "Skincare", "Entertainment",
    "Transport", "Shopping", "Health", "Utilities", "Rent", "Other",
]

PALETTE = px.colors.qualitative.Pastel

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
        section[data-testid="stSidebar"] { background: #1a1a2e; }
        section[data-testid="stSidebar"] * { color: #e0e0e0 !important; }
        .metric-card {
            background: linear-gradient(135deg,#667eea 0%,#764ba2 100%);
            border-radius:12px; padding:20px; color:white; text-align:center;
            box-shadow:0 4px 15px rgba(0,0,0,.15);
        }
        .metric-card h1 { font-size:2rem; margin:0; color:white; }
        .metric-card p  { margin:4px 0 0; opacity:.85; font-size:.9rem; }
        .alert-box {
            background:#fff3cd; border-left:4px solid #ffc107;
            padding:10px 15px; border-radius:6px; margin-bottom:8px;
        }
        .danger-box {
            background:#f8d7da; border-left:4px solid #dc3545;
            padding:10px 15px; border-radius:6px; margin-bottom:8px;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# ── Database singleton ─────────────────────────────────────────────────────────
@st.cache_resource
def get_db() -> Database | None:
    try:
        return Database()
    except Exception as exc:
        st.session_state["db_error"] = str(exc)
        return None


def require_db() -> Database:
    db = get_db()
    if db is None:
        err = st.session_state.get("db_error", "Unknown error")
        st.error(
            f"""
            **Cannot connect to Neo4j.**

            {err}

            **Quick fix — start everything with Docker:**
            ```
            docker-compose up --build
            ```
            Then visit **http://localhost:8501**

            **Or start only Neo4j locally:**
            ```
            docker-compose up -d neo4j
            python run.py
            ```
            """
        )
        st.stop()
    return db


# ── Helpers ────────────────────────────────────────────────────────────────────
def fmt(amount: float) -> str:
    return f"{CURRENCY}{amount:,.2f}"


def prev_month(year: int, month: int) -> tuple[int, int]:
    if month == 1:
        return year - 1, 12
    return year, month - 1


def change_badge(pct: float | None) -> str:
    if pct is None:
        return "🆕 New"
    if pct > 0:
        return f"🔺 +{pct:.1f}%"
    if pct < 0:
        return f"🟢 {pct:.1f}%"
    return "➡ 0%"


# ── Sidebar navigation ─────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 💸 Budget Tracker")
    st.markdown("---")
    page = st.radio(
        "Go to",
        ["Dashboard", "Add Expense", "Set Budget", "Analytics", "History", "Compare Months"],
        label_visibility="collapsed",
    )
    st.markdown("---")
    now = datetime.now()
    sel_year = st.selectbox("Year", list(range(now.year, now.year - 5, -1)), index=0)
    sel_month = st.selectbox(
        "Month",
        list(range(1, 13)),
        index=now.month - 1,
        format_func=lambda m: datetime(2000, m, 1).strftime("%B"),
    )
    st.markdown("---")
    st.caption("Neo4j graph powers this app.")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
def show_dashboard():
    db = require_db()
    month_label = datetime(sel_year, sel_month, 1).strftime("%B %Y")
    st.title(f"📊 Dashboard — {month_label}")

    svb = db.get_spending_vs_budget(sel_year, sel_month)
    summary = db.get_monthly_summary(sel_year, sel_month)

    total_spent = sum(r["spent"] for r in svb)
    total_budget = sum(r["budget"] for r in svb if r["budget"] > 0)
    over_budget_cats = [r for r in svb if r["budget"] > 0 and r["spent"] > r["budget"]]
    pct_overall = (total_spent / total_budget * 100) if total_budget > 0 else 0

    # ── Key metrics ──────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(
            f'<div class="metric-card"><h1>{fmt(total_spent)}</h1><p>Total Spent</p></div>',
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f'<div class="metric-card"><h1>{fmt(total_budget)}</h1><p>Total Budget</p></div>',
            unsafe_allow_html=True,
        )
    with c3:
        remaining = total_budget - total_spent
        color = "#e74c3c" if remaining < 0 else "#2ecc71"
        st.markdown(
            f'<div class="metric-card" style="background:linear-gradient(135deg,{color},#2c3e50)">'
            f"<h1>{fmt(remaining)}</h1><p>Remaining</p></div>",
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            f'<div class="metric-card" style="background:linear-gradient(135deg,#f39c12,#e74c3c)">'
            f"<h1>{len(over_budget_cats)}</h1><p>Over Budget</p></div>",
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Over-budget alerts ───────────────────────────────────────────────────
    if over_budget_cats:
        st.subheader("⚠️ Over-Budget Categories")
        for r in over_budget_cats:
            excess = r["spent"] - r["budget"]
            st.markdown(
                f'<div class="danger-box"><b>{r["category"]}</b> — '
                f'spent {fmt(r["spent"])} of {fmt(r["budget"])} budget '
                f'(<b>+{fmt(excess)} over</b>)</div>',
                unsafe_allow_html=True,
            )

    # ── Charts row ───────────────────────────────────────────────────────────
    if summary:
        col_left, col_right = st.columns([1, 1])

        with col_left:
            st.subheader("Spending Breakdown")
            df_pie = pd.DataFrame(summary)
            fig_pie = px.pie(
                df_pie,
                names="category",
                values="total",
                hole=0.45,
                color_discrete_sequence=PALETTE,
            )
            fig_pie.update_traces(textposition="inside", textinfo="percent+label")
            fig_pie.update_layout(showlegend=False, margin=dict(t=20, b=20))
            st.plotly_chart(fig_pie, use_container_width=True)

        with col_right:
            st.subheader("Budget vs Actual")
            if svb:
                df_bva = pd.DataFrame(svb)
                df_melt = df_bva[df_bva["budget"] > 0][["category", "budget", "spent"]]
                if not df_melt.empty:
                    df_melt = df_melt.melt(
                        id_vars="category", var_name="Type", value_name="Amount"
                    )
                    fig_bar = px.bar(
                        df_melt,
                        x="Amount",
                        y="category",
                        color="Type",
                        orientation="h",
                        barmode="group",
                        color_discrete_map={"budget": "#a8d8ea", "spent": "#ff6b6b"},
                        labels={"Amount": f"Amount ({CURRENCY})", "category": ""},
                    )
                    fig_bar.update_layout(
                        legend_title="",
                        margin=dict(t=20, b=20),
                        yaxis=dict(categoryorder="total ascending"),
                    )
                    st.plotly_chart(fig_bar, use_container_width=True)
                else:
                    st.info("Set budgets to see the comparison chart.")
            else:
                st.info("No expenses recorded yet.")

    # ── Budget progress bars ─────────────────────────────────────────────────
    if svb:
        st.subheader("Category Progress")
        for r in svb:
            col_name, col_bar = st.columns([1, 3])
            with col_name:
                st.markdown(f"**{r['category']}**")
                st.caption(f"{fmt(r['spent'])}")
            with col_bar:
                if r["budget"] > 0:
                    pct = min(r["pct_used"] or 0, 100)
                    color = "normal" if pct < 80 else ("off" if pct < 100 else "inverse")
                    st.progress(int(pct), text=f"{r['pct_used'] or 0:.1f}% of {fmt(r['budget'])}")
                else:
                    st.caption("No budget set")

    # ── Daily spending sparkline ─────────────────────────────────────────────
    daily = db.get_daily_spending(sel_year, sel_month)
    if daily:
        st.subheader("Daily Spending")
        df_daily = pd.DataFrame(daily)
        df_daily_agg = df_daily.groupby("date")["total"].sum().reset_index()
        df_daily_agg = df_daily_agg.sort_values("date")
        fig_daily = px.bar(
            df_daily_agg,
            x="date",
            y="total",
            labels={"date": "Date", "total": f"Amount ({CURRENCY})"},
            color_discrete_sequence=["#667eea"],
        )
        fig_daily.update_layout(margin=dict(t=10, b=10))
        st.plotly_chart(fig_daily, use_container_width=True)

    # ── Recent expenses ──────────────────────────────────────────────────────
    expenses = db.get_expenses_for_month(sel_year, sel_month)
    if expenses:
        st.subheader("Recent Expenses")
        df_exp = pd.DataFrame(expenses[:10])
        df_exp["amount"] = df_exp["amount"].apply(fmt)
        st.dataframe(
            df_exp[["date", "category", "description", "amount"]],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No expenses recorded for this month yet.")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: ADD EXPENSE
# ══════════════════════════════════════════════════════════════════════════════
def show_add_expense():
    db = require_db()
    st.title("➕ Add Expense")

    existing_cats = db.get_categories()
    category_options = sorted(set(DEFAULT_CATEGORIES + existing_cats)) + ["✏️ Custom category"]

    with st.form("add_expense_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            amount = st.number_input(
                f"Amount ({CURRENCY})", min_value=0.01, step=1.0, format="%.2f"
            )
            category_sel = st.selectbox("Category", category_options)
            if category_sel == "✏️ Custom category":
                category = st.text_input("Custom category name")
            else:
                category = category_sel
                st.text_input("Custom category name", disabled=True, value="")
        with col2:
            description = st.text_input("Description", placeholder="e.g. Zomato order")
            expense_date = st.date_input("Date", value=date.today())

        submitted = st.form_submit_button("💾 Add Expense", use_container_width=True)

    if submitted:
        if not category or category == "✏️ Custom category":
            st.error("Please select or enter a category.")
        elif amount <= 0:
            st.error("Amount must be greater than zero.")
        else:
            db.add_expense(amount, category, description, expense_date)
            st.success(f"Added {fmt(amount)} for **{category}** on {expense_date}.")
            get_db.clear()  # refresh cached DB so stats update

    # ── Quick summary for current month ─────────────────────────────────────
    st.markdown("---")
    st.subheader(f"This Month's Expenses ({datetime(sel_year, sel_month, 1).strftime('%B %Y')})")
    expenses = db.get_expenses_for_month(sel_year, sel_month)
    if expenses:
        df = pd.DataFrame(expenses)
        df["amount"] = df["amount"].apply(fmt)
        st.dataframe(
            df[["date", "category", "description", "amount"]],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No expenses for this month yet.")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: SET BUDGET
# ══════════════════════════════════════════════════════════════════════════════
def show_set_budget():
    db = require_db()
    month_label = datetime(sel_year, sel_month, 1).strftime("%B %Y")
    st.title(f"🎯 Set Budget — {month_label}")

    existing_budgets = {r["category"]: r["budget"] for r in db.get_budget_for_month(sel_year, sel_month)}
    existing_cats = db.get_categories()
    all_cats = sorted(set(DEFAULT_CATEGORIES + existing_cats))

    st.markdown("Enter **0** to clear a budget for that category.")
    st.markdown("---")

    with st.form("set_budget_form"):
        budget_inputs: dict[str, float] = {}
        cols = st.columns(2)
        for i, cat in enumerate(all_cats):
            with cols[i % 2]:
                current = existing_budgets.get(cat, 0.0)
                budget_inputs[cat] = st.number_input(
                    f"{cat}",
                    min_value=0.0,
                    value=float(current),
                    step=100.0,
                    format="%.2f",
                    key=f"budget_{cat}",
                )

        # Custom category budget
        st.markdown("**Add budget for a new category:**")
        cc1, cc2 = st.columns(2)
        with cc1:
            custom_cat = st.text_input("Category name")
        with cc2:
            custom_amt = st.number_input(
                f"Amount ({CURRENCY})", min_value=0.0, step=100.0, key="custom_budget_amt"
            )

        saved = st.form_submit_button("💾 Save All Budgets", use_container_width=True)

    if saved:
        count = 0
        for cat, amt in budget_inputs.items():
            if amt > 0:
                db.set_budget(sel_year, sel_month, cat, amt)
                count += 1
        if custom_cat.strip() and custom_amt > 0:
            db.set_budget(sel_year, sel_month, custom_cat.strip(), custom_amt)
            count += 1
        st.success(f"Saved budgets for {count} categories.")

    # ── Current budget summary ───────────────────────────────────────────────
    budgets = db.get_spending_vs_budget(sel_year, sel_month)
    if any(r["budget"] > 0 for r in budgets):
        st.markdown("---")
        st.subheader("Current Budget Allocation")
        df = pd.DataFrame([r for r in budgets if r["budget"] > 0])
        df["budget"] = df["budget"].apply(fmt)
        df["spent"] = df["spent"].apply(fmt)
        df["remaining"] = df["remaining"].apply(fmt)
        df["pct_used"] = df["pct_used"].apply(
            lambda x: f"{x:.1f}%" if x is not None else "N/A"
        )
        st.dataframe(
            df[["category", "budget", "spent", "remaining", "pct_used"]].rename(
                columns={
                    "category": "Category",
                    "budget": "Budget",
                    "spent": "Spent",
                    "remaining": "Remaining",
                    "pct_used": "% Used",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: ANALYTICS
# ══════════════════════════════════════════════════════════════════════════════
def show_analytics():
    db = require_db()
    st.title("📈 Analytics & Trends")

    # ── Monthly spending trend ───────────────────────────────────────────────
    st.subheader("Month-over-Month Total Spending")
    monthly = db.get_monthly_totals(limit=12)
    if monthly:
        df_monthly = pd.DataFrame(monthly).sort_values(["year", "month"])
        fig_trend = px.line(
            df_monthly,
            x="month_name",
            y="total",
            markers=True,
            labels={"month_name": "Month", "total": f"Total Spent ({CURRENCY})"},
            color_discrete_sequence=["#667eea"],
        )
        fig_trend.update_traces(line_width=3, marker_size=8)
        fig_trend.update_layout(margin=dict(t=10, b=10))
        st.plotly_chart(fig_trend, use_container_width=True)
    else:
        st.info("No data yet — add some expenses to see trends.")

    st.markdown("---")

    # ── Category trends ──────────────────────────────────────────────────────
    st.subheader("Category Spending Over Time")
    cat_trend = db.get_category_trend()
    if cat_trend:
        df_ct = pd.DataFrame(cat_trend)
        # Sort by year/month
        df_ct = df_ct.sort_values(["year", "month"])
        # Let user pick categories to compare
        all_cats = sorted(df_ct["category"].unique())
        selected_cats = st.multiselect(
            "Select categories to compare",
            all_cats,
            default=all_cats[:5],
        )
        if selected_cats:
            df_sel = df_ct[df_ct["category"].isin(selected_cats)]
            fig_ct = px.line(
                df_sel,
                x="month_name",
                y="total",
                color="category",
                markers=True,
                labels={"month_name": "Month", "total": f"Spent ({CURRENCY})", "category": "Category"},
                color_discrete_sequence=PALETTE,
            )
            fig_ct.update_traces(line_width=2, marker_size=6)
            fig_ct.update_layout(margin=dict(t=10, b=10))
            st.plotly_chart(fig_ct, use_container_width=True)
    else:
        st.info("Add expenses across multiple months to see trends.")

    st.markdown("---")

    # ── Increasing expenses detector ─────────────────────────────────────────
    st.subheader("📡 Where Are Your Expenses Increasing?")
    month_label = datetime(sel_year, sel_month, 1).strftime("%B %Y")
    py, pm = prev_month(sel_year, sel_month)
    prev_label = datetime(py, pm, 1).strftime("%B %Y")

    cur_summary = {r["category"]: r["total"] for r in db.get_monthly_summary(sel_year, sel_month)}
    prev_summary = {r["category"]: r["total"] for r in db.get_monthly_summary(py, pm)}

    all_cats_combined = sorted(set(cur_summary) | set(prev_summary))

    if all_cats_combined:
        rows = []
        for cat in all_cats_combined:
            cur = cur_summary.get(cat, 0.0)
            prev = prev_summary.get(cat, 0.0)
            if prev > 0:
                pct = (cur - prev) / prev * 100
            elif cur > 0:
                pct = None  # new category
            else:
                continue
            rows.append(
                {
                    "Category": cat,
                    prev_label: fmt(prev),
                    month_label: fmt(cur),
                    "Change": change_badge(pct),
                    "_pct": pct if pct is not None else 9999,
                    "_cur": cur,
                }
            )

        rows_sorted = sorted(rows, key=lambda x: x["_pct"], reverse=True)

        # Alert boxes for significant increases
        high_increase = [r for r in rows_sorted if r["_pct"] is not None and r["_pct"] > 20]
        if high_increase:
            st.markdown("**Categories with >20% increase:**")
            for r in high_increase[:5]:
                st.markdown(
                    f'<div class="alert-box">🔺 <b>{r["Category"]}</b>: '
                    f'{r[prev_label]} → {r[month_label]} ({r["Change"]})</div>',
                    unsafe_allow_html=True,
                )

        df_change = pd.DataFrame(rows_sorted).drop(columns=["_pct", "_cur"])
        st.dataframe(df_change, use_container_width=True, hide_index=True)

        # Waterfall chart for category changes
        if len(rows_sorted) > 1:
            fig_wf = go.Figure(
                go.Bar(
                    x=[r["Category"] for r in rows_sorted],
                    y=[
                        cur_summary.get(r["Category"], 0) - prev_summary.get(r["Category"], 0)
                        for r in rows_sorted
                    ],
                    marker_color=[
                        "#e74c3c"
                        if (cur_summary.get(r["Category"], 0) - prev_summary.get(r["Category"], 0)) > 0
                        else "#2ecc71"
                        for r in rows_sorted
                    ],
                )
            )
            fig_wf.update_layout(
                title=f"Change vs {prev_label} ({CURRENCY})",
                xaxis_title="Category",
                yaxis_title=f"Change ({CURRENCY})",
                margin=dict(t=40, b=20),
            )
            st.plotly_chart(fig_wf, use_container_width=True)
    else:
        st.info(f"No expense data found for {month_label} or {prev_label}.")

    st.markdown("---")

    # ── Year-to-date by category ─────────────────────────────────────────────
    st.subheader("Year-to-Date Category Breakdown")
    ytd_cats: dict[str, float] = {}
    for m in range(1, sel_month + 1):
        for r in db.get_monthly_summary(sel_year, m):
            ytd_cats[r["category"]] = ytd_cats.get(r["category"], 0) + r["total"]

    if ytd_cats:
        df_ytd = pd.DataFrame(
            [{"Category": k, "Total": v} for k, v in ytd_cats.items()]
        ).sort_values("Total", ascending=False)
        fig_ytd = px.bar(
            df_ytd,
            x="Category",
            y="Total",
            labels={"Total": f"Total ({CURRENCY})"},
            color="Category",
            color_discrete_sequence=PALETTE,
        )
        fig_ytd.update_layout(showlegend=False, margin=dict(t=10, b=10))
        st.plotly_chart(fig_ytd, use_container_width=True)
    else:
        st.info(f"No data for {sel_year} yet.")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: HISTORY
# ══════════════════════════════════════════════════════════════════════════════
def show_history():
    db = require_db()
    st.title("📋 Expense History")

    all_expenses = db.get_all_expenses(limit=500)

    if not all_expenses:
        st.info("No expenses recorded yet. Go to **Add Expense** to get started.")
        return

    df_all = pd.DataFrame(all_expenses)

    # ── Filters ──────────────────────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    with col1:
        filter_cats = sorted(df_all["category"].unique())
        selected_filter_cats = st.multiselect("Filter by category", filter_cats, default=[])
    with col2:
        months_available = sorted(df_all["month_name"].unique(), reverse=True)
        selected_filter_months = st.multiselect("Filter by month", months_available, default=[])
    with col3:
        min_amt = float(df_all["amount"].min())
        max_amt = float(df_all["amount"].max())
        if min_amt < max_amt:
            amt_range = st.slider(
                "Amount range",
                min_value=min_amt,
                max_value=max_amt,
                value=(min_amt, max_amt),
            )
        else:
            amt_range = (min_amt, max_amt)

    df_filtered = df_all.copy()
    if selected_filter_cats:
        df_filtered = df_filtered[df_filtered["category"].isin(selected_filter_cats)]
    if selected_filter_months:
        df_filtered = df_filtered[df_filtered["month_name"].isin(selected_filter_months)]
    df_filtered = df_filtered[
        (df_filtered["amount"] >= amt_range[0]) & (df_filtered["amount"] <= amt_range[1])
    ]

    st.caption(f"Showing {len(df_filtered)} of {len(df_all)} expenses")

    # ── Table ─────────────────────────────────────────────────────────────────
    df_display = df_filtered[["date", "month_name", "category", "description", "amount"]].copy()
    df_display["amount"] = df_display["amount"].apply(fmt)
    df_display.columns = ["Date", "Month", "Category", "Description", "Amount"]
    st.dataframe(df_display, use_container_width=True, hide_index=True)

    # ── Delete an expense ────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Delete an Expense")
    expense_options = {
        f"{r['date']} | {r['category']} | {fmt(r['amount'])} | {r['description']}": r["id"]
        for r in df_filtered.to_dict("records")
    }
    if expense_options:
        to_delete = st.selectbox("Select expense to delete", list(expense_options.keys()))
        if st.button("🗑️ Delete Selected Expense", type="primary"):
            if db.delete_expense(expense_options[to_delete]):
                st.success("Expense deleted.")
                st.rerun()
            else:
                st.error("Could not delete expense.")
    else:
        st.info("No expenses match the current filters.")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: COMPARE MONTHS
# ══════════════════════════════════════════════════════════════════════════════
def show_compare_months():
    db = require_db()
    st.title("🔍 Compare Months")
    st.markdown("Pick two months to compare spending side-by-side and drill into what drove any differences.")

    now = datetime.now()
    years = list(range(now.year, now.year - 5, -1))
    month_fmt = lambda m: datetime(2000, m, 1).strftime("%B")

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**Month A**")
        ya = st.selectbox("Year", years, key="cmp_ya", index=0)
        ma = st.selectbox(
            "Month", list(range(1, 13)),
            index=(now.month - 2) % 12,
            format_func=month_fmt,
            key="cmp_ma",
        )
    with col_b:
        st.markdown("**Month B**")
        yb = st.selectbox("Year", years, key="cmp_yb", index=0)
        mb = st.selectbox(
            "Month", list(range(1, 13)),
            index=now.month - 1,
            format_func=month_fmt,
            key="cmp_mb",
        )

    label_a = datetime(ya, ma, 1).strftime("%B %Y")
    label_b = datetime(yb, mb, 1).strftime("%B %Y")

    if (ya, ma) == (yb, mb):
        st.warning("Please select two different months to compare.")
        return

    sum_a = {r["category"]: r["total"] for r in db.get_monthly_summary(ya, ma)}
    sum_b = {r["category"]: r["total"] for r in db.get_monthly_summary(yb, mb)}
    exp_a = db.get_expenses_for_month(ya, ma)
    exp_b = db.get_expenses_for_month(yb, mb)

    if not sum_a and not sum_b:
        st.info("No expense data found for either selected month.")
        return

    by_cat_a: dict[str, list] = {}
    for e in exp_a:
        by_cat_a.setdefault(e["category"], []).append(e)
    by_cat_b: dict[str, list] = {}
    for e in exp_b:
        by_cat_b.setdefault(e["category"], []).append(e)

    total_a = sum(sum_a.values())
    total_b = sum(sum_b.values())
    diff_total = total_b - total_a

    # ── Identify the overall higher and lower month ───────────────────────────
    # Flags and "why" boxes only appear for categories where the higher month
    # also exceeded the lower month — not for categories that went the other way.
    if total_a >= total_b:
        hi_label, lo_label = label_a, label_b
        sum_hi, sum_lo = sum_a, sum_b
        by_cat_hi, by_cat_lo = by_cat_a, by_cat_b
    else:
        hi_label, lo_label = label_b, label_a
        sum_hi, sum_lo = sum_b, sum_a
        by_cat_hi, by_cat_lo = by_cat_b, by_cat_a

    # ── Summary metrics ───────────────────────────────────────────────────────
    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric(label_a, fmt(total_a))
    with m2:
        delta_sign = "+" if diff_total > 0 else ""
        st.metric(label_b, fmt(total_b), delta=f"{delta_sign}{fmt(diff_total)}", delta_color="inverse")
    with m3:
        if total_a == total_b:
            st.metric("Higher spending month", "Tied")
        else:
            base = min(total_a, total_b) if min(total_a, total_b) > 0 else 1
            pct_more = abs(diff_total) / base * 100
            st.metric("Higher spending month", hi_label, delta=f"{pct_more:.1f}% more", delta_color="off")

    st.markdown("---")

    # ── Build category rows ───────────────────────────────────────────────────
    all_cats = sorted(set(sum_a) | set(sum_b))
    cat_rows = []
    for cat in all_cats:
        a = sum_a.get(cat, 0.0)
        b = sum_b.get(cat, 0.0)
        hi = sum_hi.get(cat, 0.0)
        lo = sum_lo.get(cat, 0.0)
        # exceeded = the higher month also spent more in this specific category
        exceeded = hi > lo
        cat_rows.append((cat, a, b, hi, lo, exceeded))

    # Flagged (exceeded) categories first, sorted by gap; rest after
    cat_rows.sort(key=lambda x: (not x[5], -(x[3] - x[4])))

    # ── Highlights — only for categories where hi_label exceeded lo_label ─────
    big_jumps = [
        (cat, lo, hi) for cat, a, b, hi, lo, exc in cat_rows
        if exc and lo > 0 and (hi - lo) / lo * 100 > 20
    ]
    new_cats  = [cat for cat, a, b, hi, lo, exc in cat_rows if exc and lo == 0 and hi > 0]
    gone_cats = [cat for cat, a, b, hi, lo, exc in cat_rows if not exc and hi == 0 and lo > 0]

    if big_jumps or new_cats or gone_cats:
        st.subheader("Highlights")
        if big_jumps:
            st.markdown(f"**Categories where {hi_label} exceeded {lo_label} by >20%:**")
            for cat, lo, hi in big_jumps[:5]:
                pct = (hi - lo) / lo * 100
                st.markdown(
                    f'<div class="danger-box">🔺 <b>{cat}</b>: {fmt(lo)} ({lo_label}) → {fmt(hi)} ({hi_label})'
                    f'  (<b>+{pct:.1f}%</b>, over by {fmt(hi - lo)})</div>',
                    unsafe_allow_html=True,
                )
        if new_cats:
            st.markdown(
                f'<div class="alert-box">🆕 <b>New in {hi_label}:</b> {", ".join(new_cats)}</div>',
                unsafe_allow_html=True,
            )
        if gone_cats:
            st.markdown(
                f'<div class="alert-box">🟢 <b>Not spent in {hi_label}:</b> {", ".join(gone_cats)}</div>',
                unsafe_allow_html=True,
            )
        st.markdown("---")

    # ── Grouped bar chart ─────────────────────────────────────────────────────
    st.subheader("Side-by-Side Category Comparison")
    chart_data = []
    for cat, a, b, hi, lo, exc in cat_rows:
        chart_data.append({"Category": cat, "Month": label_a, "Amount": a})
        chart_data.append({"Category": cat, "Month": label_b, "Amount": b})

    fig = px.bar(
        pd.DataFrame(chart_data),
        x="Category",
        y="Amount",
        color="Month",
        barmode="group",
        labels={"Amount": f"Amount ({CURRENCY})"},
        color_discrete_map={label_a: "#667eea", label_b: "#ff6b6b"},
    )
    fig.update_layout(margin=dict(t=10, b=10), legend_title="")
    st.plotly_chart(fig, use_container_width=True)

    # ── Category drill-down ───────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Category Breakdown")
    st.caption(
        f"🔺 Flagged = {hi_label} (higher month) also exceeded {lo_label} in that category. "
        f"Expand to see individual expenses and the reason behind the difference."
    )

    for cat, a, b, hi, lo, exceeded in cat_rows:
        ec_a = by_cat_a.get(cat, [])
        ec_b = by_cat_b.get(cat, [])
        ec_hi = by_cat_hi.get(cat, [])
        ec_lo = by_cat_lo.get(cat, [])

        if exceeded:
            diff = hi - lo
            pct_str = ""
            if lo > 0:
                pct_str = f" (+{diff / lo * 100:.1f}%)"
            elif lo == 0:
                pct_str = " (new)"
            badge = f"  🔺 {hi_label} over by {fmt(diff)}{pct_str}"
        else:
            gap = lo - hi
            pct_str = f" (+{gap / hi * 100:.1f}%)" if hi > 0 and gap > 0 else ""
            badge = f"  🟢 {lo_label} higher by {fmt(gap)}{pct_str}" if gap > 0 else "  ➡ Same"

        expander_label = f"{cat}  —  {label_a}: {fmt(a)}  |  {label_b}: {fmt(b)}{badge}"

        with st.expander(expander_label):
            left, right = st.columns(2)

            with left:
                st.markdown(f"**{label_a}** — {fmt(a)} ({len(ec_a)} transactions)")
                if ec_a:
                    df_ea = pd.DataFrame(ec_a)[["date", "description", "amount"]]
                    df_ea["amount"] = df_ea["amount"].apply(fmt)
                    st.dataframe(df_ea, use_container_width=True, hide_index=True)
                else:
                    st.caption("No expenses this month.")

            with right:
                st.markdown(f"**{label_b}** — {fmt(b)} ({len(ec_b)} transactions)")
                if ec_b:
                    df_eb = pd.DataFrame(ec_b)[["date", "description", "amount"]]
                    df_eb["amount"] = df_eb["amount"].apply(fmt)
                    st.dataframe(df_eb, use_container_width=True, hide_index=True)
                else:
                    st.caption("No expenses this month.")

            # "Why?" box — only shown when the higher month exceeded in this category
            if exceeded and hi > lo:
                insights = []
                txn_diff = len(ec_hi) - len(ec_lo)
                if txn_diff > 0:
                    insights.append(f"{txn_diff} more transaction(s) in {hi_label}")
                elif txn_diff < 0:
                    insights.append(f"{abs(txn_diff)} fewer transaction(s) in {hi_label}")

                avg_hi = hi / len(ec_hi) if ec_hi else 0
                avg_lo = lo / len(ec_lo) if ec_lo else 0
                if avg_hi > 0 and avg_lo > 0 and abs(avg_hi - avg_lo) > 1:
                    direction = "higher" if avg_hi > avg_lo else "lower"
                    insights.append(
                        f"Average transaction {direction} in {hi_label} ({fmt(avg_hi)} vs {fmt(avg_lo)})"
                    )

                if ec_hi:
                    top = max(ec_hi, key=lambda e: e["amount"])
                    desc = top["description"] or "—"
                    insights.append(f"Largest expense in {hi_label}: {desc} ({fmt(top['amount'])})")

                if insights:
                    insight_html = "<br>".join(f"• {i}" for i in insights)
                    st.markdown(
                        f'<div class="danger-box" style="margin-top:8px">'
                        f"<b>Why did {hi_label} exceed {lo_label} here?</b><br>{insight_html}</div>",
                        unsafe_allow_html=True,
                    )


# ══════════════════════════════════════════════════════════════════════════════
# Router
# ══════════════════════════════════════════════════════════════════════════════
if page == "Dashboard":
    show_dashboard()
elif page == "Add Expense":
    show_add_expense()
elif page == "Set Budget":
    show_set_budget()
elif page == "Analytics":
    show_analytics()
elif page == "History":
    show_history()
elif page == "Compare Months":
    show_compare_months()
