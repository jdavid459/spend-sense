with debits as (
    select *
    from {{ ref('fct_transactions') }}
    where is_debit
),

monthly_base as (
    select
        date_trunc('month', transaction_date)::date as month,
        sum(amount_abs) as total_spend,
        count(*) as transaction_count,
        avg(amount_abs) as avg_transaction_amount,
        median(amount_abs) as median_transaction_amount,
        sum(case when is_recurring then amount_abs else 0 end) as recurring_spend,
        count(case when is_anomaly then 1 end) as anomaly_count,
        sum(case when is_anomaly then amount_abs else 0 end) as anomaly_spend
    from debits
    group by 1
),

category_monthly as (
    select
        date_trunc('month', transaction_date)::date as month,
        final_category,
        sum(amount_abs) as category_spend,
        row_number() over (
            partition by date_trunc('month', transaction_date)::date
            order by sum(amount_abs) desc
        ) as category_rank
    from debits
    group by 1, 2
),

top_category as (
    select
        month,
        final_category as top_category,
        category_spend as top_category_spend
    from category_monthly
    where category_rank = 1
),

merchant_monthly as (
    select
        date_trunc('month', transaction_date)::date as month,
        normalized_merchant,
        sum(amount_abs) as merchant_spend,
        row_number() over (
            partition by date_trunc('month', transaction_date)::date
            order by sum(amount_abs) desc
        ) as merchant_rank
    from debits
    group by 1, 2
),

top_merchant as (
    select
        month,
        normalized_merchant as top_merchant,
        merchant_spend as top_merchant_spend
    from merchant_monthly
    where merchant_rank = 1
),

with_previous as (
    select
        monthly_base.*,
        lag(total_spend) over (order by month) as previous_month_spend
    from monthly_base
)

select
    with_previous.month,
    with_previous.total_spend,
    with_previous.transaction_count,
    with_previous.avg_transaction_amount,
    with_previous.median_transaction_amount,
    top_category.top_category,
    top_category.top_category_spend,
    top_merchant.top_merchant,
    top_merchant.top_merchant_spend,
    with_previous.recurring_spend,
    with_previous.recurring_spend / nullif(with_previous.total_spend, 0) as recurring_spend_share,
    with_previous.anomaly_count,
    with_previous.anomaly_spend,
    with_previous.total_spend - with_previous.previous_month_spend as mom_spend_change_amount,
    case
        when with_previous.previous_month_spend >= 50
            then with_previous.total_spend / nullif(with_previous.previous_month_spend, 0) - 1
        else null
    end as mom_spend_change_pct
from with_previous
left join top_category using (month)
left join top_merchant using (month)
