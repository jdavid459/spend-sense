with debits as (
    select *
    from {{ ref('int_transaction_features') }}
    where is_debit
),

merchant_summary as (
    select
        normalized_merchant,
        final_category,
        count(*) as transaction_count,
        min(transaction_date) as first_seen,
        max(transaction_date) as last_seen,
        avg(amount_abs) as avg_amount,
        stddev_samp(amount_abs) as amount_stddev,
        avg(days_since_last_transaction_at_merchant) as avg_days_between_transactions
    from debits
    group by 1, 2
)

select
    *,
    case
        when transaction_count >= 3
             and avg_days_between_transactions between 25 and 35
             and coalesce(amount_stddev, 0) <= greatest(avg_amount * 0.15, 3)
            then true
        else false
    end as is_recurring,
    case
        when avg_days_between_transactions between 25 and 35 then 'monthly'
        when avg_days_between_transactions between 6 and 8 then 'weekly'
        else 'irregular'
    end as cadence
from merchant_summary
