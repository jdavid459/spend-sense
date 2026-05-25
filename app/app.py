from __future__ import annotations

import os
import sys
from pathlib import Path

import dash
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.express as px
from dash import Input, Output, dash_table, dcc, html

sys.path.append(str(Path(__file__).resolve().parents[1]))

try:
    from components.ai_summary import register_ai_summary_callbacks, render_ai_summary_tab
    from components.semantic_search import register_transaction_search_callbacks, render_transactions_tab
except ImportError:
    from app.components.ai_summary import register_ai_summary_callbacks, render_ai_summary_tab
    from app.components.semantic_search import register_transaction_search_callbacks, render_transactions_tab

from src.ai_summary import filter_daily_metrics
from src.config import DATA_MODE
from src.db import query_df

ACCENT = "#2563eb"
MUTED = "#64748b"
BACKGROUND = "#f8fafc"
CARD_STYLE = {
    "border": "0",
    "borderRadius": "18px",
    "boxShadow": "0 12px 30px rgba(15, 23, 42, 0.08)",
}

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP], suppress_callback_exceptions=True)
server = app.server


def safe_query(sql: str) -> pd.DataFrame:
    try:
        return query_df(sql)
    except Exception:
        return pd.DataFrame()


def money(value: float | int | None) -> str:
    if pd.isna(value) or value is None:
        return "$0.00"
    return f"${value:,.2f}"


def pct(value: float | int | None) -> str:
    if pd.isna(value) or value is None:
        return "—"
    return f"{value:.1%}"


def load_data() -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    txns = safe_query("select * from marts.fct_transactions order by transaction_date desc")
    monthly_spend = safe_query("select * from marts.mart_monthly_spend order by month")
    flagged = safe_query("select * from marts.mart_anomalies order by severity_score desc")
    recurring_spend = safe_query("select * from marts.mart_recurring_spend order by estimated_monthly_cost desc")
    merchant_review_data = safe_query(
        "select * from marts.mart_merchant_review order by needs_review desc, review_priority_score desc"
    )
    spend_kpis = safe_query("select * from marts.mart_spend_kpis")
    monthly_kpis = safe_query("select * from marts.mart_monthly_kpis order by month")
    category_metrics = safe_query("select * from marts.mart_category_metrics order by total_spend desc")
    data_quality = safe_query("select * from marts.mart_data_quality order by total_spend desc")
    metric_summary = safe_query("select * from marts.mart_metric_summary order by metric_group, metric_label")
    daily_metrics = safe_query(
        "select * from marts.mart_daily_metric_values order by metric_date, metric_group, metric_name"
    )

    for df in [
        txns,
        monthly_spend,
        flagged,
        recurring_spend,
        merchant_review_data,
        spend_kpis,
        monthly_kpis,
        category_metrics,
        data_quality,
        metric_summary,
        daily_metrics,
    ]:
        for col in df.columns:
            if "date" in col or col in {"month", "first_seen", "last_seen"}:
                df[col] = pd.to_datetime(df[col], errors="coerce")

    return (
        txns,
        monthly_spend,
        flagged,
        recurring_spend,
        merchant_review_data,
        spend_kpis,
        monthly_kpis,
        category_metrics,
        data_quality,
        metric_summary,
        daily_metrics,
    )


(
    transactions,
    monthly,
    anomalies,
    recurring,
    merchant_review,
    spend_kpis,
    monthly_kpis,
    category_metrics,
    data_quality,
    metric_summary,
    daily_metrics,
) = load_data()


def filter_transactions(
    start_date: str | None,
    end_date: str | None,
    categories: list[str] | None,
    merchants: list[str] | None,
    view_mode: str,
) -> pd.DataFrame:
    if transactions.empty:
        return transactions.copy()

    df = transactions.copy()
    if start_date:
        df = df[df["transaction_date"] >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df["transaction_date"] <= pd.to_datetime(end_date)]
    if categories:
        df = df[df["final_category"].isin(categories)]
    if merchants:
        df = df[df["normalized_merchant"].isin(merchants)]
    if view_mode == "debits":
        df = df[df["is_debit"]]
    elif view_mode == "credits":
        df = df[df["is_credit"]]
    elif view_mode == "anomalies":
        df = df[df["is_anomaly"]]
    elif view_mode == "recurring":
        df = df[df["is_recurring"]]
    return df


def metric_card(
    title: str,
    value: str,
    subtitle: str = "",
    color: str = ACCENT,
    value_size: str = "32px",
) -> dbc.Card:
    return dbc.Card(
        dbc.CardBody(
            [
                html.Div(title, className="text-uppercase small fw-semibold", style={"color": MUTED}),
                html.Div(
                    value,
                    className="fw-bold lh-sm",
                    style={"color": color, "fontSize": value_size, "wordBreak": "break-word"},
                ),
                html.Div(subtitle, className="small mt-1", style={"color": MUTED}),
            ]
        ),
        style=CARD_STYLE | {"height": "100%"},
    )


def markdown_summary_card(text: str, title: str | None = None) -> dbc.Card:
    children = []
    if title:
        children.append(html.H5(title, className="mb-3"))
    children.append(
        dcc.Markdown(
            text,
            style={"fontSize": "17px", "lineHeight": "1.7", "marginBottom": "0"},
        )
    )
    return dbc.Card(
        dbc.CardBody(children),
        style=CARD_STYLE | {"background": "linear-gradient(180deg, #ffffff 0%, #f8fbff 100%)"},
        className="mb-4",
    )


def empty_state(message: str) -> dbc.Alert:
    return dbc.Alert(message, color="light", className="border")


def table_from_df(df: pd.DataFrame, columns: list[str], page_size: int = 15) -> dash_table.DataTable:
    table_df = df[columns].copy()
    for col in table_df.columns:
        if pd.api.types.is_datetime64_any_dtype(table_df[col]):
            table_df[col] = table_df[col].dt.strftime("%Y-%m-%d")
    for col in table_df.columns:
        if "share" in col or "rate" in col or "pct" in col:
            if pd.api.types.is_numeric_dtype(table_df[col]):
                table_df[col] = table_df[col].map(lambda value: pct(value))
        elif any(token in col for token in ["amount", "spend", "cost", "score", "stddev", "volatility"]):
            if pd.api.types.is_numeric_dtype(table_df[col]):
                table_df[col] = table_df[col].round(2)

    return dash_table.DataTable(
        data=table_df.to_dict("records"),
        columns=[{"name": col.replace("_", " ").title(), "id": col} for col in table_df.columns],
        page_size=page_size,
        sort_action="native",
        filter_action="native",
        style_table={"overflowX": "auto"},
        style_cell={
            "fontFamily": "Inter, system-ui, -apple-system, BlinkMacSystemFont, sans-serif",
            "fontSize": "13px",
            "padding": "10px",
            "textAlign": "left",
            "maxWidth": "280px",
            "overflow": "hidden",
            "textOverflow": "ellipsis",
        },
        style_header={"backgroundColor": "#f1f5f9", "fontWeight": "700", "border": "0"},
        style_data={"border": "0", "borderBottom": "1px solid #e2e8f0"},
        style_data_conditional=[
            {"if": {"filter_query": "{is_anomaly} = True"}, "backgroundColor": "#fef2f2"},
            {"if": {"filter_query": "{is_recurring} = True"}, "backgroundColor": "#eff6ff"},
        ],
    )


def date_bounds() -> tuple[str | None, str | None]:
    if transactions.empty:
        return None, None
    return (
        transactions["transaction_date"].min().date().isoformat(),
        transactions["transaction_date"].max().date().isoformat(),
    )


min_date, max_date = date_bounds()
category_options = [
    {"label": category, "value": category}
    for category in sorted(transactions.get("final_category", pd.Series(dtype=str)).dropna().unique())
]
merchant_options = [
    {"label": merchant, "value": merchant}
    for merchant in sorted(transactions.get("normalized_merchant", pd.Series(dtype=str)).dropna().unique())
]
metric_group_options = [
    {"label": group, "value": group}
    for group in sorted(daily_metrics.get("metric_group", pd.Series(dtype=str)).dropna().unique())
]

register_ai_summary_callbacks(
    app,
    daily_metrics=daily_metrics,
    filter_transactions=filter_transactions,
    empty_state=empty_state,
    markdown_summary_card=markdown_summary_card,
)
register_transaction_search_callbacks(
    app,
    filter_transactions=filter_transactions,
    empty_state=empty_state,
    metric_card=metric_card,
    table_from_df=table_from_df,
    muted=MUTED,
)

app.layout = html.Div(
    style={"backgroundColor": BACKGROUND, "minHeight": "100vh"},
    children=[
        dbc.Container(
            [
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                html.Div("SpendSense", className="display-5 fw-bold"),
                                html.Div(
                                    "A dbt-backed transaction intelligence dashboard for Chase CSV data.",
                                    style={"color": MUTED},
                                ),
                            ],
                            md=8,
                        ),
                        dbc.Col(
                            dbc.Badge(
                                f"Dataset: {DATA_MODE}",
                                color="primary" if DATA_MODE == "private" else "success",
                                className="px-3 py-2 fs-6 mt-3 float-md-end",
                            ),
                            md=4,
                        ),
                    ],
                    align="center",
                    className="pt-4 pb-3",
                ),
                dbc.Alert(
                    "No mart data found. Run ingestion and dbt first, then restart the app.",
                    color="warning",
                    is_open=transactions.empty,
                ),
                dbc.Card(
                    dbc.CardBody(
                        [
                            dbc.Row(
                                [
                                    dbc.Col(
                                        [
                                            html.Label("Date range", className="small fw-semibold"),
                                            dcc.DatePickerRange(
                                                id="date-range",
                                                min_date_allowed=min_date,
                                                max_date_allowed=max_date,
                                                start_date=min_date,
                                                end_date=max_date,
                                                display_format="MMM D, YYYY",
                                            ),
                                        ],
                                        lg=3,
                                    ),
                                    dbc.Col(
                                        [
                                            html.Label("Categories", className="small fw-semibold"),
                                            dcc.Dropdown(
                                                id="category-filter",
                                                options=category_options,
                                                multi=True,
                                                placeholder="All categories",
                                            ),
                                        ],
                                        lg=3,
                                    ),
                                    dbc.Col(
                                        [
                                            html.Label("Merchants", className="small fw-semibold"),
                                            dcc.Dropdown(
                                                id="merchant-filter",
                                                options=merchant_options,
                                                multi=True,
                                                placeholder="All merchants",
                                            ),
                                        ],
                                        lg=3,
                                    ),
                                    dbc.Col(
                                        [
                                            html.Label("View", className="small fw-semibold"),
                                            dbc.RadioItems(
                                                id="view-mode",
                                                options=[
                                                    {"label": "Debits", "value": "debits"},
                                                    {"label": "All", "value": "all"},
                                                    {"label": "Anomalies", "value": "anomalies"},
                                                    {"label": "Recurring", "value": "recurring"},
                                                ],
                                                value="debits",
                                                inline=True,
                                            ),
                                        ],
                                        lg=3,
                                    ),
                                ],
                                className="g-3",
                            )
                        ]
                    ),
                    style=CARD_STYLE,
                    className="mb-4",
                ),
                html.Div(id="kpi-row", className="mb-4"),
                dcc.Tabs(
                    id="tabs",
                    value="overview",
                    children=[
                        dcc.Tab(label="Overview", value="overview"),
                        dcc.Tab(label="Transactions", value="transactions"),
                        dcc.Tab(label="Anomalies", value="anomalies"),
                        dcc.Tab(label="Recurring", value="recurring"),
                        dcc.Tab(label="Metrics", value="metrics"),
                        dcc.Tab(label="Merchant Cleanup", value="merchants"),
                        dcc.Tab(label="AI Summary", value="ai"),
                    ],
                ),
                html.Div(id="tab-content", className="py-4"),
            ],
            fluid=True,
            style={"maxWidth": "1500px"},
        )
    ],
)


@app.callback(
    Output("kpi-row", "children"),
    Input("date-range", "start_date"),
    Input("date-range", "end_date"),
    Input("category-filter", "value"),
    Input("merchant-filter", "value"),
    Input("view-mode", "value"),
)
def render_kpis(start_date, end_date, categories, merchants, view_mode):
    df = filter_transactions(start_date, end_date, categories, merchants, view_mode)
    debits = df[df["is_debit"]] if not df.empty else df
    credits = df[df["is_credit"]] if not df.empty else df
    top_category = "—"
    top_category_spend = 0
    if not debits.empty:
        category_spend = debits.groupby("final_category")["amount_abs"].sum().sort_values(ascending=False)
        top_category = category_spend.index[0]
        top_category_spend = category_spend.iloc[0]
    recurring_total = debits.loc[debits["is_recurring"], "amount_abs"].sum() if not debits.empty else 0
    date_label = "—"
    if start_date and end_date:
        date_label = (
            f"{pd.to_datetime(start_date).strftime('%b %-d, %Y')} – {pd.to_datetime(end_date).strftime('%b %-d, %Y')}"
        )

    return dbc.Row(
        [
            dbc.Col(
                metric_card("Spend", money(debits["amount_abs"].sum() if not debits.empty else 0), "Filtered debits"),
                lg=3,
            ),
            dbc.Col(
                metric_card(
                    "Credits",
                    money(credits["amount_abs"].sum() if not credits.empty else 0),
                    "Payments/credits",
                    "#16a34a",
                ),
                lg=3,
            ),
            dbc.Col(metric_card("Top Category", top_category, money(top_category_spend), value_size="28px"), lg=3),
            dbc.Col(
                metric_card(
                    "Anomalies",
                    f"{int(df['is_anomaly'].sum()) if not df.empty else 0:,}",
                    "Flagged transactions",
                    "#dc2626",
                ),
                lg=3,
            ),
            dbc.Col(metric_card("Transactions", f"{len(df):,}", "Rows in current view"), lg=3, className="mt-3"),
            dbc.Col(
                metric_card(
                    "Avg Transaction", money(debits["amount_abs"].mean() if not debits.empty else 0), "Debit avg"
                ),
                lg=3,
                className="mt-3",
            ),
            dbc.Col(
                metric_card("Recurring Spend", money(recurring_total), "Observed in filtered data"),
                lg=3,
                className="mt-3",
            ),
            dbc.Col(
                metric_card("Date Window", date_label, "Active filter", value_size="20px"),
                lg=3,
                className="mt-3",
            ),
        ],
        className="g-3",
    )


@app.callback(
    Output("tab-content", "children"),
    Input("tabs", "value"),
    Input("date-range", "start_date"),
    Input("date-range", "end_date"),
    Input("category-filter", "value"),
    Input("merchant-filter", "value"),
    Input("view-mode", "value"),
)
def render_tab(tab, start_date, end_date, categories, merchants, view_mode):
    df = filter_transactions(start_date, end_date, categories, merchants, view_mode)
    if df.empty:
        return empty_state("No transactions match the current filters.")

    debits = df[df["is_debit"]].copy()

    if tab == "overview":
        monthly_filtered = (
            debits.assign(month=debits["transaction_date"].dt.to_period("M").dt.to_timestamp())
            .groupby(["month", "final_category"], as_index=False)["amount_abs"]
            .sum()
        )
        category_spend = debits.groupby("final_category", as_index=False)["amount_abs"].sum()
        merchant_spend = (
            debits.groupby("normalized_merchant", as_index=False)["amount_abs"]
            .sum()
            .sort_values("amount_abs", ascending=False)
            .head(15)
        )
        merchant_spend["spend_label"] = merchant_spend["amount_abs"].map(lambda value: f"${value:,.0f}")
        daily = debits.groupby("transaction_date", as_index=False)["amount_abs"].sum()

        labels = {
            "amount_abs": "Spend",
            "final_category": "Category",
            "normalized_merchant": "Merchant",
            "transaction_date": "Date",
            "month": "Month",
        }
        fig_month = px.line(
            monthly_filtered,
            x="month",
            y="amount_abs",
            color="final_category",
            markers=True,
            title="Monthly spend by category",
            labels=labels,
        )
        fig_cat = px.bar(
            category_spend.sort_values("amount_abs", ascending=False),
            x="final_category",
            y="amount_abs",
            title="Spend by category",
            labels=labels,
        )
        fig_merchants = px.bar(
            merchant_spend.sort_values("amount_abs"),
            x="amount_abs",
            y="normalized_merchant",
            orientation="h",
            text="spend_label",
            title="Top merchants by spend",
            labels=labels,
        )
        fig_daily = px.line(daily, x="transaction_date", y="amount_abs", title="Daily spend", labels=labels)
        for fig in [fig_month, fig_cat, fig_merchants, fig_daily]:
            fig.update_layout(template="plotly_white", margin=dict(l=30, r=20, t=60, b=30))
            fig.update_yaxes(tickprefix="$", separatethousands=True)
        fig_cat.update_xaxes(tickangle=-45)
        fig_month.update_yaxes(tickprefix="$", separatethousands=True)
        fig_merchants.update_xaxes(tickprefix="$", separatethousands=True)
        fig_merchants.update_yaxes(tickprefix="")
        fig_merchants.update_traces(textposition="outside", cliponaxis=False)

        return dbc.Row(
            [
                dbc.Col(dbc.Card(dbc.CardBody(dcc.Graph(figure=fig_month)), style=CARD_STYLE), lg=8),
                dbc.Col(dbc.Card(dbc.CardBody(dcc.Graph(figure=fig_cat)), style=CARD_STYLE), lg=4),
                dbc.Col(
                    dbc.Card(dbc.CardBody(dcc.Graph(figure=fig_merchants)), style=CARD_STYLE), lg=6, className="mt-4"
                ),
                dbc.Col(dbc.Card(dbc.CardBody(dcc.Graph(figure=fig_daily)), style=CARD_STYLE), lg=6, className="mt-4"),
            ],
            className="g-3",
        )

    if tab == "transactions":
        return render_transactions_tab(
            df,
            muted=MUTED,
            card_style=CARD_STYLE,
        )

    if tab == "anomalies":
        flagged = df[df["is_anomaly"]].copy().sort_values(["zscore_vs_merchant", "zscore_vs_category"], ascending=False)
        if flagged.empty:
            return empty_state("No anomalies match the current filters.")
        cards = []
        for _, row in flagged.head(10).iterrows():
            severity = max(row.get("zscore_vs_merchant") or 0, row.get("zscore_vs_category") or 0)
            cards.append(
                dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            [
                                html.Div(row["normalized_merchant"], className="fw-bold fs-5"),
                                html.Div(row["transaction_date"].strftime("%Y-%m-%d"), style={"color": MUTED}),
                                html.Div(money(row["amount_abs"]), className="display-6 fw-bold text-danger"),
                                html.Div(row.get("anomaly_reason") or "Flagged as unusual"),
                                dbc.Badge(f"severity {severity:.1f}", color="danger", className="mt-2"),
                            ]
                        ),
                        style=CARD_STYLE,
                    ),
                    lg=4,
                    className="mb-3",
                )
            )
        cols = [
            "transaction_date",
            "normalized_merchant",
            "final_category",
            "amount_abs",
            "anomaly_reason",
            "zscore_vs_merchant",
            "zscore_vs_category",
        ]
        return [dbc.Row(cards), dbc.Card(dbc.CardBody(table_from_df(flagged, cols, 15)), style=CARD_STYLE)]

    if tab == "recurring":
        filtered_merchants = debits[debits["is_recurring"]]["normalized_merchant"].unique()
        recurring_filtered = recurring[recurring["normalized_merchant"].isin(filtered_merchants)].copy()
        if recurring_filtered.empty:
            return empty_state("No recurring transactions match the current filters.")
        recurring_filtered = recurring_filtered.sort_values("estimated_monthly_cost", ascending=False)
        recurring_plot = recurring_filtered.sort_values("estimated_monthly_cost", ascending=True).copy()
        recurring_plot["cost_label"] = recurring_plot["estimated_monthly_cost"].map(lambda value: f"${value:,.0f}")
        fig = px.bar(
            recurring_plot,
            x="estimated_monthly_cost",
            y="normalized_merchant",
            orientation="h",
            text="cost_label",
            title="Estimated monthly recurring spend",
        )
        fig.update_layout(template="plotly_white", margin=dict(l=30, r=40, t=60, b=30))
        fig.update_xaxes(tickprefix="$", separatethousands=True)
        fig.update_traces(textposition="outside", cliponaxis=False)
        cols = [
            "normalized_merchant",
            "final_category",
            "cadence",
            "avg_amount",
            "estimated_monthly_cost",
            "transaction_count",
            "first_seen",
            "last_seen",
        ]
        return dbc.Row(
            [
                dbc.Col(dbc.Card(dbc.CardBody(dcc.Graph(figure=fig)), style=CARD_STYLE), lg=5),
                dbc.Col(dbc.Card(dbc.CardBody(table_from_df(recurring_filtered, cols, 15)), style=CARD_STYLE), lg=7),
            ],
            className="g-3",
        )

    if tab == "metrics":
        return dbc.Card(
            dbc.CardBody(
                [
                    html.H4("Metrics"),
                    html.P(
                        "Each row is one additive metric from the dbt daily metric fact. Filters apply before "
                        "the rolling 30-day value, prior-period delta, and trend are displayed.",
                        style={"color": MUTED},
                    ),
                    dbc.Row(
                        [
                            dbc.Col(
                                [
                                    html.Label("Metric groups", className="small fw-semibold"),
                                    dcc.Dropdown(
                                        id="metric-group-filter",
                                        options=metric_group_options,
                                        multi=True,
                                        placeholder="All metric groups",
                                    ),
                                ],
                                lg=4,
                            )
                        ],
                        className="g-3 mb-4",
                    ),
                    html.Div(id="metrics-content"),
                ]
            ),
            style=CARD_STYLE,
        )

    if tab == "merchants":
        if merchant_review.empty:
            return empty_state("No merchant review mart found. Run dbt to build marts.mart_merchant_review.")

        visible_raw_descriptions = df["raw_description"].unique()
        review = merchant_review[merchant_review["raw_description"].isin(visible_raw_descriptions)].copy()
        review_cards = dbc.Row(
            [
                dbc.Col(
                    metric_card(
                        "Needs Review",
                        f"{int(review['needs_review'].sum()):,}",
                        "Raw descriptions",
                        "#dc2626",
                    ),
                    lg=3,
                ),
                dbc.Col(
                    metric_card(
                        "Unmapped Spend",
                        money(review.loc[review["needs_review"], "total_spend"].sum()),
                        "Prioritize cleanup here",
                    ),
                    lg=3,
                ),
                dbc.Col(
                    metric_card(
                        "Mapped Merchants",
                        f"{len(review) - int(review['needs_review'].sum()):,}",
                        "Already covered by rules",
                    ),
                    lg=3,
                ),
                dbc.Col(
                    metric_card(
                        "Top Priority Score",
                        f"{review['review_priority_score'].max():,.1f}",
                        "Count + spend + unmapped",
                    ),
                    lg=3,
                ),
            ],
            className="g-3 mb-4",
        )
        cols = [
            "needs_review",
            "review_priority_score",
            "review_reason",
            "raw_description",
            "normalized_merchant",
            "merchant_group",
            "merchant_source",
            "category_source",
            "raw_category",
            "final_category",
            "transaction_count",
            "total_spend",
            "avg_debit_amount",
            "first_seen",
            "last_seen",
        ]
        needs_review = review[review["needs_review"]].copy()
        cohere_enriched = review[review["merchant_source"] == "cohere_cache"].copy()
        seed_mapped = review[review["merchant_source"] == "seed_rule"].copy()

        def review_table(section_df: pd.DataFrame, empty_message: str):
            if section_df.empty:
                return empty_state(empty_message)
            return table_from_df(section_df, cols, 20)

        return dbc.Card(
            dbc.CardBody(
                [
                    html.H4("Merchant normalization review"),
                    html.P(
                        "This table is generated by dbt in marts.mart_merchant_review. "
                        "It prioritizes merchant patterns that should be promoted into governed seed rules.",
                        style={"color": MUTED},
                    ),
                    review_cards,
                    dcc.Tabs(
                        value="needs_review",
                        children=[
                            dcc.Tab(
                                label=f"Needs Review ({len(needs_review):,})",
                                value="needs_review",
                                children=[
                                    html.Div(
                                        review_table(needs_review, "No fallback merchants match the current filters."),
                                        className="pt-3",
                                    )
                                ],
                            ),
                            dcc.Tab(
                                label=f"Cohere Enriched ({len(cohere_enriched):,})",
                                value="cohere",
                                children=[
                                    html.Div(
                                        review_table(cohere_enriched, "No Cohere-enriched merchants yet."),
                                        className="pt-3",
                                    )
                                ],
                            ),
                            dcc.Tab(
                                label=f"Seed Mapped ({len(seed_mapped):,})",
                                value="seed",
                                children=[
                                    html.Div(
                                        review_table(seed_mapped, "No seed-mapped merchants match the filters."),
                                        className="pt-3",
                                    )
                                ],
                            ),
                            dcc.Tab(
                                label=f"All ({len(review):,})",
                                value="all",
                                children=[html.Div(table_from_df(review, cols, 20), className="pt-3")],
                            ),
                        ],
                    ),
                ]
            ),
            style=CARD_STYLE,
        )

    if tab == "ai":
        return render_ai_summary_tab(
            df,
            daily_metrics,
            start_date,
            end_date,
            categories,
            merchants,
            view_mode,
            accent=ACCENT,
            muted=MUTED,
            card_style=CARD_STYLE,
            metric_card=metric_card,
            markdown_summary_card=markdown_summary_card,
        )

    return empty_state("Unknown tab.")


@app.callback(
    Output("metrics-content", "children"),
    Input("date-range", "start_date"),
    Input("date-range", "end_date"),
    Input("category-filter", "value"),
    Input("merchant-filter", "value"),
    Input("view-mode", "value"),
    Input("metric-group-filter", "value"),
)
def render_metrics_content(start_date, end_date, categories, merchants, view_mode, metric_groups):
    if daily_metrics.empty:
        return empty_state("Daily metric mart not found. Run dbt build to create marts.mart_daily_metric_values.")

    metrics = filter_daily_metrics(daily_metrics, start_date, end_date, categories, merchants, view_mode)
    if metric_groups:
        metrics = metrics[metrics["metric_group"].isin(metric_groups)]

    if metrics.empty:
        return empty_state("No metric values match the current filters.")

    def format_by_unit(value, unit: str) -> str:
        if pd.isna(value):
            return "—"
        if unit == "currency":
            return money(value)
        if unit == "percent":
            return pct(value)
        if unit == "count":
            return f"{value:,.0f}"
        return f"{value:,.2f}"

    latest_metric_date = metrics["metric_date"].max()
    metric_rollups = (
        metrics[metrics["metric_date"] == latest_metric_date]
        .groupby(["metric_key", "metric_name", "metric_group", "unit"], as_index=False)[
            ["metric_value_l30d", "metric_value_prior_l30d"]
        ]
        .sum()
    )
    metric_rollups["delta_value"] = metric_rollups["metric_value_l30d"] - metric_rollups["metric_value_prior_l30d"]
    metric_rollups["delta_pct"] = metric_rollups["delta_value"] / metric_rollups["metric_value_prior_l30d"].replace(
        {0: pd.NA}
    )

    display_order = [
        "total_spend",
        "debit_transaction_count",
        "recurring_spend",
        "recurring_transaction_count",
        "anomaly_spend",
        "anomaly_transaction_count",
        "fallback_spend",
        "fallback_transaction_count",
        "cohere_spend",
        "cohere_transaction_count",
        "seed_rule_spend",
        "seed_rule_transaction_count",
        "credit_amount",
        "credit_transaction_count",
    ]
    metric_rollups["sort_order"] = metric_rollups["metric_key"].map({key: idx for idx, key in enumerate(display_order)})
    metric_rollups["sort_order"] = metric_rollups["sort_order"].fillna(999)
    metric_rollups = metric_rollups.sort_values(["sort_order", "metric_group", "metric_name"])

    trend = (
        metrics.groupby(["metric_date", "metric_key", "metric_name", "metric_group", "unit"], as_index=False)[
            "metric_value_l30d"
        ]
        .sum()
        .sort_values("metric_date")
    )

    def delta_text(row) -> str:
        delta = row["delta_value"]
        delta_pct = row["delta_pct"]
        if pd.isna(delta):
            return "No prior 30d"
        delta_value = format_by_unit(delta, row["unit"])
        if delta > 0:
            delta_value = f"+{delta_value}"
        pct_text = f" ({delta_pct:+.1%})" if not pd.isna(delta_pct) else ""
        return f"{delta_value}{pct_text} vs prior 30d"

    def delta_color(row) -> str:
        if pd.isna(row["delta_value"]) or row["delta_value"] == 0:
            return MUTED
        return "#16a34a" if row["delta_value"] < 0 else "#dc2626"

    metric_rows = []
    for _, row in metric_rollups.iterrows():
        metric_trend = trend[trend["metric_key"] == row["metric_key"]]
        fig = px.line(
            metric_trend,
            x="metric_date",
            y="metric_value_l30d",
            labels={"metric_date": "", "metric_value_l30d": ""},
        )
        fig.update_traces(
            line={"color": ACCENT, "width": 3},
            hovertemplate="%{x|%b %-d}<br>%{y:,.2f}<extra></extra>",
        )
        fig.update_layout(
            template="plotly_white",
            height=120,
            margin=dict(l=10, r=10, t=8, b=8),
            showlegend=False,
            xaxis={"showgrid": False, "title": None},
            yaxis={"showgrid": False, "title": None, "tickprefix": "$" if row["unit"] == "currency" else ""},
        )

        metric_rows.append(
            dbc.Card(
                dbc.CardBody(
                    dbc.Row(
                        [
                            dbc.Col(
                                [
                                    html.Div(
                                        row["metric_group"],
                                        className="text-uppercase small fw-semibold",
                                        style={"color": MUTED},
                                    ),
                                    html.Div(row["metric_name"], className="fw-bold fs-4"),
                                    html.Div("Rolling 30-day value", className="small", style={"color": MUTED}),
                                ],
                                lg=3,
                            ),
                            dbc.Col(
                                [
                                    html.Div(
                                        format_by_unit(row["metric_value_l30d"], row["unit"]),
                                        className="fw-bold lh-sm",
                                        style={"fontSize": "42px", "color": ACCENT},
                                    ),
                                    html.Div(
                                        delta_text(row),
                                        className="small fw-semibold mt-1",
                                        style={"color": delta_color(row)},
                                    ),
                                ],
                                lg=3,
                            ),
                            dbc.Col(dcc.Graph(figure=fig, config={"displayModeBar": False}), lg=6),
                        ],
                        align="center",
                        className="g-3",
                    )
                ),
                style=CARD_STYLE,
                className="mb-3",
            )
        )

    return [
        dbc.Alert(
            f"Showing rolling 30-day values as of {latest_metric_date.strftime('%Y-%m-%d')}. "
            "Read each row left to right: metric, current value, delta, trend.",
            color="light",
            className="border",
        ),
        html.Div(metric_rows),
    ]


if __name__ == "__main__":
    app.run(debug=True, port=int(os.getenv("PORT", "8050")))
