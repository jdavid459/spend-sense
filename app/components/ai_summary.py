from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import Input, Output, State, html, no_update

from src.ai_summary import (
    build_ai_prompt_context,
    build_fallback_summary,
    build_summary_context,
    filter_daily_metrics,
)
from src.cohere_client import summarize_spend


def render_ai_summary_tab(
    df,
    daily_metrics,
    start_date,
    end_date,
    categories,
    merchants,
    view_mode,
    *,
    accent: str,
    muted: str,
    card_style: dict,
    metric_card,
    markdown_summary_card,
):
    filtered_metrics = filter_daily_metrics(daily_metrics, start_date, end_date, categories, merchants, view_mode)
    summary_context, summary_meta = build_summary_context(
        df,
        filtered_metrics,
        start_date,
        end_date,
        categories,
        merchants,
        view_mode,
    )
    deterministic_summary = build_fallback_summary(summary_meta)

    summary_cards = dbc.Row(
        [
            dbc.Col(
                metric_card(
                    summary_meta["summary_card_1_title"],
                    summary_meta["summary_card_1_value"],
                    summary_meta["summary_card_1_subtitle"],
                ),
                lg=4,
            ),
            dbc.Col(
                metric_card(
                    summary_meta["summary_card_2_title"],
                    summary_meta["summary_card_2_value"],
                    summary_meta["summary_card_2_subtitle"],
                    value_size="28px",
                ),
                lg=4,
            ),
            dbc.Col(
                metric_card(
                    summary_meta["summary_card_3_title"],
                    summary_meta["summary_card_3_value"],
                    summary_meta["summary_card_3_subtitle"],
                    "#dc2626" if summary_meta["selected_anomaly_spend"] else accent,
                    value_size="28px",
                ),
                lg=4,
            ),
        ],
        className="g-3 mb-4",
    )

    return dbc.Card(
        dbc.CardBody(
            [
                html.H4("AI-generated spending summary"),
                html.P(
                    "This view now opens instantly with a deterministic summary. "
                    "Use the button below only when you want a Cohere-written version.",
                    style={"color": muted},
                ),
                summary_cards,
                dbc.Row(
                    [
                        dbc.Col(
                            dbc.Button(
                                "Generate AI Summary",
                                id="generate-ai-summary-btn",
                                color="primary",
                                className="px-4",
                            ),
                            lg="auto",
                        ),
                        dbc.Col(
                            [
                                html.Div(
                                    "Uses Cohere on demand. Cached responses return faster on repeat runs.",
                                    className="small",
                                    style={"color": muted},
                                ),
                                dbc.Spinner(
                                    html.Div(id="ai-summary-loading-indicator"),
                                    color="primary",
                                    size="sm",
                                ),
                            ],
                            lg=True,
                        ),
                    ],
                    align="center",
                    className="g-3 mb-3",
                ),
                html.Div(
                    id="ai-summary-display",
                    children=markdown_summary_card(deterministic_summary, "Instant summary"),
                ),
                dbc.Alert(
                    [
                        html.Strong("Grounding note: "),
                        "Both summaries use dbt-modeled transactions plus rolling 30-day metric comparisons. "
                        "Cohere prompt context and responses are cached in DuckDB for auditability.",
                    ],
                    color="light",
                    className="border mb-0 mt-4",
                ),
                html.Details(
                    [
                        html.Summary("View grounding context sent to Cohere", className="fw-semibold mt-4"),
                        html.Pre(
                            summary_context,
                            style={
                                "whiteSpace": "pre-wrap",
                                "marginTop": "12px",
                                "padding": "16px",
                                "backgroundColor": "#f8fafc",
                                "borderRadius": "12px",
                                "border": "1px solid #e2e8f0",
                                "fontSize": "13px",
                                "lineHeight": "1.5",
                            },
                        ),
                    ]
                ),
            ]
        ),
        style=card_style,
    )


def register_ai_summary_callbacks(
    app,
    *,
    daily_metrics,
    filter_transactions,
    empty_state,
    markdown_summary_card,
):
    @app.callback(
        Output("ai-summary-display", "children"),
        Output("ai-summary-loading-indicator", "children"),
        Input("generate-ai-summary-btn", "n_clicks"),
        State("tabs", "value"),
        State("date-range", "start_date"),
        State("date-range", "end_date"),
        State("category-filter", "value"),
        State("merchant-filter", "value"),
        State("view-mode", "value"),
        prevent_initial_call=True,
    )
    def render_ai_summary_content(n_clicks, tab, start_date, end_date, categories, merchants, view_mode):
        if tab != "ai" or not n_clicks:
            return no_update, html.Div()

        df = filter_transactions(start_date, end_date, categories, merchants, view_mode)
        if df.empty:
            return empty_state("No transactions match the current filters."), html.Div()

        filtered_metrics = filter_daily_metrics(daily_metrics, start_date, end_date, categories, merchants, view_mode)
        summary_context, summary_meta = build_summary_context(
            df,
            filtered_metrics,
            start_date,
            end_date,
            categories,
            merchants,
            view_mode,
        )
        filters_payload = {
            "start_date": start_date,
            "end_date": end_date,
            "categories": categories or [],
            "merchants": merchants or [],
            "view_mode": view_mode,
        }
        prompt_context = build_ai_prompt_context(summary_meta)
        summary_text = summarize_spend(prompt_context, filters=filters_payload)

        if summary_text.startswith("Unable to generate Cohere summary right now:"):
            return (
                html.Div(
                    [
                        markdown_summary_card(build_fallback_summary(summary_meta), "Instant summary"),
                        dbc.Alert(
                            [
                                html.Strong("AI summary unavailable. "),
                                summary_text.replace("Unable to generate Cohere summary right now: ", ""),
                            ],
                            color="warning",
                            className="border mb-0",
                        ),
                    ]
                ),
                html.Div(),
            )

        if summary_text.startswith("Cohere API key is not configured"):
            return (
                html.Div(
                    [
                        markdown_summary_card(build_fallback_summary(summary_meta), "Instant summary"),
                        dbc.Alert(summary_text, color="light", className="border mb-0"),
                    ]
                ),
                html.Div(),
            )

        return markdown_summary_card(summary_text, "Cohere-written summary"), html.Div()
