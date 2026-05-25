with debits as (
    select *
    from {{ ref('fct_transactions') }}
    where is_debit
),

totals as (
    select
        count(*) as transaction_count,
        sum(amount_abs) as total_spend
    from debits
),

source_metrics as (
    select
        merchant_source,
        category_source,
        count(*) as transaction_count,
        sum(amount_abs) as total_spend,
        count(distinct raw_description) as unique_raw_descriptions,
        count(distinct normalized_merchant) as unique_normalized_merchants
    from debits
    group by 1, 2
)

select
    source_metrics.merchant_source,
    source_metrics.category_source,
    source_metrics.transaction_count,
    source_metrics.total_spend,
    source_metrics.transaction_count / nullif(totals.transaction_count, 0) as transaction_share,
    source_metrics.total_spend / nullif(totals.total_spend, 0) as spend_share,
    source_metrics.unique_raw_descriptions,
    source_metrics.unique_normalized_merchants
from source_metrics
cross join totals
