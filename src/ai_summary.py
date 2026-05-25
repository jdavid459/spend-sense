from __future__ import annotations

from typing import Any

import pandas as pd


def format_money(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "$0.00"
    return f"${value:,.2f}"


def format_pct(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{value:.1%}"


def format_signed_money(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "$0.00"
    if value < 0:
        return f"-${abs(value):,.2f}"
    if value > 0:
        return f"+${value:,.2f}"
    return "$0.00"


def format_date(value: Any) -> str:
    if value is None or pd.isna(value):
        return "—"
    return pd.to_datetime(value).strftime("%b %d, %Y").replace(" 0", " ")


def _series_or_empty(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(dtype="object")
    return df[column]


def _window_slice(df: pd.DataFrame, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
    return df[(df["transaction_date"] >= start_date) & (df["transaction_date"] <= end_date)].copy()


def _change_table(
    df: pd.DataFrame,
    dimension: str,
    current_start: pd.Timestamp,
    current_end: pd.Timestamp,
    prior_start: pd.Timestamp,
    prior_end: pd.Timestamp,
) -> pd.DataFrame:
    current = (
        _window_slice(df, current_start, current_end)
        .groupby(dimension, dropna=False, as_index=False)["amount_abs"]
        .sum()
        .rename(columns={"amount_abs": "current_spend"})
    )
    prior = (
        _window_slice(df, prior_start, prior_end)
        .groupby(dimension, dropna=False, as_index=False)["amount_abs"]
        .sum()
        .rename(columns={"amount_abs": "prior_spend"})
    )
    changes = current.merge(prior, on=dimension, how="outer").fillna(0)
    changes[dimension] = changes[dimension].fillna("Unknown")
    changes["delta_amount"] = changes["current_spend"] - changes["prior_spend"]
    changes["delta_pct"] = changes["delta_amount"] / changes["prior_spend"].replace({0: pd.NA})
    return changes.sort_values(["delta_amount", "current_spend"], ascending=[False, False])


def _top_change_text(changes: pd.DataFrame, dimension: str) -> tuple[str, str, float | None]:
    non_zero = changes[changes["delta_amount"] != 0].copy()
    if non_zero.empty:
        return "No change", "No material change versus the prior 30 days.", None

    non_zero["abs_delta_amount"] = non_zero["delta_amount"].abs()
    row = non_zero.sort_values(["abs_delta_amount", "current_spend"], ascending=[False, False]).iloc[0]
    label = str(row[dimension])
    delta_amount = float(row["delta_amount"])
    direction = "up" if delta_amount > 0 else "down"
    subtitle = (
        f"{label} {direction} {format_money(abs(delta_amount))} vs prior 30d "
        f"({format_money(row['current_spend'])} current)"
    )
    return label, subtitle, delta_amount


def _directional_change_text(
    changes: pd.DataFrame,
    dimension: str,
    direction: str,
) -> tuple[str, str, float | None]:
    if direction == "up":
        directional = changes[changes["delta_amount"] > 0].copy()
    else:
        directional = changes[changes["delta_amount"] < 0].copy()

    if directional.empty:
        return "No change", f"No category moved {direction} versus the prior 30 days.", None

    if direction == "up":
        row = directional.sort_values(["delta_amount", "current_spend"], ascending=[False, False]).iloc[0]
    else:
        row = directional.sort_values(["delta_amount", "current_spend"], ascending=[True, False]).iloc[0]

    label = str(row[dimension])
    delta_amount = float(row["delta_amount"])
    subtitle = (
        f"{label} {direction} {format_money(abs(delta_amount))} vs prior 30d "
        f"({format_money(row['current_spend'])} current)"
    )
    return label, subtitle, delta_amount


def _largest_anomaly_text(anomalies: pd.DataFrame) -> tuple[str, str]:
    if anomalies.empty:
        return "No major anomaly", "No anomalies in the current selection."

    row = anomalies.sort_values("amount_abs", ascending=False).iloc[0]
    return str(row["normalized_merchant"]), f"{format_money(row['amount_abs'])} · {row['anomaly_reason']}"


def filter_daily_metrics(
    daily_metrics: pd.DataFrame,
    start_date: str | None,
    end_date: str | None,
    categories: list[str] | None,
    merchants: list[str] | None,
    view_mode: str,
) -> pd.DataFrame:
    if daily_metrics.empty:
        return daily_metrics.copy()

    metrics = daily_metrics.copy()
    if start_date:
        metrics = metrics[metrics["metric_date"] >= pd.to_datetime(start_date)]
    if end_date:
        metrics = metrics[metrics["metric_date"] <= pd.to_datetime(end_date)]
    if categories:
        metrics = metrics[metrics["final_category"].isin(categories)]
    if merchants:
        metrics = metrics[metrics["normalized_merchant"].isin(merchants)]
    if view_mode == "debits":
        metrics = metrics[~metrics["metric_key"].str.startswith("credit_")]
    elif view_mode == "credits":
        metrics = metrics[metrics["metric_key"].str.startswith("credit_")]
    elif view_mode == "anomalies":
        metrics = metrics[metrics["metric_key"].str.startswith("anomaly_")]
    elif view_mode == "recurring":
        metrics = metrics[metrics["metric_key"].str.startswith("recurring_")]

    return metrics


def build_fallback_summary(summary_meta: dict[str, Any]) -> str:
    return "\n".join(
        [
            "## What changed",
            (
                f"- Rolling 30-day spend is {format_money(summary_meta['current_window_spend'])}, "
                f"with a change of {format_signed_money(summary_meta['current_30d_total_spend_delta'])} "
                f"vs the prior 30 days ({format_pct(summary_meta['current_30d_total_spend_delta_pct'])})."
            ),
            f"- Biggest category mover: {summary_meta['recent_category_text']}",
            f"- Biggest merchant mover: {summary_meta['recent_merchant_text']}",
            f"- Largest category decline: {summary_meta['largest_decline_category_text']}",
            "",
            "## What's notable",
            (
                f"- Recurring spend in the latest 30-day window is "
                f"{format_money(summary_meta['current_window_recurring_spend'])}."
            ),
            (
                f"- Anomaly spend in the current selection is {format_money(summary_meta['selected_anomaly_spend'])} "
                f"({format_pct(summary_meta['selected_anomaly_share'])} of debit spend)."
            ),
            f"- Watch item: {summary_meta['summary_card_3_value']} — {summary_meta['summary_card_3_subtitle']}",
            "",
            "## What to review",
            (
                f"- Fallback merchant coverage is {format_pct(summary_meta['selected_fallback_share'])} "
                f"of selected debit spend."
            ),
            (
                f"- If you are investigating recent change, start with "
                f"{summary_meta['recent_category_label']} and {summary_meta['recent_merchant_label']}."
            ),
        ]
    )


def build_ai_prompt_context(summary_meta: dict[str, Any]) -> str:
    return "\n".join(
        [
            "Summary cues",
            f"- Selected window: {summary_meta['selected_start']} to {summary_meta['selected_end']}",
            f"- Selected debit spend: {format_money(summary_meta['selected_total_spend'])}",
            f"- Debit transactions: {summary_meta['selected_debit_count']:,}",
            (
                f"- Rolling 30-day spend: {format_money(summary_meta['current_window_spend'])}, "
                f"delta {format_signed_money(summary_meta['current_30d_total_spend_delta'])} "
                f"({format_pct(summary_meta['current_30d_total_spend_delta_pct'])})"
            ),
            f"- Primary category shift: {summary_meta['recent_category_text']}",
            f"- Primary merchant shift: {summary_meta['recent_merchant_text']}",
            f"- Largest category decline: {summary_meta['largest_decline_category_text']}",
            (
                f"- Recurring spend in latest 30d: "
                f"{format_money(summary_meta['current_window_recurring_spend'])}"
            ),
            (
                f"- Anomaly spend in selected window: {format_money(summary_meta['selected_anomaly_spend'])} "
                f"({format_pct(summary_meta['selected_anomaly_share'])} of debit spend)"
            ),
            f"- Watch item: {summary_meta['summary_card_3_value']} — {summary_meta['summary_card_3_subtitle']}",
            (
                f"- Fallback merchant coverage: {format_pct(summary_meta['selected_fallback_share'])} "
                "of selected debit spend"
            ),
        ]
    )


def build_summary_context(
    transactions: pd.DataFrame,
    filtered_metrics: pd.DataFrame,
    start_date: str | None,
    end_date: str | None,
    categories: list[str] | None,
    merchants: list[str] | None,
    view_mode: str,
) -> tuple[str, dict[str, Any]]:
    df = transactions.copy()
    debits = df[df["is_debit"]].copy() if "is_debit" in df.columns else pd.DataFrame()
    credits = df[df["is_credit"]].copy() if "is_credit" in df.columns else pd.DataFrame()

    selected_total_spend = float(debits["amount_abs"].sum()) if not debits.empty else 0.0
    selected_credit_amount = float(credits["amount_abs"].sum()) if not credits.empty else 0.0
    selected_debit_count = int(debits.shape[0])
    selected_credit_count = int(credits.shape[0])
    selected_transaction_count = int(df.shape[0])
    selected_avg_debit = float(debits["amount_abs"].mean()) if not debits.empty else None

    recurring_txns = debits[debits["is_recurring"]].copy() if "is_recurring" in debits.columns else pd.DataFrame()
    anomaly_txns = debits[debits["is_anomaly"]].copy() if "is_anomaly" in debits.columns else pd.DataFrame()

    selected_recurring_spend = float(recurring_txns["amount_abs"].sum()) if not recurring_txns.empty else 0.0
    selected_anomaly_spend = float(anomaly_txns["amount_abs"].sum()) if not anomaly_txns.empty else 0.0
    selected_anomaly_count = int(anomaly_txns.shape[0])

    fallback_spend = (
        float(debits.loc[debits["merchant_source"] == "fallback", "amount_abs"].sum()) if not debits.empty else 0.0
    )
    cohere_spend = (
        float(debits.loc[debits["merchant_source"] == "cohere_cache", "amount_abs"].sum())
        if not debits.empty
        else 0.0
    )
    seed_rule_spend = (
        float(debits.loc[debits["merchant_source"] == "seed_rule", "amount_abs"].sum()) if not debits.empty else 0.0
    )

    def spend_share(value: float) -> float | None:
        if selected_total_spend == 0:
            return None
        return value / selected_total_spend

    metric_lookup: dict[str, dict[str, Any]] = {}
    latest_metric_date = None
    if not filtered_metrics.empty:
        latest_metric_date = filtered_metrics["metric_date"].max()
        metric_rollups = (
            filtered_metrics[filtered_metrics["metric_date"] == latest_metric_date]
            .groupby(["metric_key", "metric_name", "metric_group", "unit"], as_index=False)[
                ["metric_value_l30d", "metric_value_prior_l30d"]
            ]
            .sum()
        )
        metric_rollups["delta_value"] = metric_rollups["metric_value_l30d"] - metric_rollups["metric_value_prior_l30d"]
        metric_rollups["delta_pct"] = metric_rollups["delta_value"] / metric_rollups["metric_value_prior_l30d"].replace(
            {0: pd.NA}
        )
        metric_lookup = metric_rollups.set_index("metric_key").to_dict("index")

    def metric_value(metric_key: str, field: str) -> float | None:
        row = metric_lookup.get(metric_key)
        if not row:
            return None
        value = row.get(field)
        if value is None or pd.isna(value):
            return None
        return float(value)

    top_categories = (
        debits.groupby("final_category")["amount_abs"].sum().sort_values(ascending=False).head(5)
        if not debits.empty
        else pd.Series(dtype=float)
    )
    recurring_merchants = (
        recurring_txns.groupby(["normalized_merchant", "final_category"], as_index=False)
        .agg(amount_abs=("amount_abs", "sum"), transaction_count=("transaction_id", "count"))
        .sort_values(["amount_abs", "transaction_count"], ascending=False)
        .head(5)
        if not recurring_txns.empty
        else pd.DataFrame()
    )

    category_filter = ", ".join(categories) if categories else "All categories"
    merchant_filter = ", ".join(merchants) if merchants else "All merchants"
    observed_start = format_date(_series_or_empty(df, "transaction_date").min()) if not df.empty else "—"
    observed_end = format_date(_series_or_empty(df, "transaction_date").max()) if not df.empty else "—"
    selected_start = format_date(start_date) if start_date else observed_start
    selected_end = format_date(end_date) if end_date else observed_end

    current_window_end = pd.to_datetime(latest_metric_date or _series_or_empty(debits, "transaction_date").max())
    current_window_start = current_window_end - pd.Timedelta(days=29) if not pd.isna(current_window_end) else None
    prior_window_end = current_window_start - pd.Timedelta(days=1) if current_window_start is not None else None
    prior_window_start = prior_window_end - pd.Timedelta(days=29) if prior_window_end is not None else None

    current_window = (
        _window_slice(debits, current_window_start, current_window_end)
        if current_window_start is not None and current_window_end is not None and not debits.empty
        else pd.DataFrame()
    )
    prior_window = (
        _window_slice(debits, prior_window_start, prior_window_end)
        if prior_window_start is not None and prior_window_end is not None and not debits.empty
        else pd.DataFrame()
    )

    category_changes = (
        _change_table(
            debits,
            "final_category",
            current_window_start,
            current_window_end,
            prior_window_start,
            prior_window_end,
        )
        if current_window_start is not None and prior_window_start is not None and not debits.empty
        else pd.DataFrame()
    )
    merchant_changes = (
        _change_table(
            debits,
            "normalized_merchant",
            current_window_start,
            current_window_end,
            prior_window_start,
            prior_window_end,
        )
        if current_window_start is not None and prior_window_start is not None and not debits.empty
        else pd.DataFrame()
    )

    top_category_label, top_category_change_text, top_category_delta = _top_change_text(
        category_changes,
        "final_category",
    )
    top_merchant_label, top_merchant_change_text, top_merchant_delta = _top_change_text(
        merchant_changes,
        "normalized_merchant",
    )
    primary_category_label, primary_category_change_text, primary_category_delta = _directional_change_text(
        category_changes,
        "final_category",
        "up",
    )
    primary_merchant_label, primary_merchant_change_text, primary_merchant_delta = _directional_change_text(
        merchant_changes,
        "normalized_merchant",
        "up",
    )
    decline_category_label, decline_category_change_text, decline_category_delta = _directional_change_text(
        category_changes,
        "final_category",
        "down",
    )
    if primary_category_delta is None:
        primary_category_label = top_category_label
        primary_category_change_text = top_category_change_text
        primary_category_delta = top_category_delta
    if primary_merchant_delta is None:
        primary_merchant_label = top_merchant_label
        primary_merchant_change_text = top_merchant_change_text
        primary_merchant_delta = top_merchant_delta
    top_anomaly_label, top_anomaly_text = _largest_anomaly_text(anomaly_txns)

    current_window_recurring = (
        current_window[current_window["is_recurring"]].copy() if not current_window.empty else pd.DataFrame()
    )
    current_window_anomalies = (
        current_window[current_window["is_anomaly"]].copy() if not current_window.empty else pd.DataFrame()
    )

    current_window_spend = float(current_window["amount_abs"].sum()) if not current_window.empty else 0.0
    prior_window_spend = float(prior_window["amount_abs"].sum()) if not prior_window.empty else 0.0
    current_window_recurring_spend = (
        float(current_window_recurring["amount_abs"].sum()) if not current_window_recurring.empty else 0.0
    )
    current_window_anomaly_spend = (
        float(current_window_anomalies["amount_abs"].sum()) if not current_window_anomalies.empty else 0.0
    )
    current_window_fallback_spend = (
        float(current_window.loc[current_window["merchant_source"] == "fallback", "amount_abs"].sum())
        if not current_window.empty
        else 0.0
    )

    recurring_line = (
        f"- Recurring spend: {format_money(selected_recurring_spend)} "
        f"({format_pct(spend_share(selected_recurring_spend))} of debit spend)"
    )
    anomaly_line = (
        f"- Anomaly spend: {format_money(selected_anomaly_spend)} across {selected_anomaly_count:,} "
        f"transactions ({format_pct(spend_share(selected_anomaly_spend))} of debit spend)"
    )
    coverage_line = (
        "- Merchant source coverage: "
        f"seed_rule={format_money(seed_rule_spend)} ({format_pct(spend_share(seed_rule_spend))}), "
        f"cohere_cache={format_money(cohere_spend)} ({format_pct(spend_share(cohere_spend))}), "
        f"fallback={format_money(fallback_spend)} ({format_pct(spend_share(fallback_spend))})"
    )

    context_lines = [
        "Summary scope",
        f"- View mode: {view_mode}",
        f"- Selected date window: {selected_start} to {selected_end}",
        f"- Observed transaction window after filters: {observed_start} to {observed_end}",
        f"- Category filter: {category_filter}",
        f"- Merchant filter: {merchant_filter}",
        "",
        "Selected-window metrics from marts.fct_transactions",
        f"- Total debit spend: {format_money(selected_total_spend)}",
        f"- Credit amount: {format_money(selected_credit_amount)}",
        f"- Total transactions: {selected_transaction_count:,}",
        f"- Debit transactions: {selected_debit_count:,}",
        f"- Credit transactions: {selected_credit_count:,}",
        f"- Average debit transaction: {format_money(selected_avg_debit)}",
        recurring_line,
        anomaly_line,
        coverage_line,
        "",
    ]

    if latest_metric_date is not None:
        total_spend_l30d = metric_value("total_spend", "metric_value_l30d")
        total_spend_prior_l30d = metric_value("total_spend", "metric_value_prior_l30d")
        total_spend_delta = metric_value("total_spend", "delta_value")
        total_spend_delta_pct = metric_value("total_spend", "delta_pct")
        recurring_spend_l30d = metric_value("recurring_spend", "metric_value_l30d")
        anomaly_spend_l30d = metric_value("anomaly_spend", "metric_value_l30d")
        fallback_spend_l30d = metric_value("fallback_spend", "metric_value_l30d")
        cohere_spend_l30d = metric_value("cohere_spend", "metric_value_l30d")

        def rolling_share(value: float | None) -> float | None:
            if value is None or total_spend_l30d in (None, 0):
                return None
            return value / total_spend_l30d

        context_lines += [
            (
                f"Latest rolling 30-day window: {format_date(current_window_start)} to "
                f"{format_date(current_window_end)}"
            ),
            (
                f"Prior rolling 30-day window: {format_date(prior_window_start)} to "
                f"{format_date(prior_window_end)}"
            ),
            (
                f"- Total spend: {format_money(total_spend_l30d)} vs prior 30d "
                f"{format_money(total_spend_prior_l30d)}"
            ),
            (
                f"- Total spend delta vs prior 30d: {format_money(total_spend_delta)} "
                f"({format_pct(total_spend_delta_pct)})"
            ),
            (
                f"- Recurring spend: {format_money(recurring_spend_l30d)} "
                f"({format_pct(rolling_share(recurring_spend_l30d))} of total spend)"
            ),
            (
                f"- Anomaly spend: {format_money(anomaly_spend_l30d)} "
                f"({format_pct(rolling_share(anomaly_spend_l30d))} of total spend)"
            ),
            (
                f"- Fallback spend: {format_money(fallback_spend_l30d)} "
                f"({format_pct(rolling_share(fallback_spend_l30d))} of total spend)"
            ),
            (
                f"- Cohere-enriched spend: {format_money(cohere_spend_l30d)} "
                f"({format_pct(rolling_share(cohere_spend_l30d))} of total spend)"
            ),
            "",
        ]
    else:
        context_lines += ["Rolling 30-day metrics", "- No daily metric rollups match the current filters.", ""]

    context_lines += [
        "Primary summary cues",
        f"- Primary category shift for the summary card: {primary_category_change_text}",
        f"- Primary merchant shift for the summary card: {primary_merchant_change_text}",
        f"- Largest category decline: {decline_category_change_text}",
        f"- Watch item for the summary card: {top_anomaly_label} | {top_anomaly_text}",
        "",
    ]

    context_lines.append("Biggest recent changes by category")
    if category_changes.empty:
        context_lines.append("- No recent category comparison is available.")
    else:
        for row in category_changes.head(5).itertuples(index=False):
            context_lines.append(
                f"- {row.final_category}: current {format_money(row.current_spend)}, "
                f"prior {format_money(row.prior_spend)}, delta {format_money(row.delta_amount)}"
            )
    context_lines.append("")

    context_lines.append("Biggest recent changes by merchant")
    if merchant_changes.empty:
        context_lines.append("- No recent merchant comparison is available.")
    else:
        for row in merchant_changes.head(5).itertuples(index=False):
            context_lines.append(
                f"- {row.normalized_merchant}: current {format_money(row.current_spend)}, "
                f"prior {format_money(row.prior_spend)}, delta {format_money(row.delta_amount)}"
            )
    context_lines.append("")

    context_lines.append("Top categories in selected window")
    if top_categories.empty:
        context_lines.append("- No debit categories in the current filters.")
    else:
        for category, value in top_categories.items():
            context_lines.append(f"- {category}: {format_money(value)} ({format_pct(spend_share(float(value)))})")
    context_lines.append("")

    context_lines.append("Largest anomalies in selected window")
    if anomaly_txns.empty:
        context_lines.append("- No anomalies in the current filters.")
    else:
        for row in anomaly_txns.sort_values("amount_abs", ascending=False).head(5).itertuples(index=False):
            context_lines.append(
                f"- {row.transaction_date.strftime('%Y-%m-%d')} | {row.normalized_merchant} | "
                f"{format_money(row.amount_abs)} | {row.anomaly_reason}"
            )
    context_lines.append("")

    context_lines.append("Recurring merchants in selected window")
    if recurring_merchants.empty:
        context_lines.append("- No recurring merchants in the current filters.")
    else:
        for row in recurring_merchants.itertuples(index=False):
            context_lines.append(
                f"- {row.normalized_merchant} | {row.final_category} | "
                f"{format_money(row.amount_abs)} across {int(row.transaction_count):,} transactions"
            )

    metadata = {
        "selected_total_spend": selected_total_spend,
        "selected_debit_count": selected_debit_count,
        "selected_recurring_spend": selected_recurring_spend,
        "selected_anomaly_spend": selected_anomaly_spend,
        "selected_anomaly_share": spend_share(selected_anomaly_spend),
        "selected_fallback_share": spend_share(fallback_spend),
        "current_30d_total_spend": metric_value("total_spend", "metric_value_l30d"),
        "current_30d_total_spend_delta": metric_value("total_spend", "delta_value"),
        "current_30d_total_spend_delta_pct": metric_value("total_spend", "delta_pct"),
        "summary_card_1_title": "30D Trend",
        "summary_card_1_value": format_money(current_window_spend),
        "summary_card_1_subtitle": (
            f"{format_signed_money(metric_value('total_spend', 'delta_value'))} vs prior 30d "
            f"({format_pct(metric_value('total_spend', 'delta_pct'))})"
        ),
        "summary_card_2_title": "Recent Driver",
        "summary_card_2_value": primary_category_label,
        "summary_card_2_subtitle": primary_category_change_text,
        "summary_card_3_title": "Watch Item",
        "summary_card_3_value": top_anomaly_label,
        "summary_card_3_subtitle": top_anomaly_text,
        "latest_metric_date": latest_metric_date,
        "recent_category_delta": primary_category_delta,
        "recent_merchant_delta": primary_merchant_delta,
        "recent_category_label": primary_category_label,
        "recent_merchant_label": primary_merchant_label,
        "recent_category_text": primary_category_change_text,
        "recent_merchant_text": primary_merchant_change_text,
        "largest_decline_category_label": decline_category_label,
        "largest_decline_category_text": decline_category_change_text,
        "largest_decline_category_delta": decline_category_delta,
        "current_window_spend": current_window_spend,
        "prior_window_spend": prior_window_spend,
        "current_window_recurring_spend": current_window_recurring_spend,
        "current_window_anomaly_spend": current_window_anomaly_spend,
        "current_window_fallback_spend": current_window_fallback_spend,
        "selected_start": selected_start,
        "selected_end": selected_end,
    }

    return "\n".join(context_lines), metadata
