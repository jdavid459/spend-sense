with txns as (
    select * from {{ ref('fct_transactions') }}
),

debits as (
    select * from txns where is_debit
),

credits as (
    select * from txns where is_credit
),

base as (
    select
        coalesce(sum(amount_abs), 0) as total_spend,
        count(*) as debit_transaction_count,
        avg(amount_abs) as avg_transaction_amount,
        median(amount_abs) as median_transaction_amount
    from debits
),

credit_summary as (
    select coalesce(sum(amount_abs), 0) as credit_amount
    from credits
),

transaction_summary as (
    select count(*) as transaction_count
    from txns
),

category_spend as (
    select
        final_category,
        sum(amount_abs) as total_spend
    from debits
    group by 1
),

top_category as (
    select
        final_category as top_category,
        total_spend as top_category_spend
    from category_spend
    order by total_spend desc
    limit 1
),

merchant_spend as (
    select
        normalized_merchant,
        sum(amount_abs) as total_spend
    from debits
    group by 1
),

ranked_merchant_spend as (
    select
        normalized_merchant,
        total_spend,
        row_number() over (order by total_spend desc) as merchant_rank
    from merchant_spend
),

top_merchant as (
    select
        normalized_merchant as top_merchant,
        total_spend as top_merchant_spend
    from ranked_merchant_spend
    where merchant_rank = 1
),

top_5_merchants as (
    select coalesce(sum(total_spend), 0) as top_5_merchant_spend
    from ranked_merchant_spend
    where merchant_rank <= 5
),

recurring as (
    select coalesce(sum(estimated_monthly_cost), 0) as estimated_monthly_recurring_spend
    from {{ ref('mart_recurring_spend') }}
),

anomalies as (
    select
        count(*) as anomaly_count,
        coalesce(sum(amount_abs), 0) as anomaly_spend
    from debits
    where is_anomaly
),

source_summary as (
    select
        coalesce(sum(case when merchant_source = 'fallback' then amount_abs else 0 end), 0) as fallback_spend,
        count(case when merchant_source = 'fallback' then 1 end) as fallback_transaction_count,
        coalesce(sum(case when merchant_source = 'cohere_cache' then amount_abs else 0 end), 0) as cohere_spend,
        count(case when merchant_source = 'cohere_cache' then 1 end) as cohere_transaction_count,
        coalesce(sum(case when merchant_source = 'seed_rule' then amount_abs else 0 end), 0) as seed_rule_spend,
        count(case when merchant_source = 'seed_rule' then 1 end) as seed_rule_transaction_count
    from debits
)

select
    base.total_spend,
    credit_summary.credit_amount,
    transaction_summary.transaction_count,
    base.debit_transaction_count,
    base.avg_transaction_amount,
    base.median_transaction_amount,
    top_category.top_category,
    coalesce(top_category.top_category_spend, 0) as top_category_spend,
    coalesce(top_category.top_category_spend, 0) / nullif(base.total_spend, 0) as top_category_spend_share,
    top_merchant.top_merchant,
    coalesce(top_merchant.top_merchant_spend, 0) as top_merchant_spend,
    coalesce(top_merchant.top_merchant_spend, 0) / nullif(base.total_spend, 0) as top_merchant_spend_share,
    top_5_merchants.top_5_merchant_spend,
    top_5_merchants.top_5_merchant_spend / nullif(base.total_spend, 0) as top_5_merchant_spend_share,
    recurring.estimated_monthly_recurring_spend,
    recurring.estimated_monthly_recurring_spend / nullif(base.total_spend, 0) as recurring_spend_share,
    anomalies.anomaly_count,
    anomalies.anomaly_spend,
    anomalies.anomaly_count / nullif(base.debit_transaction_count, 0) as anomaly_transaction_rate,
    anomalies.anomaly_spend / nullif(base.total_spend, 0) as anomaly_spend_share,
    source_summary.fallback_transaction_count,
    source_summary.fallback_spend,
    source_summary.fallback_transaction_count / nullif(base.debit_transaction_count, 0) as fallback_transaction_share,
    source_summary.fallback_spend / nullif(base.total_spend, 0) as fallback_spend_share,
    source_summary.cohere_transaction_count,
    source_summary.cohere_spend,
    source_summary.cohere_transaction_count / nullif(base.debit_transaction_count, 0) as cohere_transaction_share,
    source_summary.cohere_spend / nullif(base.total_spend, 0) as cohere_spend_share,
    source_summary.seed_rule_transaction_count,
    source_summary.seed_rule_spend,
    source_summary.seed_rule_transaction_count / nullif(base.debit_transaction_count, 0) as seed_rule_transaction_share,
    source_summary.seed_rule_spend / nullif(base.total_spend, 0) as seed_rule_spend_share
from base
cross join credit_summary
cross join transaction_summary
cross join top_5_merchants
cross join recurring
cross join anomalies
cross join source_summary
left join top_category on true
left join top_merchant on true
