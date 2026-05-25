from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import Input, Output, dcc, html, no_update

from src.semantic_search import MIN_QUERY_LENGTH, search_transactions

DEFAULT_TRANSACTION_COLUMNS = [
    "transaction_date",
    "normalized_merchant",
    "merchant_group",
    "merchant_source",
    "category_source",
    "final_category",
    "raw_category",
    "amount",
    "transaction_type",
    "is_recurring",
    "is_anomaly",
    "raw_description",
]
SEARCH_RESULT_COLUMNS = [
    "rank",
    "match_confidence",
    "transaction_date",
    "normalized_merchant",
    "merchant_group",
    "final_category",
    "amount_abs",
    "merchant_source",
    "is_recurring",
    "is_anomaly",
    "raw_description",
]


def render_transactions_tab(
    df,
    *,
    muted: str,
    card_style: dict,
):
    helper_text = (
        "Type a natural query like coffee, subscriptions, travel, or health. "
        "Search runs after a short pause and only affects this transaction table."
    )
    if df.empty:
        default_results = dbc.Alert("No transactions match the current filters.", color="light", className="border")
    else:
        default_results = html.Div(
            [
                dbc.Alert(
                    (
                        f"Browsing {len(df):,} filtered transactions. "
                        f"Enter {MIN_QUERY_LENGTH}+ characters to start AI search."
                    ),
                    color="light",
                    className="border",
                )
            ]
        )

    return dbc.Card(
        dbc.CardBody(
            [
                html.H4("Transactions"),
                html.P(
                    "This tab combines normal browsing with Cohere-powered search: embeddings for recall, "
                    "rerank for precision, and DuckDB caching for auditability.",
                    style={"color": muted},
                ),
                html.Label("Search within current transactions", className="small fw-semibold"),
                dcc.Input(
                    id="transaction-search-query",
                    type="text",
                    debounce=0.5,
                    placeholder="Start typing: coffee, subscriptions, travel, cafes, transit...",
                    className="form-control",
                ),
                html.Div(helper_text, className="small mt-2 mb-3", style={"color": muted}),
                dbc.Spinner(html.Div(id="transaction-search-results", children=default_results), color="primary"),
            ]
        ),
        style=card_style,
    )


def _default_transactions_view(df, *, table_from_df):
    return html.Div(
        [
            dbc.Card(
                dbc.CardBody(table_from_df(df, DEFAULT_TRANSACTION_COLUMNS, 20)),
                className="border-0",
            )
        ]
    )


def _render_search_results(results, semantic_candidates, meta, *, muted, metric_card, table_from_df, empty_state):
    if results.empty:
        return html.Div(
            [
                dbc.Alert(
                    [
                        html.Strong("No confident matches. "),
                        f"The search did not find likely-accurate results for “{meta['query_text']}”. ",
                        "Try a slightly broader term or clear the search to browse all filtered transactions.",
                    ],
                    color="warning",
                    className="border",
                )
            ]
        )

    cards = dbc.Row(
        [
            dbc.Col(
                metric_card("Likely Matches", f"{meta.get('result_count', 0):,}", meta.get("query_text", "")),
                lg=4,
            ),
            dbc.Col(
                metric_card(
                    "Retrieval",
                    "Semantic + Rerank" if meta.get("used_rerank") else "Semantic only",
                    meta.get("rerank_model", meta.get("embedding_model", "")),
                    value_size="24px",
                ),
                lg=4,
            ),
            dbc.Col(
                metric_card(
                    "Cache",
                    f"{meta.get('cache_hits', 0):,} hit / {meta.get('embedded_now', 0):,} new",
                    "Query cache hit" if meta.get("query_cached") else "Query cache miss",
                    value_size="24px",
                ),
                lg=4,
            ),
        ],
        className="g-3 mb-4",
    )

    preview_lines = []
    for row in semantic_candidates.head(5).itertuples(index=False):
        preview_lines.append(
            f"hybrid={row.hybrid_score:.4f} | semantic={row.semantic_score:.4f} | lexical={row.lexical_score:.1f} "
            f"| {row.normalized_merchant} | {row.raw_description}"
        )

    children = [
        cards,
        dbc.Alert(
            (
                f"Showing only likely-accurate matches for “{meta['query_text']}”. "
                f"Searched {meta.get('document_count', 0):,} filtered transactions and kept "
                f"{meta.get('result_count', 0):,} after precision gating."
            ),
            color="light",
            className="border",
        ),
        dbc.Card(dbc.CardBody(table_from_df(results, SEARCH_RESULT_COLUMNS, 20)), className="mb-4"),
        html.Details(
            [
                html.Summary("View retrieval diagnostics", className="fw-semibold"),
                html.Pre(
                    "\n".join(preview_lines),
                    style={
                        "whiteSpace": "pre-wrap",
                        "marginTop": "12px",
                        "padding": "16px",
                        "backgroundColor": "#f8fafc",
                        "borderRadius": "12px",
                        "border": "1px solid #e2e8f0",
                        "fontSize": "13px",
                        "lineHeight": "1.5",
                        "color": muted,
                    },
                ),
            ]
        ),
    ]
    if meta.get("rerank_error"):
        children.insert(
            2,
            dbc.Alert(
                [html.Strong("Rerank fallback: "), meta["rerank_error"]],
                color="warning",
                className="border",
            ),
        )
    return html.Div(children)


def register_transaction_search_callbacks(
    app,
    *,
    filter_transactions,
    empty_state,
    metric_card,
    table_from_df,
    muted: str,
):
    @app.callback(
        Output("transaction-search-results", "children"),
        Input("tabs", "value"),
        Input("date-range", "start_date"),
        Input("date-range", "end_date"),
        Input("category-filter", "value"),
        Input("merchant-filter", "value"),
        Input("view-mode", "value"),
        Input("transaction-search-query", "value"),
        prevent_initial_call=False,
    )
    def render_transaction_results(tab, start_date, end_date, categories, merchants, view_mode, query_text):
        if tab != "transactions":
            return no_update

        df = filter_transactions(start_date, end_date, categories, merchants, view_mode)
        if df.empty:
            return empty_state("No transactions match the current filters.")

        query = (query_text or "").strip()
        if not query:
            return _default_transactions_view(df, table_from_df=table_from_df)

        if len(query) < MIN_QUERY_LENGTH:
            return html.Div(
                [
                    dbc.Alert(
                        f"Keep typing — AI search starts at {MIN_QUERY_LENGTH} characters. "
                        "Clear the box to return to the full transaction table.",
                        color="light",
                        className="border",
                    ),
                    dbc.Card(
                        dbc.CardBody(table_from_df(df, DEFAULT_TRANSACTION_COLUMNS, 20)),
                        className="border-0",
                    ),
                ]
            )

        try:
            results, semantic_candidates, meta = search_transactions(df, query)
        except Exception as exc:
            return dbc.Alert(str(exc), color="warning", className="border mb-0")

        return _render_search_results(
            results,
            semantic_candidates,
            meta,
            muted=muted,
            metric_card=metric_card,
            table_from_df=table_from_df,
            empty_state=empty_state,
        )
