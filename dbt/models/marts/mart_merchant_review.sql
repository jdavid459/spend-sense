with txns as (
    select *
    from {{ ref('fct_transactions') }}
),

merchant_descriptions as (
    select
        raw_description,
        normalized_merchant,
        merchant_group,
        raw_category,
        final_category,
        count(*) as transaction_count,
        sum(case when is_debit then amount_abs else 0 end) as total_spend,
        avg(case when is_debit then amount_abs end) as avg_debit_amount,
        min(transaction_date) as first_seen,
        max(transaction_date) as last_seen,
        sum(case when is_anomaly then 1 else 0 end) as anomaly_count,
        max(case when is_recurring then 1 else 0 end)::boolean as has_recurring_flag
    from txns
    group by 1, 2, 3, 4, 5
),

scored as (
    select
        *,
        case
            when merchant_group = 'Unmapped' then true
            when normalized_merchant = raw_description then true
            else false
        end as needs_review,
        case
            when merchant_group = 'Unmapped' and transaction_count >= 3
                then 'High-frequency unmapped merchant'
            when merchant_group = 'Unmapped' and total_spend >= 250
                then 'High-spend unmapped merchant'
            when normalized_merchant = raw_description
                then 'Raw description used as merchant fallback'
            else 'Mapped by existing rules'
        end as review_reason,
        case
            when merchant_group = 'Unmapped' then 100 else 0
        end
        + least(transaction_count, 25) * 3
        + least(total_spend / 100, 25) as review_priority_score
    from merchant_descriptions
)

select
    raw_description,
    normalized_merchant,
    merchant_group,
    raw_category,
    final_category,
    transaction_count,
    round(total_spend, 2) as total_spend,
    round(avg_debit_amount, 2) as avg_debit_amount,
    first_seen,
    last_seen,
    anomaly_count,
    has_recurring_flag,
    needs_review,
    review_reason,
    round(review_priority_score, 2) as review_priority_score
from scored
order by needs_review desc, review_priority_score desc, total_spend desc
