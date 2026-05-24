with txns as (
    select *
    from {{ ref('fct_transactions') }}
    where is_debit
),

monthly as (
    select
        date_trunc('month', transaction_date)::date as month,
        final_category,
        sum(amount_abs) as total_spend,
        count(*) as transaction_count,
        avg(amount_abs) as avg_transaction_amount
    from txns
    group by 1, 2
)

select
    *,
    total_spend - lag(total_spend) over (
        partition by final_category
        order by month
    ) as mom_change_amount,
    total_spend / nullif(lag(total_spend) over (
        partition by final_category
        order by month
    ), 0) - 1 as mom_change_pct
from monthly
