with txns as (
    select * from {{ ref('stg_chase_transactions') }}
),

merchants as (
    select * from {{ ref('int_merchant_normalization') }}
),

enriched as (
    select
        txns.*,
        merchants.normalized_merchant,
        merchants.merchant_group,
        merchants.merchant_source,
        merchants.category_source,
        merchants.ai_category,
        merchants.ai_confidence,
        merchants.ai_reasoning,
        coalesce(merchants.rule_category, merchants.ai_category, txns.raw_category, 'Other') as final_category
    from txns
    left join merchants using (transaction_id)
),

features as (
    select
        *,
        avg(amount_abs) over (partition by normalized_merchant) as merchant_avg_amount,
        stddev_samp(amount_abs) over (partition by normalized_merchant) as merchant_std_amount,
        avg(amount_abs) over (partition by final_category) as category_avg_amount,
        stddev_samp(amount_abs) over (partition by final_category) as category_std_amount,
        lag(transaction_date) over (
            partition by normalized_merchant
            order by transaction_date
        ) as previous_merchant_transaction_date
    from enriched
)

select
    *,
    case
        when merchant_std_amount is null or merchant_std_amount = 0 then null
        else (amount_abs - merchant_avg_amount) / merchant_std_amount
    end as zscore_vs_merchant,
    case
        when category_std_amount is null or category_std_amount = 0 then null
        else (amount_abs - category_avg_amount) / category_std_amount
    end as zscore_vs_category,
    date_diff('day', previous_merchant_transaction_date, transaction_date) as days_since_last_transaction_at_merchant
from features
