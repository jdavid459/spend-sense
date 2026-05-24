from __future__ import annotations

import sys
from pathlib import Path

import dash
import dash_bootstrap_components as dbc
import plotly.express as px
from dash import Input, Output, dcc, html

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.cohere_client import summarize_spend
from src.config import DATA_MODE
from src.db import query_df

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
server = app.server


def safe_query(sql: str):
    try:
        return query_df(sql)
    except Exception:
        return None


transactions = safe_query("select * from marts.fct_transactions order by transaction_date desc")
monthly = safe_query("select * from marts.mart_monthly_spend order by month")
anomalies = safe_query("select * from marts.mart_anomalies order by severity_score desc")
recurring = safe_query("select * from marts.mart_recurring_spend order by estimated_monthly_cost desc")

if transactions is not None and not transactions.empty:
    total_spend = transactions.loc[transactions["is_debit"], "amount_abs"].sum()
    txn_count = len(transactions)
    anomaly_count = int(transactions["is_anomaly"].sum())
    recurring_total = 0 if recurring is None or recurring.empty else recurring["estimated_monthly_cost"].sum()
else:
    total_spend = txn_count = anomaly_count = recurring_total = 0

app.layout = dbc.Container(
    [
        dbc.Row(
            [
                dbc.Col(html.H1("SpendSense"), md=8),
                dbc.Col(dbc.Badge(f"Dataset: {DATA_MODE}", color="info", className="mt-3"), md=4),
            ],
            align="center",
        ),
        html.P("AI-assisted spend analytics from Chase-like transaction data."),
        dbc.Alert(
            "If charts are empty, run: python scripts/generate_demo_data.py && "
            "python scripts/ingest_chase_csv.py && cd dbt && dbt seed --profiles-dir . && "
            "dbt run --profiles-dir .",
            color="warning",
            is_open=transactions is None,
        ),
        dbc.Row(
            [
                dbc.Col(dbc.Card(dbc.CardBody([html.H6("Total Spend"), html.H3(f"${total_spend:,.2f}")])), md=3),
                dbc.Col(dbc.Card(dbc.CardBody([html.H6("Transactions"), html.H3(f"{txn_count:,}")])), md=3),
                dbc.Col(dbc.Card(dbc.CardBody([html.H6("Anomalies"), html.H3(f"{anomaly_count:,}")])), md=3),
                dbc.Col(
                    dbc.Card(dbc.CardBody([html.H6("Monthly Recurring"), html.H3(f"${recurring_total:,.2f}")])),
                    md=3,
                ),
            ],
            className="mb-4",
        ),
        dcc.Tabs(
            [
                dcc.Tab(label="Overview", children=[html.Div(id="overview-tab", className="p-3")]),
                dcc.Tab(label="Transactions", children=[html.Div(id="transactions-tab", className="p-3")]),
                dcc.Tab(label="Anomalies", children=[html.Div(id="anomalies-tab", className="p-3")]),
                dcc.Tab(label="Recurring", children=[html.Div(id="recurring-tab", className="p-3")]),
                dcc.Tab(label="AI Summary", children=[html.Div(id="ai-tab", className="p-3")]),
            ]
        ),
    ],
    fluid=True,
)


@app.callback(Output("overview-tab", "children"), Input("overview-tab", "id"))
def render_overview(_):
    if monthly is None or monthly.empty:
        return html.P("No monthly spend data available yet.")
    fig_month = px.line(monthly, x="month", y="total_spend", color="final_category", markers=True)
    fig_cat = px.bar(
        monthly.groupby("final_category", as_index=False)["total_spend"].sum(),
        x="final_category",
        y="total_spend",
        title="Spend by category",
    )
    return [dcc.Graph(figure=fig_month), dcc.Graph(figure=fig_cat)]


@app.callback(Output("transactions-tab", "children"), Input("transactions-tab", "id"))
def render_transactions(_):
    if transactions is None or transactions.empty:
        return html.P("No transactions available yet.")
    cols = ["transaction_date", "normalized_merchant", "final_category", "amount", "is_recurring", "is_anomaly"]
    return dbc.Table.from_dataframe(transactions[cols].head(100), striped=True, bordered=True, hover=True)


@app.callback(Output("anomalies-tab", "children"), Input("anomalies-tab", "id"))
def render_anomalies(_):
    if anomalies is None or anomalies.empty:
        return html.P("No anomalies flagged yet.")
    return dbc.Table.from_dataframe(anomalies, striped=True, bordered=True, hover=True)


@app.callback(Output("recurring-tab", "children"), Input("recurring-tab", "id"))
def render_recurring(_):
    if recurring is None or recurring.empty:
        return html.P("No recurring transactions detected yet.")
    fig = px.bar(
        recurring,
        x="normalized_merchant",
        y="estimated_monthly_cost",
        title="Estimated monthly recurring spend",
    )
    return [dcc.Graph(figure=fig), dbc.Table.from_dataframe(recurring, striped=True, bordered=True, hover=True)]


@app.callback(Output("ai-tab", "children"), Input("ai-tab", "id"))
def render_ai(_):
    if monthly is None or monthly.empty:
        return html.P("No metrics available for summary yet.")
    metrics = ["Monthly spend by category:", monthly.to_string(index=False)]
    if anomalies is not None and not anomalies.empty:
        metrics += ["\nAnomalies:", anomalies.head(10).to_string(index=False)]
    if recurring is not None and not recurring.empty:
        metrics += ["\nRecurring spend:", recurring.to_string(index=False)]
    return dbc.Card(dbc.CardBody(html.Pre(summarize_spend("\n".join(metrics)), style={"whiteSpace": "pre-wrap"})))


if __name__ == "__main__":
    app.run(debug=True)
