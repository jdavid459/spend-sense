with txns as (
    select *
    from {{ ref('fct_transactions') }}
),

bounds as (
    select
        min(transaction_date)::date as min_date,
        max(transaction_date)::date as max_date
    from txns
),

date_spine as (
    select date_value::date as metric_date
    from bounds,
        generate_series(bounds.min_date, bounds.max_date, interval '1 day') as dates(date_value)
),

metric_events as (
    select
        transaction_date::date as metric_date,
        final_category,
        normalized_merchant,
        merchant_source,
        category_source,
        'total_spend' as metric_key,
        'Total Spend' as metric_name,
        'Spend' as metric_group,
        'currency' as unit,
        amount_abs as metric_value
    from txns
    where is_debit

    union all

    select
        transaction_date::date,
        final_category,
        normalized_merchant,
        merchant_source,
        category_source,
        'debit_transaction_count',
        'Debit Transactions',
        'Spend',
        'count',
        1.0
    from txns
    where is_debit

    union all

    select
        transaction_date::date,
        final_category,
        normalized_merchant,
        merchant_source,
        category_source,
        'credit_amount',
        'Credit Amount',
        'Credits',
        'currency',
        amount_abs
    from txns
    where is_credit

    union all

    select
        transaction_date::date,
        final_category,
        normalized_merchant,
        merchant_source,
        category_source,
        'credit_transaction_count',
        'Credit Transactions',
        'Credits',
        'count',
        1.0
    from txns
    where is_credit

    union all

    select
        transaction_date::date,
        final_category,
        normalized_merchant,
        merchant_source,
        category_source,
        'anomaly_spend',
        'Anomaly Spend',
        'Risk',
        'currency',
        amount_abs
    from txns
    where is_debit and is_anomaly

    union all

    select
        transaction_date::date,
        final_category,
        normalized_merchant,
        merchant_source,
        category_source,
        'anomaly_transaction_count',
        'Anomaly Transactions',
        'Risk',
        'count',
        1.0
    from txns
    where is_debit and is_anomaly

    union all

    select
        transaction_date::date,
        final_category,
        normalized_merchant,
        merchant_source,
        category_source,
        'recurring_spend',
        'Recurring Spend',
        'Behavior',
        'currency',
        amount_abs
    from txns
    where is_debit and is_recurring

    union all

    select
        transaction_date::date,
        final_category,
        normalized_merchant,
        merchant_source,
        category_source,
        'recurring_transaction_count',
        'Recurring Transactions',
        'Behavior',
        'count',
        1.0
    from txns
    where is_debit and is_recurring

    union all

    select
        transaction_date::date,
        final_category,
        normalized_merchant,
        merchant_source,
        category_source,
        'fallback_spend',
        'Fallback Spend',
        'Data Quality',
        'currency',
        amount_abs
    from txns
    where is_debit and merchant_source = 'fallback'

    union all

    select
        transaction_date::date,
        final_category,
        normalized_merchant,
        merchant_source,
        category_source,
        'fallback_transaction_count',
        'Fallback Transactions',
        'Data Quality',
        'count',
        1.0
    from txns
    where is_debit and merchant_source = 'fallback'

    union all

    select
        transaction_date::date,
        final_category,
        normalized_merchant,
        merchant_source,
        category_source,
        'cohere_spend',
        'Cohere-Enriched Spend',
        'Data Quality',
        'currency',
        amount_abs
    from txns
    where is_debit and merchant_source = 'cohere_cache'

    union all

    select
        transaction_date::date,
        final_category,
        normalized_merchant,
        merchant_source,
        category_source,
        'cohere_transaction_count',
        'Cohere-Enriched Transactions',
        'Data Quality',
        'count',
        1.0
    from txns
    where is_debit and merchant_source = 'cohere_cache'

    union all

    select
        transaction_date::date,
        final_category,
        normalized_merchant,
        merchant_source,
        category_source,
        'seed_rule_spend',
        'Seed Rule Spend',
        'Data Quality',
        'currency',
        amount_abs
    from txns
    where is_debit and merchant_source = 'seed_rule'

    union all

    select
        transaction_date::date,
        final_category,
        normalized_merchant,
        merchant_source,
        category_source,
        'seed_rule_transaction_count',
        'Seed Rule Transactions',
        'Data Quality',
        'count',
        1.0
    from txns
    where is_debit and merchant_source = 'seed_rule'
),

daily_values as (
    select
        metric_date,
        final_category,
        normalized_merchant,
        merchant_source,
        category_source,
        metric_key,
        metric_name,
        metric_group,
        unit,
        sum(metric_value) as metric_value
    from metric_events
    group by 1, 2, 3, 4, 5, 6, 7, 8, 9
),

metric_dimension_combinations as (
    select distinct
        final_category,
        normalized_merchant,
        merchant_source,
        category_source,
        metric_key,
        metric_name,
        metric_group,
        unit
    from daily_values
),

dense_daily_values as (
    select
        date_spine.metric_date,
        metric_dimension_combinations.final_category,
        metric_dimension_combinations.normalized_merchant,
        metric_dimension_combinations.merchant_source,
        metric_dimension_combinations.category_source,
        metric_dimension_combinations.metric_key,
        metric_dimension_combinations.metric_name,
        metric_dimension_combinations.metric_group,
        metric_dimension_combinations.unit,
        coalesce(daily_values.metric_value, 0) as metric_value
    from date_spine
    cross join metric_dimension_combinations
    left join daily_values
        on date_spine.metric_date = daily_values.metric_date
        and metric_dimension_combinations.final_category = daily_values.final_category
        and metric_dimension_combinations.normalized_merchant = daily_values.normalized_merchant
        and metric_dimension_combinations.merchant_source = daily_values.merchant_source
        and metric_dimension_combinations.category_source = daily_values.category_source
        and metric_dimension_combinations.metric_key = daily_values.metric_key
),

rolling_values as (
    select
        *,
        sum(metric_value) over (
            partition by
                final_category,
                normalized_merchant,
                merchant_source,
                category_source,
                metric_key
            order by metric_date
            rows between 29 preceding and current row
        ) as metric_value_l30d
    from dense_daily_values
)

select
    metric_date,
    metric_key,
    metric_name,
    metric_group,
    final_category,
    normalized_merchant,
    merchant_source,
    category_source,
    metric_value,
    metric_value_l30d,
    lag(metric_value_l30d, 30) over (
        partition by
            final_category,
            normalized_merchant,
            merchant_source,
            category_source,
            metric_key
        order by metric_date
    ) as metric_value_prior_l30d,
    unit
from rolling_values
