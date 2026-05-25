with debits as (
    select *
    from {{ ref('fct_transactions') }}
    where is_debit
),

total_spend as (
    select sum(amount_abs) as total_spend
    from debits
),

category_base as (
    select
        final_category,
        sum(amount_abs) as total_spend,
        count(*) as transaction_count,
        avg(amount_abs) as avg_transaction_amount,
        max(amount_abs) as largest_transaction_amount
    from debits
    group by 1
),

category_monthly as (
    select
        final_category,
        date_trunc('month', transaction_date)::date as month,
        sum(amount_abs) as monthly_spend
    from debits
    group by 1, 2
),

category_monthly_stats as (
    select
        final_category,
        avg(monthly_spend) as monthly_avg_spend,
        stddev_samp(monthly_spend) as monthly_spend_stddev
    from category_monthly
    group by 1
),

merchant_category_spend as (
    select
        final_category,
        normalized_merchant,
        sum(amount_abs) as merchant_spend,
        row_number() over (
            partition by final_category
            order by sum(amount_abs) desc
        ) as merchant_rank
    from debits
    group by 1, 2
),

top_merchant as (
    select
        final_category,
        normalized_merchant as top_merchant,
        merchant_spend as top_merchant_spend
    from merchant_category_spend
    where merchant_rank = 1
),

latest_month as (
    select max(month) as month
    from category_monthly
),

latest_prior_spend as (
    select
        category_monthly.final_category,
        sum(case when category_monthly.month = latest_month.month then category_monthly.monthly_spend else 0 end)
            as latest_month_spend,
        sum(
            case
                when category_monthly.month = latest_month.month - interval '1 month'
                    then category_monthly.monthly_spend
                else 0
            end
        ) as prior_month_spend
    from category_monthly
    cross join latest_month
    group by 1
)

select
    category_base.final_category,
    category_base.total_spend,
    category_base.total_spend / nullif(total_spend.total_spend, 0) as spend_share,
    category_monthly_stats.monthly_avg_spend,
    coalesce(category_monthly_stats.monthly_spend_stddev, 0) as monthly_spend_stddev,
    coalesce(category_monthly_stats.monthly_spend_stddev, 0)
        / nullif(category_monthly_stats.monthly_avg_spend, 0) as monthly_spend_volatility,
    category_base.transaction_count,
    category_base.avg_transaction_amount,
    category_base.largest_transaction_amount,
    top_merchant.top_merchant,
    top_merchant.top_merchant_spend,
    latest_prior_spend.latest_month_spend,
    latest_prior_spend.prior_month_spend,
    latest_prior_spend.latest_month_spend - latest_prior_spend.prior_month_spend as latest_mom_change_amount,
    case
        when latest_prior_spend.prior_month_spend >= 50
            then latest_prior_spend.latest_month_spend / nullif(latest_prior_spend.prior_month_spend, 0) - 1
        else null
    end as latest_mom_change_pct
from category_base
cross join total_spend
left join category_monthly_stats using (final_category)
left join top_merchant using (final_category)
left join latest_prior_spend using (final_category)
