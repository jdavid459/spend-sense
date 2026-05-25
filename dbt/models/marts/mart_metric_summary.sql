with txns as (
    select *
    from {{ ref('fct_transactions') }}
),

bounds as (
    select
        max(transaction_date)::date as as_of_date,
        (max(transaction_date)::date - interval '29 days')::date as current_period_start,
        (max(transaction_date)::date - interval '30 days')::date as comparison_period_end,
        (max(transaction_date)::date - interval '59 days')::date as comparison_period_start
    from txns
),

period_txns as (
    select
        case
            when txns.transaction_date::date between bounds.current_period_start and bounds.as_of_date then 'current'
            when txns.transaction_date::date between bounds.comparison_period_start and bounds.comparison_period_end then 'comparison'
        end as period_name,
        txns.*
    from txns
    cross join bounds
    where txns.transaction_date::date between bounds.comparison_period_start and bounds.as_of_date
),

debits as (
    select *
    from period_txns
    where is_debit and period_name is not null
),

period_base as (
    select
        period_name,
        sum(amount_abs) as total_spend,
        count(*) as debit_transaction_count,
        avg(amount_abs) as avg_transaction_amount,
        median(amount_abs) as median_transaction_amount,
        stddev_samp(amount_abs) / nullif(avg(amount_abs), 0) as transaction_amount_volatility,
        count(case when is_anomaly then 1 end) as anomaly_count,
        sum(case when is_anomaly then amount_abs else 0 end) as anomaly_spend,
        sum(case when is_recurring then amount_abs else 0 end) as recurring_spend,
        sum(case when merchant_source = 'fallback' then amount_abs else 0 end) as fallback_spend,
        sum(case when merchant_source = 'cohere_cache' then amount_abs else 0 end) as cohere_spend,
        sum(case when merchant_source = 'seed_rule' then amount_abs else 0 end) as seed_rule_spend
    from debits
    group by 1
),

category_spend as (
    select
        period_name,
        final_category,
        sum(amount_abs) as spend
    from debits
    group by 1, 2
),

top_category as (
    select
        period_name,
        final_category,
        spend,
        row_number() over (partition by period_name order by spend desc) as category_rank
    from category_spend
),

merchant_spend as (
    select
        period_name,
        normalized_merchant,
        sum(amount_abs) as spend
    from debits
    group by 1, 2
),

ranked_merchant_spend as (
    select
        period_name,
        normalized_merchant,
        spend,
        row_number() over (partition by period_name order by spend desc) as merchant_rank
    from merchant_spend
),

top_merchant as (
    select
        period_name,
        normalized_merchant,
        spend
    from ranked_merchant_spend
    where merchant_rank = 1
),

top_5_merchants as (
    select
        period_name,
        sum(spend) as spend
    from ranked_merchant_spend
    where merchant_rank <= 5
    group by 1
),

period_metrics as (
    select
        period_base.period_name,
        'total_spend' as metric_key,
        'Total Spend' as metric_label,
        'Spend' as metric_group,
        period_base.total_spend as metric_value,
        'currency' as unit,
        'lower' as favorable_direction,
        'Debit spend in the period. Payments and credits are excluded.' as definition
    from period_base

    union all

    select
        period_name,
        'debit_transaction_count',
        'Debit Transactions',
        'Spend',
        debit_transaction_count,
        'count',
        'neutral',
        'Count of debit transactions in the period.'
    from period_base

    union all

    select
        period_name,
        'avg_transaction_amount',
        'Average Transaction',
        'Spend',
        avg_transaction_amount,
        'currency',
        'lower',
        'Average debit transaction amount in the period.'
    from period_base

    union all

    select
        period_name,
        'median_transaction_amount',
        'Median Transaction',
        'Spend',
        median_transaction_amount,
        'currency',
        'lower',
        'Median debit transaction amount in the period.'
    from period_base

    union all

    select
        period_base.period_name,
        'top_category_share',
        'Top Category Share',
        'Concentration',
        top_category.spend / nullif(period_base.total_spend, 0),
        'percent',
        'lower',
        'Largest category spend divided by total debit spend.'
    from period_base
    left join top_category
        on period_base.period_name = top_category.period_name
        and top_category.category_rank = 1

    union all

    select
        period_base.period_name,
        'top_merchant_share',
        'Top Merchant Share',
        'Concentration',
        top_merchant.spend / nullif(period_base.total_spend, 0),
        'percent',
        'lower',
        'Largest merchant spend divided by total debit spend.'
    from period_base
    left join top_merchant using (period_name)

    union all

    select
        period_base.period_name,
        'top_5_merchant_share',
        'Top 5 Merchant Share',
        'Concentration',
        top_5_merchants.spend / nullif(period_base.total_spend, 0),
        'percent',
        'lower',
        'Top five merchants by spend divided by total debit spend.'
    from period_base
    left join top_5_merchants using (period_name)

    union all

    select
        period_name,
        'recurring_spend_share',
        'Recurring Spend Share',
        'Behavior',
        recurring_spend / nullif(total_spend, 0),
        'percent',
        'lower',
        'Debit spend marked as recurring divided by total debit spend.'
    from period_base

    union all

    select
        period_name,
        'anomaly_spend_share',
        'Anomaly Spend Share',
        'Risk',
        anomaly_spend / nullif(total_spend, 0),
        'percent',
        'lower',
        'Anomalous debit spend divided by total debit spend.'
    from period_base

    union all

    select
        period_name,
        'fallback_spend_share',
        'Fallback Spend Share',
        'Data Quality',
        fallback_spend / nullif(total_spend, 0),
        'percent',
        'lower',
        'Debit spend using raw fallback merchant normalization divided by total debit spend.'
    from period_base

    union all

    select
        period_name,
        'cohere_spend_share',
        'Cohere-Enriched Share',
        'Data Quality',
        cohere_spend / nullif(total_spend, 0),
        'percent',
        'neutral',
        'Debit spend with merchant/category values supplied by the Cohere enrichment cache.'
    from period_base

    union all

    select
        period_name,
        'seed_rule_spend_share',
        'Seed Rule Share',
        'Data Quality',
        seed_rule_spend / nullif(total_spend, 0),
        'percent',
        'higher',
        'Debit spend covered by deterministic merchant seed rules.'
    from period_base

    union all

    select
        period_name,
        'transaction_amount_volatility',
        'Transaction Volatility',
        'Volatility',
        transaction_amount_volatility,
        'percent',
        'lower',
        'Standard deviation of debit transaction amount divided by average debit transaction amount.'
    from period_base
),

current_metrics as (
    select *
    from period_metrics
    where period_name = 'current'
),

comparison_metrics as (
    select *
    from period_metrics
    where period_name = 'comparison'
)

select
    bounds.as_of_date,
    bounds.current_period_start,
    bounds.as_of_date as current_period_end,
    bounds.comparison_period_start,
    bounds.comparison_period_end,
    current_metrics.metric_key,
    current_metrics.metric_label,
    current_metrics.metric_group,
    current_metrics.metric_value,
    comparison_metrics.metric_value as comparison_value,
    current_metrics.metric_value - comparison_metrics.metric_value as delta_value,
    case
        when abs(comparison_metrics.metric_value) > 0
            then current_metrics.metric_value / comparison_metrics.metric_value - 1
        else null
    end as delta_pct,
    current_metrics.unit,
    current_metrics.favorable_direction,
    current_metrics.definition
from current_metrics
left join comparison_metrics using (metric_key)
cross join bounds
