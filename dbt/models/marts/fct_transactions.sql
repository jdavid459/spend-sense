with features as (
    select * from {{ ref('int_transaction_features') }}
),

recurring as (
    select normalized_merchant, final_category, is_recurring
    from {{ ref('int_recurring_transactions') }}
)

select
    features.transaction_id,
    features.transaction_date,
    features.post_date,
    features.raw_description,
    features.normalized_merchant,
    features.merchant_group,
    features.merchant_source,
    features.category_source,
    features.ai_confidence,
    features.ai_reasoning,
    features.raw_category,
    features.final_category,
    features.transaction_type,
    features.amount,
    features.amount_abs,
    features.is_debit,
    features.is_credit,
    coalesce(recurring.is_recurring, false) as is_recurring,
    case
        when features.is_debit and features.zscore_vs_merchant >= 2.5 then true
        when features.is_debit and features.zscore_vs_category >= 3.0 then true
        else false
    end as is_anomaly,
    case
        when features.is_debit and features.zscore_vs_merchant >= 2.5
            then 'High amount compared with usual merchant spend'
        when features.is_debit and features.zscore_vs_category >= 3.0
            then 'High amount compared with category spend'
        else null
    end as anomaly_reason,
    features.zscore_vs_merchant,
    features.zscore_vs_category
from features
left join recurring
    on features.normalized_merchant = recurring.normalized_merchant
    and features.final_category = recurring.final_category
